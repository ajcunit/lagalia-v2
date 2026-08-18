"""Extracció dels JSON de fase de contractaciopublica.cat.

Esquema real fixat a specs/pscp-enrichment.md (fixtures reals als tests).
Multiidioma sempre ca→es→en; documents i mesa per extracció recursiva.
Els camins dels escalars són els VALORS PER DEFECTE: sobreescrivibles per
pantalla i persistits a `field_mappings` (specs/field-mapping.md).
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

DOWNLOAD_PATH = "/portal-api/descarrega-document/{id}/{hash}"


@dataclass(frozen=True)
class PscpField:
    """Escalar promocionat des del JSON de fase: camí per defecte, tipus,
    etiqueta i fases on aplica. Un camí «~text» és cerca heurística (el
    primer valor el camí del qual conté el text)."""

    path: str
    kind: str  # raw | text | amount | bool | int
    label: str
    phases: tuple[str, ...]


_LOT = "publicacio.dadesPublicacioLot[0]"
_DADES = "publicacio.dadesPublicacio"
_AWARD_PHASES = ("adjudicacio", "formalitzacio")

PSCP_FIELDS: dict[str, PscpField] = {
    "is_harmonized": PscpField(
        f"{_DADES}.contracteHarmonitzat", "raw", "Contracte harmonitzat", ("licitacio",)
    ),
    "allows_extensions": PscpField(
        f"{_DADES}.preveuenProrroguesAlsPlecs", "raw", "Preveu pròrrogues", ("licitacio",)
    ),
    "allows_modifications": PscpField(
        f"{_DADES}.preveuenModificacionsAlsPlecs", "raw", "Preveu modificacions", ("licitacio",)
    ),
    "social_reserve": PscpField(
        f"{_LOT}.reservaSocial", "bool", "Reserva social", ("licitacio",)
    ),
    "definitive_guarantee": PscpField(
        f"{_LOT}.garantiaDefinitiva", "text", "Garantia definitiva", ("licitacio",)
    ),
    "place_of_execution": PscpField(
        f"{_LOT}.llocExecucio", "text", "Lloc d'execució", ("licitacio",)
    ),
    "award_amount": PscpField(
        f"{_LOT}.importAdjudicacio", "raw", "Import d'adjudicació", _AWARD_PHASES
    ),
    "award_date": PscpField(
        f"{_LOT}.dataAdjudicacio", "raw", "Data d'adjudicació", _AWARD_PHASES
    ),
    "winner_name": PscpField(
        f"{_LOT}.empresesAdjudicataries[0].denominacio", "text", "Adjudicatari", _AWARD_PHASES
    ),
    "winner_tax_id": PscpField(
        f"{_LOT}.empresesAdjudicataries[0].identificador",
        "raw",
        "Adjudicatari (NIF)",
        _AWARD_PHASES,
    ),
    "appeal_notice": PscpField(f"{_LOT}.peuDeRecurs", "text", "Peu de recurs", _AWARD_PHASES),
    "received_offers": PscpField(
        # El portal usa totes dues variants segons la fase/l'antiguitat.
        "~ofertesrebudes|nombreofertes",
        "int",
        "Ofertes rebudes",
        ("licitacio", "avaluacio", "adjudicacio", "formalitzacio"),
    ),
}

_LANG_KEYS = {"ca", "es", "en", "oc"}

_PATH_TOKEN = re.compile(r"([a-zA-Z0-9_]+)|\[(\d+)\]")


def path_get(data: Any, path: str) -> Any:
    """Valor d'un camí «a.b[0].c» dins del JSON; None si no existeix."""
    node = data
    for match in _PATH_TOKEN.finditer(path):
        key, index = match.group(1), match.group(2)
        if key is not None:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        else:
            if not isinstance(node, list) or int(index) >= len(node):
                return None
            node = node[int(index)]
        if node is None:
            return None
    return node


def flatten_paths(data: Any, *, max_entries: int = 400) -> dict[str, Any]:
    """Aplana el JSON de fase a {camí: valor escalar} per a la UI del mapejador."""
    flattened: dict[str, Any] = {}
    for path, value in _walk(data):
        if len(flattened) >= max_entries:
            break
        flattened[path.lstrip(".")] = value
    return flattened


def ml(value: Any) -> str | None:
    """Text multiidioma ca→es→en (08 §2.2); també catàlegs {id, ca…}."""
    if value is None:
        return None
    if isinstance(value, dict):
        for lang in ("ca", "es", "en"):
            text = value.get(lang)
            if isinstance(text, str) and text.strip():
                return text.strip()
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _walk(node: Any, path: str = "") -> Any:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")
    else:
        yield path, node


