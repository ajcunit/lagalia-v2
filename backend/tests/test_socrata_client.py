"""Client Socrata contra respostes gravades (httpx.MockTransport, sense xarxa)."""

import json
from typing import Any

import httpx
import pytest

from app.integrations import socrata
from app.integrations.base import ConnectorError
from app.integrations.socrata.client import SocrataClient
from app.integrations.socrata.query import SoqlQuery

BASE_URL = "https://analisi.transparenciacatalunya.cat"


def _client(handler: httpx.MockTransport) -> SocrataClient:
    return SocrataClient(BASE_URL, min_interval_seconds=0, transport=handler)


async def test_pagination_until_short_page() -> None:
    pages = {
        "0": [{"codi_expedient": "A"}, {"codi_expedient": "B"}],
        "2": [{"codi_expedient": "C"}],  # pàgina curta: final
    }
    requested_offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = dict(request.url.params)["$offset"]
        requested_offsets.append(offset)
        return httpx.Response(200, json=pages[offset])

    async with _client(httpx.MockTransport(handler)) as client:
        records = [r async for r in client.iter_records(SoqlQuery("ybgg-dgi6"), page_size=2)]

    assert [r["codi_expedient"] for r in records] == ["A", "B", "C"]
    assert requested_offsets == ["0", "2"]


async def test_retry_with_backoff_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socrata.client, "_BACKOFF_BASE_SECONDS", 0.01)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503, text="manteniment")
        return httpx.Response(200, json=[{"ok": True}])

    async with _client(httpx.MockTransport(handler)) as client:
        page = await client.fetch_page(SoqlQuery("ybgg-dgi6").limit(1))

    assert page == [{"ok": True}]
    assert len(attempts) == 3


async def test_gives_up_after_three_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socrata.client, "_BACKOFF_BASE_SECONDS", 0.01)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503)

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match="3 intents"):
            await client.fetch_page(SoqlQuery("ybgg-dgi6"))

    assert len(attempts) == 3


async def test_4xx_fails_immediately_without_retry() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(400, json={"error": True})

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match="400"):
            await client.fetch_page(SoqlQuery("ybgg-dgi6"))

    assert len(attempts) == 1


async def test_app_token_header_sent() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("X-App-Token")
        return httpx.Response(200, json=[])

    client = SocrataClient(
        BASE_URL,
        app_token="token-secret",  # noqa: S106 — valor sintètic de test
        min_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    async with client:
        await client.fetch_page(SoqlQuery("ybgg-dgi6"))

    assert seen["token"] == "token-secret"


async def test_non_list_payload_is_connector_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=json.dumps({"missatge": "no sóc una llista"}))

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match="no és una llista"):
            await client.fetch_page(SoqlQuery("ybgg-dgi6"))
