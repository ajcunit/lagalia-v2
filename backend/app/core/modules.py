"""Mòduls activables des de la configuració (specs/module-flags.md).

Un sol punt d'aplicació: el middleware de main.py talla les rutes dels
mòduls desactivats (403 `module-disabled`). El nucli (contractes,
usuaris, configuració, auditoria de seguretat) no és desactivable mai.
"""

import json
import time
from typing import Any

MODULES: dict[str, str] = {
    "minor_contracts": "Contractes menors",
    "contractors": "Adjudicataris",
    "tasks": "Tasques i calendari",
    "favorites": "Favorits",
    "cpv": "Cercador CPV",
    "super_search": "SuperBuscador",
    "docgen": "Generador documental",
    "analyst": "Analista de dades",
    "chat": "Xat",
    "risk_audit": "Auditoria de riscos",
    "compliance": "Revisió legal",
    "plan": "Pla anual",
    "webhooks": "Webhooks sortints",
    "bpm": "Processos BPM",
}

SETTING_KEY = "modules.disabled"

# Prefixos (relatius a /api/v1/) → mòdul. El més específic primer.
_PREFIXES: list[tuple[str, str]] = [
    ("ai/analyses", "analyst"),
    ("minor-contracts", "minor_contracts"),
    ("contractors", "contractors"),
    ("tasks", "tasks"),
    ("folders", "favorites"),
    ("cpv", "cpv"),
    ("public-registry", "super_search"),
    ("doc-projects", "docgen"),
    ("doc-references", "docgen"),
    ("chat", "chat"),
    ("audit", "risk_audit"),  # /audit/red-flags; /audit-log NO hi casa
    ("compliance", "compliance"),
    ("plan", "plan"),
    ("webhooks", "webhooks"),
    ("bpm", "bpm"),
]

_API_ROOT = "/api/v1/"


def module_for_path(path: str) -> str | None:
    """Mòdul que governa una ruta, o None si és del nucli."""
    if not path.startswith(_API_ROOT):
        return None
    relative = path[len(_API_ROOT) :]
    for prefix, module in _PREFIXES:
        if relative == prefix or relative.startswith(prefix + "/"):
            return module
    return None


def parse_disabled(raw: Any) -> frozenset[str]:
    """Valor del setting → conjunt de mòduls coneguts (mai el nucli)."""
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return frozenset()
    if not isinstance(value, list):
        return frozenset()
    return frozenset(str(v) for v in value if str(v) in MODULES)


# Cache curta: una lectura de BD com a molt cada 15 s per procés; el PUT
# del setting la invalida a l'instant al procés de l'API.
_TTL_SECONDS = 15.0
_cache: tuple[float, frozenset[str]] = (0.0, frozenset())


def invalidate_cache() -> None:
    global _cache
    _cache = (0.0, frozenset())


async def disabled_modules() -> frozenset[str]:
    global _cache
    now = time.monotonic()
    stamp, value = _cache
    if stamp and now - stamp < _TTL_SECONDS:
        return value
    from sqlalchemy import select

    from app.core.db import session_factory
    from app.modules.config.models import Setting

    async with session_factory() as session:
        raw = (
            await session.execute(select(Setting.value).where(Setting.key == SETTING_KEY))
        ).scalar_one_or_none()
    value = parse_disabled(raw)
    _cache = (now, value)
    return value
