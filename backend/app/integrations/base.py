"""Interfície comuna dels connectors (docs/08-hub-integracions.md §1).

El domini no coneix els connectors: consumeix capacitats resoltes pel
hub. Cada connector declara un manifest i rep la configuració i les
credencials desxifrades — mai les llegeix pel seu compte.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Manifest:
    slug: str
    name: str
    version: str
    mode: str = "native"
    capabilities: list[str] = field(default_factory=list)
    config_defaults: dict[str, Any] = field(default_factory=dict)
    credentials: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "version": self.version,
            "mode": self.mode,
            "capabilities": self.capabilities,
            "config_schema": {},
            "credentials": self.credentials,
        }


@dataclass(frozen=True)
class HealthStatus:
    healthy: bool
    detail: str | None = None


class Connector(Protocol):
    manifest: Manifest

    async def healthcheck(self) -> HealthStatus: ...


class ConnectorError(Exception):
    """Error operatiu d'un connector (xarxa, resposta invàlida...)."""
