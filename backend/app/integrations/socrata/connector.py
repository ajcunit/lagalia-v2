"""Connector socrata: manifest, fàbrica i healthcheck."""

from typing import Any

from app.integrations import hub
from app.integrations.base import ConnectorError, HealthStatus, Manifest
from app.integrations.socrata.client import SocrataClient
from app.integrations.socrata.query import SoqlQuery, validate_dataset_id

MANIFEST = Manifest(
    slug="socrata",
    name="Transparència Catalunya (Socrata)",
    version="1.0.0",
    capabilities=["contracts_read", "rpc_read", "cpv_read"],
    config_defaults={
        "base_url": "https://analisi.transparenciacatalunya.cat",
        "dataset_contracts": "ybgg-dgi6",
        "dataset_rpc": "hb6v-jcbf",
        "dataset_execution": "8idu-wkjv",
        "dataset_cpv": "wxdw-5eyv",
        "min_interval_seconds": 0.5,
        # Camp d'actualització per a sync incremental "quan el dataset ho
        # permet" (08 §2.1). Verificat 2026-08-12: el dataset real NO té
        # data_actualitzacio → per defecte, sync complet.
        "incremental_field": None,
    },
    credentials=["app_token"],
)


class SocrataConnector:
    manifest = MANIFEST

    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        self.config = config
        self._app_token = credentials.get("app_token")
        for key in ("dataset_contracts", "dataset_rpc", "dataset_cpv", "dataset_execution"):
            validate_dataset_id(config[key])

    def client(self) -> SocrataClient:
        return SocrataClient(
            self.config["base_url"],
            app_token=self._app_token,
            min_interval_seconds=float(self.config["min_interval_seconds"]),
        )

    async def healthcheck(self) -> HealthStatus:
        query = SoqlQuery(self.config["dataset_contracts"]).limit(1)
        try:
            async with self.client() as client:
                await client.fetch_page(query)
        except ConnectorError as exc:
            return HealthStatus(healthy=False, detail=str(exc))
        return HealthStatus(healthy=True)


def _factory(config: dict[str, Any], credentials: dict[str, str]) -> SocrataConnector:
    return SocrataConnector(config, credentials)


hub.register(MANIFEST, _factory)
