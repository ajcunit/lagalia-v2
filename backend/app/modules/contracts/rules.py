"""Motor de regles d'associació automàtica de departaments (A1 §8).

La v2 implementa TOTS els operadors declarats al model (el ⚠️ de l'annex):
equals, contains i starts_with (case-insensitive) i gt/lt (numèrics).
Regles actives per prioritat descendent; la primera que casa assigna.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contracts.models import AssociationRule, RuleOperator

# Camps del contracte que una regla pot avaluar.
EVALUABLE_FIELDS = frozenset(
    {
        "awarding_department",
        "awarding_body",
        "subject",
        "cpv_code",
        "award_amount",
        "tender_amount",
        "budget_no_vat",
    }
)


def _matches(rule: AssociationRule, values: dict[str, Any]) -> bool:
    if rule.source_field not in EVALUABLE_FIELDS:
        return False
    actual = values.get(rule.source_field)
    if actual is None:
        return False

    if rule.operator in (RuleOperator.GT, RuleOperator.LT):
        try:
            actual_number = Decimal(str(actual))
            expected_number = Decimal(rule.match_value)
        except InvalidOperation:
            return False
        if rule.operator == RuleOperator.GT:
            return actual_number > expected_number
        return actual_number < expected_number

    actual_text = str(actual).casefold()
    expected_text = rule.match_value.casefold()
    if rule.operator == RuleOperator.EQUALS:
        return actual_text == expected_text
    if rule.operator == RuleOperator.CONTAINS:
        return expected_text in actual_text
    if rule.operator == RuleOperator.STARTS_WITH:
        return actual_text.startswith(expected_text)
    return False


def first_matching_department(rules: list[AssociationRule], values: dict[str, Any]) -> int | None:
    """Primera regla que casa (ja ordenades per prioritat desc) → departament."""
    for rule in rules:
        if _matches(rule, values):
            return rule.department_id
    return None


async def load_active_rules(session: AsyncSession) -> list[AssociationRule]:
    result = await session.execute(
        select(AssociationRule)
        .where(AssociationRule.active.is_(True))
        .order_by(AssociationRule.priority.desc(), AssociationRule.id.asc())
    )
    return list(result.scalars())
