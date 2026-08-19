"""Hub d'integracions: registre, estat activat/desactivat i credencials."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.integrations.socrata.connector  # noqa: F401 — registra el connector
from app.core.config import settings
from app.core.db import session_factory
from app.core.problems import Problem
from app.integrations import hub
from app.integrations.socrata.connector import SocrataConnector


@pytest.fixture(autouse=True)
async def clean_connector_rows() -> AsyncIterator[None]:
    """Els tests volen un socrata verge, però la BD és la de dev: es desa
    l'estat real i es restaura al final (esborrar-lo el deixava desactivat
    i sense config — trencava el SuperBuscador i les syncs de debò)."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        saved = (
            (
                await conn.execute(
                    text(
                        "SELECT enabled, mode, manifest, config, health_status "
                        "FROM connectors WHERE slug = 'socrata'"
                    )
                )
            )
            .mappings()
            .first()
        )
        await conn.execute(text("DELETE FROM connectors WHERE slug = 'socrata'"))
    yield
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM connectors WHERE slug = 'socrata'"))
        if saved is not None:
            import json as _json

            row = dict(saved)
            await conn.execute(
                text(
                    "INSERT INTO connectors "
                    "(slug, enabled, mode, manifest, config, health_status) "
                    "VALUES ('socrata', :enabled, CAST(:mode AS connector_mode), "
                    "CAST(:manifest AS jsonb), CAST(:config AS jsonb), :health_status)"
                ),
                {
                    "enabled": row["enabled"],
                    "mode": str(row["mode"]),
                    "manifest": _json.dumps(row["manifest"]),
                    "config": _json.dumps(row["config"]) if row["config"] is not None else None,
                    "health_status": row["health_status"],
                },
            )
    await engine.dispose()


async def test_unknown_slug_raises() -> None:
    async with session_factory() as session:
        with pytest.raises(LookupError, match="desconegut"):
            await hub.get_connector(session, "inventat")


async def test_disabled_connector_is_409_problem() -> None:
    async with session_factory() as session:
        with pytest.raises(Problem) as excinfo:
            await hub.get_connector(session, "socrata")
        await session.commit()  # la fila auto-registrada persisteix

    assert excinfo.value.status_code == 409
    assert excinfo.value.error_type == "connector-disabled"


async def test_enabled_connector_with_decrypted_credentials() -> None:
    async with session_factory() as session:
        record = await hub.ensure_registered(session, "socrata")
        record.enabled = True
        await hub.set_credential(session, record.id, "app_token", "token-de-prova")
        await session.commit()
        record_id = record.id

    # La credencial és xifrada a la BD (mai en clar).
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        blob = (
            await conn.execute(
                text(
                    "SELECT value_encrypted FROM connector_credentials "
                    "WHERE connector_id = :id AND name = 'app_token'"
                ),
                {"id": record_id},
            )
        ).scalar_one()
    await engine.dispose()
    assert b"token-de-prova" not in bytes(blob)

    async with session_factory() as session:
        connector = await hub.get_connector(session, "socrata")
        await session.commit()

    assert isinstance(connector, SocrataConnector)
    assert connector._app_token == "token-de-prova"  # noqa: SLF001
    assert connector.config["dataset_contracts"] == "ybgg-dgi6"


async def test_config_overrides_manifest_defaults() -> None:
    async with session_factory() as session:
        record = await hub.ensure_registered(session, "socrata")
        record.enabled = True
        record.config = {"dataset_contracts": "abcd-1234"}
        await session.commit()

    async with session_factory() as session:
        connector = await hub.get_connector(session, "socrata")
        await session.commit()

    assert isinstance(connector, SocrataConnector)
    assert connector.config["dataset_contracts"] == "abcd-1234"
    assert connector.config["dataset_cpv"] == "wxdw-5eyv"  # default intacte
