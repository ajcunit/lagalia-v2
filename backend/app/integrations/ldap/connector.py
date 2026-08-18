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


def build_upn(identifier: str, domain_suffix: str) -> str:
    """usuari → usuari@domini (si cal) per al bind directe sense servei."""
    if "@" in identifier or not domain_suffix.strip():
        return identifier
    suffix = domain_suffix.strip()
    return identifier + (suffix if suffix.startswith("@") else f"@{suffix}")


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

    def _authenticate_sync(self, identifier: str, password: str) -> dict[str, Any] | None:
        # Contrasenya buida = bind anònim a molts directoris: es rebutja
        # aquí, abans de tocar la xarxa.
        if not identifier.strip() or not password.strip():
            return None
        base_dn = str(self.config.get("base_dn") or "").strip()
        if not base_dn:
            raise ConnectorError("Falta base_dn a la configuració del connector ldap")
        server = self._server()

        if self._bind_dn and self._bind_password:
            return self._auth_with_service_account(server, base_dn, identifier, password)
        return self._auth_direct_bind(server, base_dn, identifier, password)

    def _auth_with_service_account(
        self, server: Server, base_dn: str, identifier: str, password: str
    ) -> dict[str, Any] | None:
        """Bind de servei → cerca → bind de verificació amb el DN trobat."""
        try:
            service = self._open(server, self._bind_dn, self._bind_password)
        except LDAPException as exc:
            raise ConnectorError(f"No es pot connectar amb el directori: {exc}") from exc
        try:
            if not service.bind():
                raise ConnectorError("El bind del compte de servei ha fallat")
            entries = self._search_user(service, base_dn, identifier)
        except ConnectorError:
            raise
        except LDAPException as exc:
            raise ConnectorError(f"Error de cerca al directori: {exc}") from exc
        finally:
            service.unbind()

        if len(entries) != 1:
            # 0 = desconegut; >1 = ambigu (mai s'endevina): totes dues → refús.
            return None
        entry = entries[0]

        try:
            verify = self._open(server, str(entry.entry_dn), password)
        except LDAPException as exc:
            raise ConnectorError(f"No es pot connectar amb el directori: {exc}") from exc
        try:
            if not verify.bind():
                return None
        except LDAPException:
            return None
        finally:
            verify.unbind()
        return self._profile_from_entry(entry, identifier)

    def _auth_direct_bind(
        self, server: Server, base_dn: str, identifier: str, password: str
    ) -> dict[str, Any] | None:
        """Sense compte de servei: bind com a usuari (UPN) i cerca pròpia."""
        upn = build_upn(identifier, str(self.config.get("domain_suffix") or ""))
        try:
            conn = self._open(server, upn, password)
        except LDAPException as exc:
            raise ConnectorError(f"No es pot connectar amb el directori: {exc}") from exc
        try:
            try:
                if not conn.bind():
                    return None  # credencials invàlides
            except LDAPException:
                return None
            try:
                entries = self._search_user(conn, base_dn, identifier)
                if not entries and upn != identifier:
                    entries = self._search_user(conn, base_dn, upn)
            except LDAPException as exc:
                raise ConnectorError(f"Error de cerca al directori: {exc}") from exc
        finally:
            conn.unbind()
        if len(entries) != 1:
            return None
        return self._profile_from_entry(entries[0], identifier)

    async def authenticate(self, identifier: str, password: str) -> dict[str, Any] | None:
        """Perfil de l'usuari si les credencials són vàlides; None si no ho són.

        ConnectorError només per problemes d'infraestructura (AD caigut,
        timeout, TLS): el caller decideix el fallback.
        """
        return await asyncio.to_thread(self._authenticate_sync, identifier, password)

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
