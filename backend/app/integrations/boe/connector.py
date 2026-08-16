"""Connector boe: normes consolidades del BOE (specs/legal-corpus.md; 08 §2.6).

Dades obertes, sense credencials; TLS sempre verificat.
"""

import re
from typing import Any
from xml.etree.ElementTree import ParseError

import httpx
from defusedxml.ElementTree import fromstring as safe_fromstring

from app.integrations import hub
from app.integrations.base import ConnectorError, HealthStatus, Manifest

MANIFEST = Manifest(
    slug="boe",
    name="BOE — legislació consolidada",
    version="1.0.0",
    capabilities=["legal_corpus"],
    config_defaults={
        "base_url": "https://www.boe.es",
        # Normes subscrites (identificadors BOE). LCSP per defecte.
        "norm_ids": ["BOE-A-2017-12902"],
    },
    credentials=[],
)

_ARTICLE_RE = re.compile(
    r"^\s*(Artículo\s+\d+[a-z]*(?:\s*bis|\s*ter|\s*quáter)?|"
    r"Disposición\s+(?:adicional|transitoria|final|derogatoria)[^.]*)\.?",
    re.IGNORECASE,
)


def parse_articles(xml_bytes: bytes) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Retorna (metadades, articles) del XML consolidat.

    L'índex inicial repeteix els encapçalaments sense cos: per a cada
    etiqueta es conserva el bloc amb més contingut (el cos real).
    """
    root = safe_fromstring(xml_bytes)
    meta_node = root.find("metadatos")
    meta: dict[str, str] = {}
    if meta_node is not None:
        for item in meta_node:
            meta[item.tag] = (item.text or "").strip()
    meta["fecha_actualizacion"] = root.attrib.get("fecha_actualizacion", "")

    paragraphs = ["".join(p.itertext()).strip() for p in root.findall("./texto/p")]
    blocks: dict[str, str] = {}
    label: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if label is None:
            return
        body = "\n".join(buffer).strip()
        if len(body) > len(blocks.get(label, "")):
            blocks[label] = body

    for text_value in paragraphs:
        match = _ARTICLE_RE.match(text_value)
        if match:
            flush()
            label = " ".join(match.group(1).split())[:120]
            buffer = [text_value]
        elif label is not None:
            buffer.append(text_value)
    flush()

    articles = [
        {"label": key, "content": value}
        for key, value in blocks.items()
        if len(value) > 80  # descarta entrades d'índex sense cos
    ]
    return meta, articles


class BoeConnector:
    manifest = MANIFEST

    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        self.config = config

    @property
    def norm_ids(self) -> list[str]:
        raw = self.config.get("norm_ids") or []
        return [str(x) for x in raw if str(x).strip()]

    async def fetch_norm(self, boe_id: str) -> tuple[dict[str, str], list[dict[str, str]]]:
        base = str(self.config["base_url"]).rstrip("/")
        url = f"{base}/diario_boe/xml.php?id={boe_id}"
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            try:
                response = await client.get(url)
            except httpx.TransportError as exc:
                raise ConnectorError(f"BOE inaccessible: {exc}") from exc
        if response.status_code != 200:
            raise ConnectorError(f"el BOE ha respost {response.status_code} per a {boe_id}")
        try:
            return parse_articles(response.content)
        except ParseError as exc:
            raise ConnectorError(f"XML del BOE il·legible: {exc}") from exc

    async def healthcheck(self) -> HealthStatus:
        try:
            meta, articles = await self.fetch_norm(self.norm_ids[0] if self.norm_ids else "")
        except (ConnectorError, IndexError) as exc:
            return HealthStatus(healthy=False, detail=str(exc))
        return HealthStatus(
            healthy=True,
            detail=f"{meta.get('titulo', '')[:60]} — {len(articles)} articles",
        )


def _factory(config: dict[str, Any], credentials: dict[str, str]) -> BoeConnector:
    return BoeConnector(config, credentials)


hub.register(MANIFEST, _factory)
