"""Mapeig Socrata → model v2 (transcripció de l'annex A1).

L'annex és l'especificació camp a camp; qualsevol desviació s'hi anota.
"""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

_YEARS_RE = re.compile(r"(\d+)\s*any")
_MONTHS_RE = re.compile(r"(\d+)\s*mes")
_DAYS_RE = re.compile(r"(\d+)\s*di")

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


def map_contract(record: dict[str, Any]) -> dict[str, Any]:
    """Valors de columna de `contracts` segons A1 (sense l'adjudicatari,
    que resol el servei de contractors)."""
    duration_months = parse_duration(record.get("durada_contracte"))
    formalized_at = _date(record, "data_formalitzacio_contracte")

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
        # Identitat
        "file_code": _text(record, "codi_expedient") or "",
        "status": _text(record, "resultat") or _text(record, "fase_publicacio") or "",
        "lot": _text(record, "numero_lot") or "",
        "ine10_code": _text(record, "codi_ine10"),
        "dir3_code": _text(record, "codi_dir3"),
        # Bàsics
        "subject": _text(record, "objecte_contracte"),
        "contract_type": _text(record, "tipus_contracte"),
        "procedure": _text(record, "procediment"),
        "processing_type": _text(record, "tipus_tramitacio"),
        "awarding_body": _text(record, "nom_organ"),
        "awarding_department": _text(record, "departament_adjudicador"),
        # Imports (la duplicitat v1 d'import_adjudicacio_sense es descarta)
        "tender_amount": _amount(record, "valor_estimat_contracte"),
        "award_amount": _amount(record, "import_adjudicacio_sense"),
        "award_amount_vat": _amount(record, "import_adjudicacio_amb_iva"),
        "estimated_value": _amount(record, "valor_estimat_expedient"),
        "budget_no_vat": _amount(record, "pressupost_licitacio_sense"),
        "budget_vat": _amount(record, "pressupost_licitacio_amb"),
        # Dates
        "published_at": _datetime(record, "data_publicacio_anunci"),
        "updated_at_source": _datetime(record, "data_actualitzacio"),
        "formalized_at": formalized_at,
        "start_date": start_date,
        "end_date": end_date,
        "calculated_end_date": end_date,
        "prior_notice_date": _date(record, "data_anunci_previ"),
        "tender_notice_date": _date(record, "data_anunci_licitacio"),
        "award_notice_date": _date(record, "data_adjudicacio_contracte"),
        "formalization_notice_date": _date(record, "data_anunci_formalitzacio"),
        "cancellation_date": _date(record, "data_publicacio_anul"),
        # Durada
        "duration_months": duration_months,
        # Classificació
        "cpv_code": _text(record, "codi_cpv"),
        "cpv_description": _text(record, "cpv_principal_descripcio"),
        "nuts_code": _text(record, "codi_nuts"),
        "nuts_description": _text(record, "descripcio_nuts"),
        "financing": _text(record, "forma_financament"),
        # Agrupacions
        "links": links or None,
        "phase_urls": phase_urls or None,
        # Control
        "content_hash": content_hash(record),
        "raw": record,
    }


def contractor_fields(record: dict[str, Any]) -> dict[str, str | None]:
    return {
        "name": _text(record, "denominacio_adjudicatari"),
        "tax_id": _text(record, "identificacio_adjudicatari"),
        "nationality": _text(record, "adjudicatari_nacionalitat"),
    }
