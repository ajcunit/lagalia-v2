"""Mapeig Socrata → model v2 (transcripció de l'annex A1).

L'annex és l'especificació camp a camp; qualsevol desviació s'hi anota.
Els camps font d'aquest mòdul són els VALORS PER DEFECTE: es poden
sobreescriure per pantalla i queden persistits a `field_mappings`
(specs/field-mapping.md); els consumidors passen `overrides` a
`map_contract`/`contractor_fields`.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

_YEARS_RE = re.compile(r"(\d+)\s*any")
_MONTHS_RE = re.compile(r"(\d+)\s*mes")
_DAYS_RE = re.compile(r"(\d+)\s*di")
_RANGE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})")


@dataclass(frozen=True)
class FieldDef:
    """Un camp de destí mapejable: font per defecte (A1), tipus i etiqueta UI."""

    source: str
    kind: str  # text | amount | date | datetime | duration
    label: str


# Camps de `contracts` amb mapeig 1:1 sobreescrivible. Els compostos o
# d'identitat (file_code/status/lot, links, phase_urls, inici/fi calculats,
# content_hash, raw) NO són mapejables i queden al codi.
MAPPABLE_FIELDS: dict[str, FieldDef] = {
    "ine10_code": FieldDef("codi_ine10", "text", "Codi INE10"),
    "dir3_code": FieldDef("codi_dir3", "text", "Codi DIR3"),
    "subject": FieldDef("objecte_contracte", "text", "Objecte"),
    "contract_type": FieldDef("tipus_contracte", "text", "Tipus de contracte"),
    "procedure": FieldDef("procediment", "text", "Procediment"),
    "processing_type": FieldDef("tipus_tramitacio", "text", "Tipus de tramitació"),
    "awarding_body": FieldDef("nom_organ", "text", "Òrgan adjudicador"),
    "awarding_department": FieldDef(
        "departament_adjudicador", "text", "Departament adjudicador"
    ),
    "tender_amount": FieldDef("valor_estimat_contracte", "amount", "Valor estimat (contracte)"),
    "award_amount": FieldDef("import_adjudicacio_sense", "amount", "Import adjudicació"),
    "award_amount_vat": FieldDef(
        "import_adjudicacio_amb_iva", "amount", "Import adjudicació (IVA)"
    ),
    "estimated_value": FieldDef("valor_estimat_expedient", "amount", "Valor estimat (expedient)"),
    "budget_no_vat": FieldDef("pressupost_licitacio_sense", "amount", "Pressupost sense IVA"),
    "budget_vat": FieldDef("pressupost_licitacio_amb", "amount", "Pressupost amb IVA"),
    "published_at": FieldDef("data_publicacio_anunci", "datetime", "Publicació"),
    "updated_at_source": FieldDef("data_actualitzacio", "datetime", "Actualització a la font"),
    "formalized_at": FieldDef("data_formalitzacio_contracte", "date", "Formalització"),
    "prior_notice_date": FieldDef("data_anunci_previ", "date", "Anunci previ"),
    "tender_notice_date": FieldDef("data_anunci_licitacio", "date", "Anunci de licitació"),
    "award_notice_date": FieldDef("data_adjudicacio_contracte", "date", "Adjudicació"),
    "formalization_notice_date": FieldDef(
        "data_anunci_formalitzacio", "date", "Anunci de formalització"
    ),
    "cancellation_date": FieldDef("data_publicacio_anul", "date", "Anul·lació"),
    "duration_months": FieldDef("durada_contracte", "duration", "Durada (mesos o rang)"),
    "cpv_code": FieldDef("codi_cpv", "text", "Codi CPV"),
    "cpv_description": FieldDef("cpv_principal_descripcio", "text", "Descripció CPV"),
    "nuts_code": FieldDef("codi_nuts", "text", "Codi NUTS"),
    "nuts_description": FieldDef("descripcio_nuts", "text", "Descripció NUTS"),
    "financing": FieldDef("forma_financament", "text", "Finançament"),
}

# Camps del contractista (resolts pel servei de contractors).
CONTRACTOR_FIELDS: dict[str, FieldDef] = {
    "contractor.name": FieldDef("denominacio_adjudicatari", "text", "Adjudicatari (nom)"),
    "contractor.tax_id": FieldDef("identificacio_adjudicatari", "text", "Adjudicatari (NIF)"),
    "contractor.nationality": FieldDef(
        "adjudicatari_nacionalitat", "text", "Adjudicatari (nacionalitat)"
    ),
}

PHASE_URL_KEYS = (
    "futura",
    "agregada",
    "cpm",
    "previ",
    "licitacio",
    "avaluacio",
    "adjudicacio",
    "formalitzacio",
    "anulacio",
)

LINK_KEYS = (
    "enllac_publicacio",
    "enllac_anunci_previ",
    "enllac_licitacio",
    "enllac_adjudicacio",
    "enllac_formalitzacio",
    "enllac_perfil_contractant",
    "url_plataforma_contractacio",
)


def parse_duration_range(value: Any) -> tuple[date, date] | None:
    """A1 §3 (ampliació 2026-08-17): «dd/mm/aaaa a dd/mm/aaaa» → (inici, fi)."""
    if value is None:
        return None
    match = _RANGE_RE.search(str(value))
    if match is None:
        return None
    try:
        start = datetime.strptime(match.group(1), "%d/%m/%Y").date()
        end = datetime.strptime(match.group(2), "%d/%m/%Y").date()
    except ValueError:
        return None
    if end < start:
        return None
    return start, end


def months_between(start: date, end: date) -> int | None:
    """Mesos entre dues dates; la fracció ≥ 15 dies compta com a mes."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day - start.day >= 15:
        months += 1
    elif start.day - end.day >= 16:
        months -= 1
    return months or None


