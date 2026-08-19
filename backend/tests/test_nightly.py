"""Cadena nocturna de sincronització (specs/sync-schedule.md)."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.jobs import nightly, registry

pytestmark = pytest.mark.anyio


def test_parse_days() -> None:
    assert nightly.parse_days(None) == {1, 2, 3, 4, 5, 6, 7}
    assert nightly.parse_days("") == {1, 2, 3, 4, 5, 6, 7}
    assert nightly.parse_days("[1, 3, 5]") == {1, 3, 5}
    assert nightly.parse_days([2, 4]) == {2, 4}  # JSONB ja tipat
    assert nightly.parse_days("no és json") == {1, 2, 3, 4, 5, 6, 7}
    assert nightly.parse_days("[9, 0]") == {1, 2, 3, 4, 5, 6, 7}  # fora de rang = tots


def test_parse_time_and_enabled() -> None:
    assert nightly.parse_time("06:15").hour == 6
    assert nightly.parse_time("garbage").hour == 2  # fallback 02:30
    assert nightly.parse_enabled(None) is True
    assert nightly.parse_enabled("false") is False
    assert nightly.parse_enabled(False) is False
    assert nightly.parse_enabled("true") is True
    # L'informe d'auditoria neix desactivat: default=False quan no hi ha setting.
    assert nightly.parse_enabled(None, default=False) is False
    assert nightly.parse_enabled("true", default=False) is True


def test_parse_interval_days() -> None:
    assert nightly.parse_interval_days("15") == 15
    assert nightly.parse_interval_days(7) == 7
    assert nightly.parse_interval_days(None) == 30
    assert nightly.parse_interval_days("garbage") == 30
    assert nightly.parse_interval_days("0") == 30  # fora de rang = per defecte
    assert nightly.parse_interval_days("9999") == 30


def test_nightly_due_respects_local_time_and_days() -> None:
    # 01:00 UTC hivern = 02:00 Europe/Madrid → abans de les 02:30: no toca.
    before = datetime(2026, 1, 14, 1, 0, tzinfo=UTC)  # dimecres
    after = datetime(2026, 1, 14, 1, 45, tzinfo=UTC)  # 02:45 local
    common = {"enabled_raw": None, "time_raw": "02:30"}
    assert nightly.nightly_due(before, days_raw=None, **common) is False
    assert nightly.nightly_due(after, days_raw=None, **common) is True
    # Dia no actiu (dimecres = 3) → no toca encara que l'hora hagi passat.
    assert nightly.nightly_due(after, days_raw="[1, 2]", **common) is False
    # Desactivada → mai.
    assert (
        nightly.nightly_due(after, enabled_raw="false", time_raw="02:30", days_raw=None) is False
    )


async def test_nightly_chain_runs_in_order_and_survives_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def make_handler(name: str, fail: bool = False) -> Any:
        async def handler(ctx: registry.JobContext) -> dict[str, Any]:
            calls.append(name)
            if fail:
                raise RuntimeError("pas trencat")
            return {"step": name}

        return handler

    for step in nightly.NIGHTLY_STEPS:
        monkeypatch.setitem(
            registry._REGISTRY, step, make_handler(step, fail=step == "sync.extensions")
        )

    async def set_progress(pct: int, message: str | None) -> None:
        pass

    ctx = registry.JobContext(job_id=uuid4(), payload={}, set_progress=set_progress)
    with pytest.raises(RuntimeError, match="sync.extensions"):
        await nightly.sync_nightly(ctx)
    # Tots els passos s'han executat, en l'ordre prescrit, malgrat la fallada.
    assert calls == nightly.NIGHTLY_STEPS


async def test_nightly_chain_success(monkeypatch: pytest.MonkeyPatch) -> None:
    for step in nightly.NIGHTLY_STEPS:

        async def handler(ctx: registry.JobContext, _step: str = step) -> dict[str, Any]:
            return {"step": _step}

        monkeypatch.setitem(registry._REGISTRY, step, handler)

    async def set_progress(pct: int, message: str | None) -> None:
        pass

    ctx = registry.JobContext(job_id=uuid4(), payload={}, set_progress=set_progress)
    result = await nightly.sync_nightly(ctx)
    assert set(result) == set(nightly.NIGHTLY_STEPS)
    assert result["sync.contracts"] == {"step": "sync.contracts"}
