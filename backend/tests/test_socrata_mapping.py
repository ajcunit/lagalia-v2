"""Mapper A1: unitats pures (sense BD ni xarxa)."""

from datetime import date

import pytest

from app.integrations.socrata import mapping
from app.integrations.socrata.mapping import add_months, map_contract, parse_duration


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("12", 12),
        (24, 24),
        ("1 anys 0 mesos 0 dies", 12),
        ("2 anys 3 mesos 0 dies", 27),
        ("0 anys 6 mesos 20 dies", 7),  # dies > 15 → +1 mes
        ("0 anys 0 mesos 10 dies", None),  # total 0 → null
        ("0", None),
        ("sense format", None),
    ],
)
def test_parse_duration(value: object, expected: int | None) -> None:
    assert parse_duration(value) == expected


def test_add_months_end_of_month() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # traspàs
    assert add_months(date(2026, 11, 15), 2) == date(2027, 1, 15)


def test_status_fallback_first_non_empty() -> None:
    assert map_contract({"resultat": "Formalitzat"})["status"] == "Formalitzat"
    assert map_contract({"fase_publicacio": "Licitació"})["status"] == "Licitació"
    assert map_contract({"resultat": "", "fase_publicacio": "Licitació"})["status"] == "Licitació"


def test_calculated_dates_require_formalization_and_duration() -> None:
    base = {
        "data_formalitzacio_contracte": "2026-01-15",
        "durada_contracte": "12",
    }

    mapped = map_contract(base)
    assert mapped["start_date"] == date(2026, 1, 16)
    assert mapped["end_date"] == date(2027, 1, 16)
    assert mapped["calculated_end_date"] == date(2027, 1, 16)

    # Sense durada (o sense formalització): tot nul.
    assert map_contract({"data_formalitzacio_contracte": "2026-01-15"})["end_date"] is None
    assert map_contract({"durada_contracte": "12"})["start_date"] is None


def test_url_or_object_fields_normalized() -> None:
    mapped = map_contract(
        {
            "enllac_publicacio": {"url": "https://exemple.cat/anunci"},
            "url_json_licitacio": "https://exemple.cat/licitacio.json",
            "url_json_adjudicacio": {"url": "https://exemple.cat/adjudicacio.json"},
        }
    )

    assert mapped["links"]["enllac_publicacio"] == "https://exemple.cat/anunci"
    assert mapped["phase_urls"]["licitacio"] == "https://exemple.cat/licitacio.json"
    assert mapped["phase_urls"]["adjudicacio"] == "https://exemple.cat/adjudicacio.json"


def test_amounts_and_duplicity_resolution() -> None:
    mapped = map_contract(
        {
            "valor_estimat_contracte": "100000.50",
            "import_adjudicacio_sense": "90000",
            "import_adjudicacio_amb_iva": "108900",
        }
    )

    assert str(mapped["tender_amount"]) == "100000.50"
    assert str(mapped["award_amount"]) == "90000"
    assert str(mapped["award_amount_vat"]) == "108900"
    # La duplicitat v1 es descarta: cap altre camp rep import_adjudicacio_sense.


def test_content_hash_is_stable_and_sensitive() -> None:
    record = {"codi_expedient": "X1", "objecte_contracte": "Neteja"}

    assert mapping.content_hash(record) == mapping.content_hash(dict(record))
    assert mapping.content_hash(record) != mapping.content_hash(
        {**record, "objecte_contracte": "Neteja viària"}
    )


def test_awarding_fields_mapped() -> None:
    mapped = map_contract({"nom_organ": "Junta de Govern", "departament_adjudicador": "Urbanisme"})

    assert mapped["awarding_body"] == "Junta de Govern"
    assert mapped["awarding_department"] == "Urbanisme"
