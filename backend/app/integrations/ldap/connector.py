"""Connector LDAP/Active Directory (specs/ldap-auth.md, docs/08 §2.4).

Dos fluxos d'autenticació, sempre amb el filtre escapat RFC 4515:
- Amb compte de servei: bind de servei → cerca de l'usuari → bind de
  verificació amb el DN trobat.
- Sense compte de servei (paritat amb la v1): bind directe com a usuari
  (UPN amb el sufix de domini) i cerca de la pròpia entrada per obtenir
  els grups.
LDAPS o StartTLS obligatoris: mai un bind en clar. ldap3 és síncron,
per això tota la xarxa corre dins d'un thread.
"""

import asyncio
from typing import Any

import structlog
from ldap3 import BASE, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from app.integrations import hub
from app.integrations.base import ConnectorError, HealthStatus, Manifest

logger = structlog.get_logger()

MANIFEST = Manifest(
    slug="ldap",
    name="Directori corporatiu (LDAP/Active Directory)",
    version="1.0.0",
    capabilities=["auth"],
    config_defaults={
        "server_url": "",
        "port": 636,
        "base_dn": "",
        "domain_suffix": "",
        "starttls": False,
        "timeout_seconds": 5,
    },
    # Compte de servei OPCIONAL: sense credencials es fa bind directe
    # com a usuari (UPN amb domain_suffix), com feia la v1.
    credentials=["bind_dn", "bind_password"],
)

_USER_ATTRIBUTES = ["displayName", "mail", "sAMAccountName", "memberOf"]


def _step(
    trace: list[dict[str, Any]] | None, name: str, ok: bool, detail: str | None = None
) -> None:
    """Anota un pas al diagnòstic; mai hi entra cap contrasenya."""
    if trace is not None:
        trace.append({"step": name, "ok": ok, "detail": detail})


def build_user_filter(identifier: str) -> str:
    """Filtre de cerca amb el valor escapat: cap entrada d'usuari en cru."""
    needle = escape_filter_chars(identifier)
    return (
        "(&(objectClass=user)"
        f"(|(sAMAccountName={needle})(mail={needle})(userPrincipalName={needle})))"
    )


def parse_server_address(url: str, port: int, starttls: bool) -> tuple[str, int, bool]:
    """(host, port, use_ssl) amb transport segur garantit.

    Sense esquema s'assumeix ldaps://; ldap:// només s'accepta amb
    StartTLS. El port de la URL mana sobre el de la config.
    """
    cleaned = url.strip()
    if not cleaned:
        raise ConnectorError("Falta server_url a la configuració del connector ldap")
    use_ssl = True
    if cleaned.startswith("ldaps://"):
        cleaned = cleaned[len("ldaps://") :]
    elif cleaned.startswith("ldap://"):
        if not starttls:
            raise ConnectorError(
                "Transport insegur: cal ldaps:// o bé ldap:// amb starttls activat"
            )
        cleaned = cleaned[len("ldap://") :]
        use_ssl = False
    cleaned = cleaned.rstrip("/")
    if ":" in cleaned:
        host, _, url_port = cleaned.rpartition(":")
        if not url_port.isdigit():
            raise ConnectorError(f"server_url invàlida: «{url}»")
        return host, int(url_port), use_ssl
    return cleaned, port, use_ssl


def upn_candidates(identifier: str, domain_suffix: str) -> list[str]:
    """UPN a provar per al bind directe, en ordre.

    Primer el que ha escrit l'usuari; si hi ha sufix de domini i canvia
    alguna cosa, també la part local amb el sufix (cas típic: login amb
    el correu @cunit.cat però UPN d'AD @ajcunit.local).
    """
    candidates = [identifier]
    suffix = domain_suffix.strip()
    if suffix:
        if not suffix.startswith("@"):
            suffix = f"@{suffix}"
        alternate = identifier.split("@", 1)[0] + suffix
        if alternate != identifier:
            candidates.append(alternate)
    return candidates


