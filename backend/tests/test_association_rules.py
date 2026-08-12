"""Motor de regles d'associació: tots els operadors (unitats pures)."""

from decimal import Decimal

import pytest

from app.modules.contracts.models import AssociationRule, RuleOperator, RuleType
from app.modules.contracts.rules import first_matching_department


def _rule(
    *,
    department_id: int,
    field: str,
    operator: RuleOperator,
    value: str,
    priority: int = 100,
) -> AssociationRule:
    return AssociationRule(
        department_id=department_id,
        rule_type=RuleType.KEYWORD,
        source_field=field,
        match_value=value,
        operator=operator,
        priority=priority,
        active=True,
    )


@pytest.mark.parametrize(
    ("operator", "match_value", "actual", "matches"),
    [
        (RuleOperator.EQUALS, "Urbanisme", "urbanisme", True),
        (RuleOperator.EQUALS, "Urbanisme", "Urbanisme i Obres", False),
        (RuleOperator.CONTAINS, "neteja", "Servei de NETEJA viària", True),
        (RuleOperator.CONTAINS, "neteja", "Jardineria", False),
        (RuleOperator.STARTS_WITH, "servei", "SERVEI de manteniment", True),
        (RuleOperator.STARTS_WITH, "servei", "El servei", False),
    ],
)
def test_text_operators_case_insensitive(
    operator: RuleOperator, match_value: str, actual: str, matches: bool
) -> None:
    rule = _rule(department_id=7, field="subject", operator=operator, value=match_value)

    result = first_matching_department([rule], {"subject": actual})

    assert (result == 7) is matches


@pytest.mark.parametrize(
    ("operator", "threshold", "amount", "matches"),
    [
        (RuleOperator.GT, "15000", Decimal("15000.01"), True),
        (RuleOperator.GT, "15000", Decimal("15000"), False),
        (RuleOperator.LT, "15000", Decimal("14999.99"), True),
        (RuleOperator.LT, "15000", Decimal("15000"), False),
    ],
)
def test_numeric_operators(
    operator: RuleOperator, threshold: str, amount: Decimal, matches: bool
) -> None:
    rule = _rule(department_id=3, field="award_amount", operator=operator, value=threshold)

    result = first_matching_department([rule], {"award_amount": amount})

    assert (result == 3) is matches


def test_first_match_wins_by_order() -> None:
    rules = [
        _rule(
            department_id=1,
            field="subject",
            operator=RuleOperator.CONTAINS,
            value="neteja",
            priority=200,
        ),
        _rule(
            department_id=2,
            field="subject",
            operator=RuleOperator.CONTAINS,
            value="servei",
            priority=100,
        ),
    ]

    # Casa amb totes dues; guanya la primera (més prioritat).
    assert first_matching_department(rules, {"subject": "Servei de neteja"}) == 1


def test_unknown_field_and_missing_value_never_match() -> None:
    bad_field = _rule(
        department_id=1, field="camp_inventat", operator=RuleOperator.EQUALS, value="x"
    )
    missing = _rule(
        department_id=2, field="cpv_code", operator=RuleOperator.EQUALS, value="90610000"
    )

    assert first_matching_department([bad_field, missing], {"subject": "x"}) is None
