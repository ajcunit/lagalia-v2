"""Extracció dels JSON de fase de contractaciopublica.cat.

Esquema real fixat a specs/pscp-enrichment.md (fixtures reals als tests).
Multiidioma sempre ca→es→en; documents i mesa per extracció recursiva.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

DOWNLOAD_PATH = "/portal-api/descarrega-document/{id}/{hash}"


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
    """Primer valor escalar el camí del qual conté `needle` (case-insensitive)."""
    needle = needle.lower()
    for path, value in _walk(data):
        if needle in path.lower() and value not in (None, "", {}):
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
                visit(value, key if isinstance(value, (dict, list)) else doc_type)
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


def _first_lot(phase: dict[str, Any]) -> dict[str, Any]:
    lots = phase.get("publicacio", {}).get("dadesPublicacioLot") or []
    return lots[0] if lots and isinstance(lots[0], dict) else {}


def extract_scalars(phase_name: str, phase: dict[str, Any]) -> dict[str, Any]:
    """Escalars promocionats + resum per a contracts.enrichment."""
    publicacio = phase.get("publicacio", {})
    dades = publicacio.get("dadesPublicacio") or {}
    lot = _first_lot(phase)

    scalars: dict[str, Any] = {}
    if phase_name == "licitacio":
        scalars["is_harmonized"] = dades.get("contracteHarmonitzat")
        scalars["allows_extensions"] = dades.get("preveuenProrroguesAlsPlecs")
        scalars["allows_modifications"] = dades.get("preveuenModificacionsAlsPlecs")
        scalars["social_reserve"] = (
            bool(lot.get("reservaSocial")) if lot.get("reservaSocial") is not None else None
        )
        scalars["definitive_guarantee"] = ml(lot.get("garantiaDefinitiva"))
        scalars["place_of_execution"] = ml(lot.get("llocExecucio"))
    if phase_name in ("adjudicacio", "formalitzacio"):
        scalars["award_amount"] = lot.get("importAdjudicacio")
        scalars["award_date"] = lot.get("dataAdjudicacio")
        winners = lot.get("empresesAdjudicataries") or []
        if winners and isinstance(winners[0], dict):
            scalars["winner_name"] = ml(winners[0].get("denominacio")) or winners[0].get(
                "denominacio"
            )
            scalars["winner_tax_id"] = winners[0].get("identificador")
        scalars["appeal_notice"] = ml(lot.get("peuDeRecurs"))
    offers = _find_scalar(phase, "nombreofertes")
    if offers is not None:
        try:
            scalars["received_offers"] = int(offers)
        except (TypeError, ValueError):
            pass
    return {key: value for key, value in scalars.items() if value is not None}