class LdapConnector:
    manifest = MANIFEST

    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        self.config = config
        self._bind_dn = credentials.get("bind_dn") or ""
        self._bind_password = credentials.get("bind_password") or ""

    # ── transport ──────────────────────────────────────────────────

    def _server(self) -> Server:
        host, port, use_ssl = parse_server_address(
            str(self.config.get("server_url") or ""),
            int(self.config.get("port") or 636),
            bool(self.config.get("starttls")),
        )
        timeout = int(self.config.get("timeout_seconds") or 5)
        return Server(host, port=port, use_ssl=use_ssl, connect_timeout=timeout, get_info=None)

    def _open(self, server: Server, user: str, password: str) -> Connection:
        """Obre la connexió; StartTLS abans del bind si el canal no és SSL."""
        timeout = int(self.config.get("timeout_seconds") or 5)
        conn = Connection(
            server, user=user, password=password, receive_timeout=timeout, auto_bind=False
        )
        conn.open()
        if not server.ssl:
            if not conn.start_tls():
                conn.unbind()
                raise ConnectorError("StartTLS ha fallat")
        return conn

    # ── autenticació ───────────────────────────────────────────────

    def _search_user(self, conn: Connection, base_dn: str, identifier: str) -> list[Any]:
        conn.search(
            search_base=base_dn,
            search_filter=build_user_filter(identifier),
            search_scope=SUBTREE,
            attributes=_USER_ATTRIBUTES,
            size_limit=2,
        )
        return list(conn.entries)

    def _profile_from_entry(self, entry: Any, identifier: str) -> dict[str, Any]:
        attrs = entry.entry_attributes_as_dict
        mail = (attrs.get("mail") or [None])[0]
        sam = (attrs.get("sAMAccountName") or [None])[0]
        name = (attrs.get("displayName") or [None])[0]
        return {
            "dn": str(entry.entry_dn),
            "name": str(name or sam or identifier),
            "email": str(mail).lower() if mail else None,
            "sam": str(sam) if sam else None,
            "groups": [str(g) for g in attrs.get("memberOf") or []],
        }

    def _authenticate_sync(
        self, identifier: str, password: str, trace: list[dict[str, Any]] | None = None
    ) -> dict[str, Any] | None:
        # Contrasenya buida = bind anònim a molts directoris: es rebutja
        # aquí, abans de tocar la xarxa.
        if not identifier.strip() or not password.strip():
            _step(trace, "credencials", False, "usuari o contrasenya en blanc")
            return None
        base_dn = str(self.config.get("base_dn") or "").strip()
        if not base_dn:
            raise ConnectorError("Falta base_dn a la configuració del connector ldap")
        server = self._server()

        if self._bind_dn and self._bind_password:
            return self._auth_with_service_account(server, base_dn, identifier, password, trace)
        return self._auth_direct_bind(server, base_dn, identifier, password, trace)

    def _auth_with_service_account(
        self,
        server: Server,
        base_dn: str,
        identifier: str,
        password: str,
        trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Bind de servei → cerca → bind de verificació amb el DN trobat."""
        try:
            service = self._open(server, self._bind_dn, self._bind_password)
        except LDAPException as exc:
            _step(trace, "connexió", False, str(exc))
            raise ConnectorError(f"No es pot connectar amb el directori: {exc}") from exc
        try:
            if not service.bind():
                _step(trace, "bind de servei", False, str(service.result.get("description")))
                raise ConnectorError("El bind del compte de servei ha fallat")
            _step(trace, "bind de servei", True)
            entries = self._search_user(service, base_dn, identifier)
        except ConnectorError:
            raise
        except LDAPException as exc:
            _step(trace, "cerca", False, str(exc))
            raise ConnectorError(f"Error de cerca al directori: {exc}") from exc
        finally:
            service.unbind()

        if len(entries) != 1:
            # 0 = desconegut; >1 = ambigu (mai s'endevina): totes dues → refús.
            _step(trace, "cerca", False, f"{len(entries)} entrades per a «{identifier}»")
            return None
        entry = entries[0]
        _step(trace, "cerca", True, str(entry.entry_dn))

        try:
            verify = self._open(server, str(entry.entry_dn), password)
        except LDAPException as exc:
            _step(trace, "connexió", False, str(exc))
            raise ConnectorError(f"No es pot connectar amb el directori: {exc}") from exc
        try:
            if not verify.bind():
                _step(trace, "bind d'usuari", False, "contrasenya incorrecta")
                return None
        except LDAPException as exc:
            _step(trace, "bind d'usuari", False, str(exc))
            return None
        finally:
            verify.unbind()
        _step(trace, "bind d'usuari", True)
        return self._profile_from_entry(entry, identifier)

    def _auth_direct_bind(
        self,
        server: Server,
        base_dn: str,
        identifier: str,
        password: str,
        trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Sense compte de servei: bind com a usuari (UPN) i cerca pròpia.

        Es proven els candidats d'UPN en ordre (login tal qual, i part
        local + sufix de domini) fins que un bind entra.
        """
        candidates = upn_candidates(identifier, str(self.config.get("domain_suffix") or ""))
        conn: Connection | None = None
        bound_upn: str | None = None
        try:
            for upn in candidates:
                try:
                    attempt = self._open(server, upn, password)
                except LDAPException as exc:
                    _step(trace, "connexió", False, str(exc))
                    raise ConnectorError(f"No es pot connectar amb el directori: {exc}") from exc
                try:
                    bound = attempt.bind()
                except LDAPException:
                    bound = False
                if bound:
                    conn, bound_upn = attempt, upn
                    _step(trace, "bind d'usuari", True, upn)
                    break
                _step(trace, "bind d'usuari", False, f"refusat per a «{upn}»")
                attempt.unbind()

            if conn is None:
                return None  # cap candidat: credencials invàlides

            try:
                entries = self._search_user(conn, base_dn, identifier)
                if not entries and bound_upn != identifier:
                    entries = self._search_user(conn, base_dn, str(bound_upn))
            except LDAPException as exc:
                _step(trace, "cerca", False, str(exc))
                raise ConnectorError(f"Error de cerca al directori: {exc}") from exc
        finally:
            if conn is not None:
                conn.unbind()
        if len(entries) != 1:
            _step(trace, "cerca", False, f"{len(entries)} entrades sota «{base_dn}»")
            return None
        _step(trace, "cerca", True, str(entries[0].entry_dn))
        return self._profile_from_entry(entries[0], identifier)

    async def authenticate(
        self, identifier: str, password: str, trace: list[dict[str, Any]] | None = None
    ) -> dict[str, Any] | None:
        """Perfil de l'usuari si les credencials són vàlides; None si no ho són.

        ConnectorError només per problemes d'infraestructura (AD caigut,
        timeout, TLS): el caller decideix el fallback. `trace` (opcional)
        recull els passos per al diagnòstic de la pantalla.
        """
        return await asyncio.to_thread(self._authenticate_sync, identifier, password, trace)

    # ── salut ──────────────────────────────────────────────────────

    def _healthcheck_sync(self) -> HealthStatus:
        base_dn = str(self.config.get("base_dn") or "").strip()
        if not (self._bind_dn and self._bind_password):
            # Sense compte de servei no hi ha bind possible sense un usuari
            # real: es valida transport i abast, i prou.
            try:
                self._server()
            except ConnectorError as exc:
                return HealthStatus(False, str(exc))
            return HealthStatus(
                True, "sense compte de servei: la connexió es prova al primer login"
            )
        try:
            server = self._server()
            conn = self._open(server, self._bind_dn, self._bind_password)
            try:
                if not conn.bind():
                    return HealthStatus(False, "El bind del compte de servei ha fallat")
                if base_dn:
                    conn.search(base_dn, "(objectClass=*)", BASE, attributes=[], size_limit=1)
            finally:
                conn.unbind()
        except (ConnectorError, LDAPException) as exc:
            return HealthStatus(False, str(exc))
        return HealthStatus(True)

    async def healthcheck(self) -> HealthStatus:
        return await asyncio.to_thread(self._healthcheck_sync)


def _factory(config: dict[str, Any], credentials: dict[str, str]) -> LdapConnector:
    return LdapConnector(config, credentials)


hub.register(MANIFEST, _factory)