def parse_duration(value: Any) -> int | None:
    """Durada en mesos (A1 §3): número directe o text 'X anys Y mesos Z dies'."""
    if value is None:
        return None
    try:
        total = int(float(str(value)))
        return total or None
    except ValueError:
        pass
    text_value = str(value)
    years = int(m.group(1)) if (m := _YEARS_RE.search(text_value)) else 0
    months = int(m.group(1)) if (m := _MONTHS_RE.search(text_value)) else 0
    days = int(m.group(1)) if (m := _DAYS_RE.search(text_value)) else 0
    total = years * 12 + months + (1 if days > 15 else 0)
    return total or None


def add_months(day: date, months: int) -> date:
    """Suma de mesos naturals amb ajust de final de mes."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = [31, 29 if _leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(day.day, last_day[month - 1]))


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _url_value(value: Any) -> str | None:
    """A1 §4: pot arribar string o objecte {'url': ...}; sempre string."""
    if value is None:
        return None
    if isinstance(value, dict):
        url = value.get("url")
        return str(url) if url else None
    return str(value)


def _text(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _amount(record: dict[str, Any], key: str) -> Decimal | None:
    value = record.get(key)
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _date(record: dict[str, Any], key: str) -> date | None:
    value = _text(record, key)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _datetime(record: dict[str, Any], key: str) -> datetime | None:
    value = _text(record, key)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def content_hash(record: dict[str, Any]) -> str:
    """SHA-256 del JSON canònic (v1 feia MD5 del JSON ordenat)."""
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


_KIND_PARSERS = {
    "text": _text,
    "amount": _amount,
    "date": _date,
    "datetime": _datetime,
}


def map_contract(
    record: dict[str, Any], overrides: dict[str, str] | None = None
) -> dict[str, Any]:
    """Valors de columna de `contracts` segons A1 (sense l'adjudicatari,
    que resol el servei de contractors). `overrides` = camp font manual
    per destí (field_mappings)."""
    effective = overrides or {}

    def src(target: str) -> str:
        return effective.get(target) or MAPPABLE_FIELDS[target].source

    values: dict[str, Any] = {}
    for target, definition in MAPPABLE_FIELDS.items():
        if definition.kind == "duration":
            continue  # es tracta a part (rang o número)
        values[target] = _KIND_PARSERS[definition.kind](record, src(target))

    duration_raw = record.get(src("duration_months"))
    duration_range = parse_duration_range(duration_raw)
    formalized_at = values["formalized_at"]
    if duration_range is not None:
        # A1 §3 (ampliació): el rang mana sobre el càlcul formalització+durada.
        start_date, end_date = duration_range
        duration_months = months_between(start_date, end_date)
    else:
        duration_months = parse_duration(duration_raw)
        start_date = end_date = None
        if formalized_at and duration_months:
            # A1 §3: només si hi ha formalització I durada.
            start_date = formalized_at + timedelta(days=1)
            end_date = add_months(formalized_at, duration_months) + timedelta(days=1)

    links = {key: _url_value(record.get(key)) for key in LINK_KEYS if record.get(key)}
    phase_urls = {
        key: _url_value(record.get(f"url_json_{key}"))
        for key in PHASE_URL_KEYS
        if record.get(f"url_json_{key}")
    }

    return {
        # Identitat (no mapejable: defineix la unicitat de la fila)
        "file_code": _text(record, "codi_expedient") or "",
        "status": _text(record, "resultat") or _text(record, "fase_publicacio") or "",
        "lot": _text(record, "numero_lot") or "",
        # Camps mapejables (A1 per defecte + overrides)
        **values,
        # Calculats
        "start_date": start_date,
        "end_date": end_date,
        "calculated_end_date": end_date,
        "duration_months": duration_months,
        # Agrupacions
        "links": links or None,
        "phase_urls": phase_urls or None,
        # Control
        "content_hash": content_hash(record),
        "raw": record,
    }


def contractor_fields(
    record: dict[str, Any], overrides: dict[str, str] | None = None
) -> dict[str, str | None]:
    effective = overrides or {}

    def src(target: str) -> str:
        return effective.get(target) or CONTRACTOR_FIELDS[target].source

    return {
        "name": _text(record, src("contractor.name")),
        "tax_id": _text(record, src("contractor.tax_id")),
        "nationality": _text(record, src("contractor.nationality")),
    }
