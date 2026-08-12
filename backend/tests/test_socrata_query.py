"""Query builder SoQL: validació estricta i escapat (mai concatenació)."""

import pytest

from app.integrations.socrata.query import (
    SoqlQuery,
    SoqlValidationError,
    validate_dataset_id,
    validate_ine10,
)


def test_full_query_params() -> None:
    query = (
        SoqlQuery("ybgg-dgi6")
        .select("codi_expedient", "objecte")
        .where_ine10("codi_ine10", "4305160009")
        .where_gte_timestamp("data_actualitzacio", "2026-01-01T00:00:00")
        .order_by("data_actualitzacio", descending=True)
        .limit(100)
        .offset(200)
    )

    params = query.params()

    assert params["$select"] == "codi_expedient, objecte"
    assert "codi_ine10 = '4305160009'" in params["$where"]
    assert "data_actualitzacio >= '2026-01-01T00:00:00'" in params["$where"]
    assert params["$order"] == "data_actualitzacio DESC"
    assert params["$limit"] == "100"
    assert params["$offset"] == "200"


def test_text_values_are_escaped_inside_literals() -> None:
    # L'intent d'injecció clàssic queda tancat dins del literal.
    query = SoqlQuery("ybgg-dgi6").where_eq("objecte", "x' OR '1'='1")

    assert query.params()["$where"] == "objecte = 'x'' OR ''1''=''1'"


@pytest.mark.parametrize("bad_field", ["objecte; DROP", "a b", "UPPER", "1camp", "camp'", "$where"])
def test_invalid_field_names_rejected(bad_field: str) -> None:
    with pytest.raises(SoqlValidationError):
        SoqlQuery("ybgg-dgi6").where_eq(bad_field, "x")


@pytest.mark.parametrize("bad_dataset", ["ybgg_dgi6", "YBGG-DGI6", "x", "ybgg-dgi6x", "../x"])
def test_invalid_dataset_ids_rejected(bad_dataset: str) -> None:
    with pytest.raises(SoqlValidationError):
        validate_dataset_id(bad_dataset)


@pytest.mark.parametrize("bad_ine", ["123", "43051600091", "4305abc009", "430516000 "])
def test_invalid_ine10_rejected(bad_ine: str) -> None:
    with pytest.raises(SoqlValidationError):
        validate_ine10(bad_ine)


def test_invalid_dates_and_numbers_rejected() -> None:
    with pytest.raises(SoqlValidationError):
        SoqlQuery("ybgg-dgi6").where_gte_timestamp("data", "ahir a la tarda")
    with pytest.raises(SoqlValidationError):
        SoqlQuery("ybgg-dgi6").where_gte_number("import", "1;2")