def _find_scalar(data: Any, needle: str) -> Any:
    """Primer valor escalar el camí del qual conté `needle` (case-insensitive).

    Accepta alternatives separades per «|»: es prova cada agulla en ordre.
    """
    for candidate in needle.lower().split("|"):
        for path, value in _walk(data):
            if candidate in path.lower() and value not in (None, "", {}):
                return value
    return None


def collect_documents(data: Any, base_url: str) -> list[dict[str, Any]]:
    """Documents descarregables: objectes {id, titol, hash} a qualsevol nivell."""
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(node: Any, doc_type: str) -> None:
        if isinstance(node, dict):
            if (
                isinstance(node.get("id"), int)
                and isinstance(node.get("titol"), str)
                and isinstance(node.get("hash"), str)
            ):
                source_doc_id = str(node["id"])
                if source_doc_id not in seen:
                    seen.add(source_doc_id)
                    size = str(node.get("mida", ""))
                    documents.append(
                        {
                            "source_doc_id": source_doc_id,
                            "title": node["titol"][:500],
                            "doc_type": doc_type[:100],
                            "size": int(size) if size.isdigit() else None,
                            "download_url": base_url
                            + DOWNLOAD_PATH.format(id=node["id"], hash=node["hash"]),
                        }
                    )
                return
            for key, value in node.items():
                # Les claus d'idioma (ca/es/en/oc) agrupen variants del mateix
                # document: no canvien el tipus (abans tot quedava com a «ca»).
                next_type = doc_type
                if isinstance(value, (dict, list)) and key not in _LANG_KEYS:
                    next_type = key
                visit(value, next_type)
        elif isinstance(node, list):
            for value in node:
                visit(value, doc_type)

    visit(data, "document")
    return documents


def collect_committee(data: Any) -> list[dict[str, str | None]]:
    """Membres de mesa: {nom, cognoms, carrec} NOMÉS sota claus amb «mesa»."""
    members: list[dict[str, str | None]] = []

    def visit(node: Any, inside_mesa: bool) -> None:
        if isinstance(node, dict):
            if inside_mesa and ("nom" in node or "cognoms" in node) and "carrec" in node:
                members.append(
                    {
                        "first_name": ml(node.get("nom")),
                        "last_name": ml(node.get("cognoms") or node.get("cognom")),
                        "role": ml(node.get("carrec")),
                    }
                )
                return
            for key, value in node.items():
                visit(value, inside_mesa or "mesa" in key.lower())
        elif isinstance(node, list):
            for value in node:
                visit(value, inside_mesa)

    visit(data, False)
    return members


def collect_criteria(data: Any) -> list[dict[str, Any]]:
    """criterisAdjudicacio dels lots (posició, nom, ponderació, desglossament)."""
    criteria: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "criterisAdjudicacio" and isinstance(value, list):
                    for entry in value:
                        if not isinstance(entry, dict):
                            continue
                        name = (
                            ml(entry.get("criteri"))
                            or ml(entry.get("denominacio"))
                            or ml(entry.get("descripcio"))
                            or ml(entry.get("nom"))
                        )
                        if not name:
                            continue
                        criteria.append(
                            {
                                "name": name,
                                "weight": _decimal(entry.get("ponderacio") or entry.get("pes")),
                                "breakdown": entry,
                            }
                        )
                else:
                    visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(data)
    for position, entry in enumerate(criteria, start=1):
        entry["position"] = position
    return criteria


def _convert(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "text":
        return ml(value) or (str(value) if not isinstance(value, (dict, list)) else None)
    if kind == "amount":
        return _decimal(value)
    if kind == "bool":
        return bool(value)
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return value  # raw


def extract_scalars(
    phase_name: str, phase: dict[str, Any], overrides: dict[str, str] | None = None
) -> dict[str, Any]:
    """Escalars promocionats + resum per a contracts.enrichment.

    Els camins per defecte són a PSCP_FIELDS; `overrides` (field_mappings,
    font «pscp») hi mana. Un camí «~text» fa cerca heurística.
    """
    effective = overrides or {}
    scalars: dict[str, Any] = {}
    for target, definition in PSCP_FIELDS.items():
        if phase_name not in definition.phases:
            continue
        path = effective.get(target) or definition.path
        raw_value = (
            _find_scalar(phase, path[1:]) if path.startswith("~") else path_get(phase, path)
        )
        value = _convert(raw_value, definition.kind)
        if value is not None:
            scalars[target] = value
    return scalars
