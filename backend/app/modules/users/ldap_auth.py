"""Login via directori corporatiu (specs/ldap-auth.md).

Provisió automàtica: el grup de rol dona accés i fixa el rol (el més alt
si n'hi ha més d'un); els grups de departament assignen l'abast i se
sincronitzen a cada login. Si l'AD cau, aquest mòdul falla en silenci i
el login local continua intacte.
"""

from dataclasses import dataclass

import structlog
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import Problem
from app.integrations import hub
from app.integrations.base import ConnectorError
from app.integrations.ldap.connector import LdapConnector
from app.modules.users import repository
from app.modules.users.models import LdapGroupMapping, User, UserRole, user_departments

logger = structlog.get_logger()

_ROLE_PRIORITY = {
    UserRole.EMPLOYEE: 1,
    UserRole.DEPT_MANAGER: 2,
    UserRole.PROCUREMENT_MANAGER: 3,
    UserRole.ADMIN: 4,
}


@dataclass(frozen=True)
class LdapLoginResult:
    user: User
    provisioned: bool  # usuari creat o actualitzat des de l'AD en aquest login


def _group_tokens(groups: list[str]) -> set[str]:
    """DN sencer + CN del primer RDN, tot en minúscules per comparar."""
    tokens: set[str] = set()
    for group in groups:
        cleaned = group.strip().lower()
        if not cleaned:
            continue
        tokens.add(cleaned)
        first_rdn = cleaned.split(",", 1)[0].strip()
        if first_rdn.startswith("cn="):
            tokens.add(first_rdn[3:].strip())
    return tokens


def resolve_mappings(
    mappings: list[LdapGroupMapping], groups: list[str]
) -> tuple[UserRole | None, set[int]]:
    """(rol més alt de les regles de rol casades, unió de departaments)."""
    tokens = _group_tokens(groups)
    role: UserRole | None = None
    department_ids: set[int] = set()
    for mapping in mappings:
        if mapping.ad_group.strip().lower() not in tokens:
            continue
        if mapping.role is not None:
            if role is None or _ROLE_PRIORITY[mapping.role] > _ROLE_PRIORITY[role]:
                role = mapping.role
        elif mapping.department_id is not None:
            department_ids.add(mapping.department_id)
    return role, department_ids


async def _resolve_connector(session: AsyncSession) -> LdapConnector | None:
    try:
        connector = await hub.get_connector(session, "ldap")
    except Problem:
        return None  # desactivat: el login local segueix el seu curs
    return connector if isinstance(connector, LdapConnector) else None


async def try_ldap_login(
    session: AsyncSession, email: str, password: str
) -> LdapLoginResult | None:
    """Autentica contra l'AD i provisiona/actualitza l'usuari.

    None = no aplica o credencials invàlides: el caller tracta el cas com
    un login fallit normal. Mai llança per un AD caigut (només ho audita
    al log estructurat).
    """
    connector = await _resolve_connector(session)
    if connector is None:
        return None

    try:
        profile = await connector.authenticate(email, password)
    except ConnectorError as exc:
        logger.warning("ldap_unavailable", error=str(exc))
        return None
    if profile is None:
        return None

    mappings = list((await session.execute(select(LdapGroupMapping))).scalars())
    role, department_ids = resolve_mappings(mappings, profile["groups"])
    if role is None:
        # Sense grup de rol no hi ha accés: l'AD autentica, la plataforma no.
        logger.info("ldap_login_denied_no_role", identifier=email)
        return None

    profile_email = profile.get("email") or email
    user = await repository.get_user_by_email(session, profile_email)
    if user is not None and user.password_hash is not None:
        # Compte local amb contrasenya pròpia: l'AD no el toca mai.
        return None

    provisioned = False
    if user is None:
        user = User(
            name=profile["name"],
            email=profile_email,
            role=role,
            active=True,
            password_hash=None,
        )
        session.add(user)
        await session.flush()
        provisioned = True
    elif user.name != profile["name"] or user.role != role:
        user.name = profile["name"]
        user.role = role
        provisioned = True

    # Sincronització de departaments: el directori mana a cada login.
    current = {
        row.department_id
        for row in (
            await session.execute(
                select(user_departments.c.department_id).where(
                    user_departments.c.user_id == user.id
                )
            )
        ).all()
    }
    if current != department_ids:
        await session.execute(delete(user_departments).where(user_departments.c.user_id == user.id))
        for department_id in sorted(department_ids):
            await session.execute(
                insert(user_departments).values(user_id=user.id, department_id=department_id)
            )
        provisioned = True

    # Recàrrega amb departments carregats (el login en depèn).
    refreshed = await repository.get_user_by_email(session, profile_email)
    if refreshed is None:  # impossible: acabem de crear-lo o trobar-lo
        raise RuntimeError("usuari LDAP desaparegut després de la provisió")
    return LdapLoginResult(user=refreshed, provisioned=provisioned)
