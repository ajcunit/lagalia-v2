"""Connector pscp (contractaciopublica.cat): client amb throttling respectuós."""

import asyncio
import time
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlparse

import httpx

from app.integrations import hub
from app.integrations.base import ConnectorError, HealthStatus, Manifest

MANIFEST = Manifest(
    slug="pscp",
    name="Plataforma de Serveis de Contractació Pública",
    version="1.0.0",
    capabilities=["phase_read", "document_download"],
    config_defaults={
        "base_url": "https://contractaciopublica.cat",
        # Valors v1 conservats: 2 s/petició (08 §2.2), ara asíncron real.
        "min_interval_seconds": 2.0,
        "max_document_bytes": 20 * 1024 * 1024,
    },
    credentials=[],
)


class PscpClient:
    def __init__(
        self,
        base_url: str,
        *,
        min_interval_seconds: float,
        max_document_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_document_bytes = max_document_bytes
        self._allowed_host = urlparse(self.base_url).hostname
        self._client = httpx.AsyncClient(timeout=60, transport=transport)
        self._min_interval = min_interval_seconds
        self._last_request_at = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    def _check_host(self, url: str) -> None:
        """Anti-SSRF: només el domini configurat del connector."""
        host = urlparse(url).hostname
        if host != self._allowed_host:
            raise ConnectorError(f"URL fora del domini del connector: {host}")

    async def _throttle(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_at = time.monotonic()

    async def fetch_phase(self, url: str) -> dict[str, Any]:
        self._check_host(url)
        await self._throttle()
        try:
            response = await self._client.get(url)
        except httpx.TransportError as exc:
            raise ConnectorError(f"pscp inaccessible: {exc}") from exc
        if response.status_code != 200:
            raise ConnectorError(f"pscp ha respost {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ConnectorError("JSON de fase inesperat")
        return payload

    async def download_document(self, url: str) -> tuple[bytes, str]:
        self._check_host(url)
        await self._throttle()
        try:
            response = await self._client.get(url)
        except httpx.TransportError as exc:
            raise ConnectorError(f"descàrrega fallida: {exc}") from exc
        if response.status_code != 200:
            raise ConnectorError(f"descàrrega ha respost {response.status_code}")
        content = response.content
        if len(content) > self.max_document_bytes:
            raise ConnectorError(f"document massa gran ({len(content)} bytes)")
        return content, response.headers.get("content-type", "application/octet-stream")


class PscpConnector:
    manifest = MANIFEST

    def __init__(self, config: dict[str, Any], _credentials: dict[str, str]) -> None:
        self.config = config

    def client(self) -> PscpClient:
        return PscpClient(
            self.config["base_url"],
            min_interval_seconds=float(self.config["min_interval_seconds"]),
            max_document_bytes=int(self.config["max_document_bytes"]),
        )

    async def healthcheck(self) -> HealthStatus:
        try:
            async with self.client() as client:
                await client._throttle()
                response = await client._client.get(self.config["base_url"])
                if response.status_code >= 500:
                    return HealthStatus(healthy=False, detail=str(response.status_code))
        except (httpx.TransportError, ConnectorError) as exc:
            return HealthStatus(healthy=False, detail=str(exc))
        return HealthStatus(healthy=True)


def _factory(config: dict[str, Any], credentials: dict[str, str]) -> PscpConnector:
    return PscpConnector(config, credentials)


hub.register(MANIFEST, _factory)
