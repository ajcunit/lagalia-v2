"""Hub d'integracions: registre, estat i resolució de connectors.

Únic punt d'accés als connectors: comprova l'estat (desactivat → 409,
mai errors críptics), fusiona la configuració i desxifra credencials.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.problems import Problem
from app.integrations.base import Connector, Manifest
from app.integrations.models import ConnectorCredential, ConnectorRecord

ConnectorFactory = Callable[[dict[str, Any], dict[str, str]], Connector]

_REGISTRY: dict[str, tuple[Manifest, ConnectorFactory]] = {}


def register(manifest: Manifest, factory: ConnectorFactory) -> None:
    if manifest.slug in _REGISTRY:
        raise ValueError(f"Connector duplicat: {manifest.slug}")
    _REGISTRY[manifest.slug] = (manifest, factory)


def known_slugs() -> list[str]:
    return sorted(_REGISTRY)


async def ensure_registered(session: AsyncSession, slug: str) -> ConnectorRecord:
    """Crea la fila del connector si no existeix (desactivat per defecte)."""
    manifest, _ = _require_known(slug)
    record = (
        await session.execute(select(ConnectorRecord).where(ConnectorRecord.slug == slug))
    ).scalar_one_or_none()
    if record is None:
        record = ConnectorRecord(slug=slug, manifest=manifest.as_dict(), mode=manifest.mode)
        session.add(record)
        await session.flush()
    return record


def _require_known(slug: str) -> tuple[Manifest, ConnectorFactory]:
    if slug not in _REGISTRY:
        raise LookupError(f"Connector desconegut: {slug}")
    return _REGISTRY[slug]


async def _load_credentials(session: AsyncSession, connector_id: int) -> dict[str, str]:
    rows = (
        await session.execute(
            select(ConnectorCredential).where(ConnectorCredential.connector_id == connector_id)
        )
    ).scalars()
    return {row.name: crypto.decrypt_value(row.value_encrypted) for row in rows}


async def set_credential(session: AsyncSession, connector_id: int, name: str, value: str) -> None:
    """Desa (o rota) una credencial, sempre xifrada."""
    existing = (
        await session.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.connector_id == connector_id,
                ConnectorCredential.name == name,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ConnectorCredential(
                connector_id=connector_id,
                name=name,
                value_encrypted=crypto.encrypt_value(value),
            )
        )
    else:
        existing.value_encrypted = crypto.encrypt_value(value)
    await session.flush()


async def get_connector(session: AsyncSession, slug: str) -> Connector:
    """Resol un connector actiu; desactivat → 409 (mai errors críptics)."""
    manifest, factory = _require_known(slug)
    record = await ensure_registered(session, slug)

    if not record.enabled:
        raise Problem(
            409,
            f"El connector «{manifest.name}» està desactivat",
            "connector-disabled",
        )

    config = {**manifest.config_defaults, **(record.config or {})}
    credentials = await _load_credentials(session, record.id)
    return factory(config, credentials)
