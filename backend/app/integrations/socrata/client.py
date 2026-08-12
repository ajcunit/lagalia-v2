"""Client HTTP de l'API Socrata: paginació, reintents i throttling.

Sense estat global: cada job en crea un i el tanca. TLS sempre verificat
(prohibició explícita del projecte).
"""

import asyncio
import time
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any, Self

import httpx
import structlog

from app.integrations.base import ConnectorError
from app.integrations.socrata.query import SoqlQuery

logger = structlog.get_logger()

_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


class SocrataClient:
    def __init__(
        self,
        base_url: str,
        *,
        app_token: str | None = None,
        timeout_seconds: float = 30.0,
        min_interval_seconds: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Accept": "application/json"}
        if app_token:
            headers["X-App-Token"] = app_token
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )
        self._min_interval = min_interval_seconds
        self._last_request_at = 0.0
        self._throttle_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        async with self._throttle_lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_at = time.monotonic()

    async def fetch_page(self, query: SoqlQuery) -> list[dict[str, Any]]:
        """Una pàgina, amb reintents exponencials sobre 5xx i errors de xarxa."""
        url = f"/resource/{query.dataset_id}.json"
        last_error: Exception | None = None
        for attempt in range(1, _RETRIES + 1):
            await self._throttle()
            try:
                response = await self._client.get(url, params=query.params())
            except httpx.TransportError as exc:
                last_error = exc
            else:
                if response.status_code < 500:
                    if response.status_code >= 400:
                        # 4xx: consulta mal formada; reintentari-ho no ajuda.
                        raise ConnectorError(f"Socrata ha respost {response.status_code}")
                    payload = response.json()
                    if not isinstance(payload, list):
                        raise ConnectorError("Resposta Socrata inesperada (no és una llista)")
                    return payload
                last_error = ConnectorError(f"Socrata ha respost {response.status_code}")

            if attempt < _RETRIES:
                delay = _BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
                logger.warning("socrata_retry", attempt=attempt, delay=delay, error=str(last_error))
                await asyncio.sleep(delay)
        raise ConnectorError(f"Socrata inaccessible després de {_RETRIES} intents") from (
            last_error
        )

    async def iter_records(
        self, query: SoqlQuery, *, page_size: int = 1000
    ) -> AsyncIterator[dict[str, Any]]:
        """Recorre el dataset per $offset fins a la primera pàgina curta."""
        offset = 0
        while True:
            page = await self.fetch_page(query.limit(page_size).offset(offset))
            for record in page:
                yield record
            if len(page) < page_size:
                return
            offset += page_size
