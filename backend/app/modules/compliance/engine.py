"""Motor de regles LCSP determinista (specs/compliance-rules.md; 07 §2.4.1).

Regles versionades per data d'efecte; cada una referencia l'article.
Sense LLM: sempre exacte i auditable.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

# Llindars del contracte menor (art. 118 LCSP, vigents des de l'entrada en
# vigor de la Llei 9/2017 el 2018-03-09). Quan la norma canviï, s'afegeix una
# versió nova amb effective_from i es conserva l'antiga per a expedients vells.
_LCSP_EFFECTIVE = date(2018, 3, 9)


@dataclass(frozen=True)
class RuleVersion:
    rule_id: str
    article: str
    effective_from: date
    effective_to: date | None
    params: dict[str, Any]
    description: str


RULES: list[RuleVersion] = [
    RuleVersion(
        rule_id="minor.amount",
        article="LCSP art. 118.1",
        effective_from=_LCSP_EFFECTIVE,
        effective_to=None,
        params={"works": 40000, "other": 15000},
        description="Import màxim del contracte menor (sense IVA): 40.000 € obres, "
        "15.000 € serveis i subministraments.",
    ),
    RuleVersion(
        rule_id="minor.duration",
        article="LCSP art. 29.8",
        effective_from=_LCSP_EFFECTIVE,
        effective_to=None,
        params={"max_years": 1},
        description="El contracte menor no pot durar més d'un any ni prorrogar-se.",
    ),
    RuleVersion(
        rule_id="contract.minor_procedure_amount",
        article="LCSP art. 118.1",
        effective_from=_LCSP_EFFECTIVE,
        effective_to=None,
        params={"works": 40000, "other": 15000},
        description="Un expedient tramitat com a menor no pot superar el llindar "
        "del seu tipus.",
    ),
    RuleVersion(
        rule_id="plan.minor_over_threshold",
        article="LCSP art. 118.1",
        effective_from=_LCSP_EFFECTIVE,
        effective_to=None,
        params={"works": 40000, "other": 15000},
        description="Entrada del pla anual amb import estimat sobre el llindar del "
        "menor: caldrà procediment amb publicitat.",
    ),
]


def rule_for(rule_id: str, when: date) -> RuleVersion | None:
    for version in RULES:
        if (
            version.rule_id == rule_id
            and version.effective_from <= when
            and (version.effective_to is None or when < version.effective_to)
        ):
            return version
    return None


def _is_works(contract_type: str | None) -> bool:
    return "obr" in (contract_type or "").lower()


def _threshold(version: RuleVersion, contract_type: str | None) -> Decimal:
    key = "works" if _is_works(contract_type) else "other"
    return Decimal(str(version.params[key]))


def _finding(
    version: RuleVersion, status: str, detail: str
) -> dict[str, Any]:
    return {
        "rule_id": version.rule_id,
        "article": version.article,
        "status": status,  # conforme | avis | no_conforme | no_verificable
        "detail": detail,
    }


def check_minor(
    *, contract_type: str | None, award_amount: Decimal | None,
    duration_years: int | None, duration_months: int | None,
    when: date,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    amount_rule = rule_for("minor.amount", when)
    if amount_rule:
        if award_amount is None:
            findings.append(_finding(amount_rule, "no_verificable", "sense import d'adjudicació"))
        else:
            threshold = _threshold(amount_rule, contract_type)
            if award_amount > threshold:
                findings.append(
                    _finding(
                        amount_rule,
                        "no_conforme",
                        f"import {award_amount} € sobre el llindar de {threshold} € del menor",
                    )
                )
            else:
                findings.append(
                    _finding(amount_rule, "conforme", f"dins del llindar ({threshold} €)")
                )
    duration_rule = rule_for("minor.duration", when)
    if duration_rule:
        months = (duration_years or 0) * 12 + (duration_months or 0)
        if duration_years is None and duration_months is None:
            findings.append(_finding(duration_rule, "no_verificable", "sense durada informada"))
        elif months > duration_rule.params["max_years"] * 12:
            findings.append(
                _finding(duration_rule, "no_conforme", f"durada de {months} mesos (màxim 12)")
            )
        else:
            findings.append(_finding(duration_rule, "conforme", f"durada de {months} mesos"))
    return findings


def check_contract(
    *, procedure: str | None, contract_type: str | None,
    award_amount: Decimal | None, when: date,
) -> list[dict[str, Any]]:
    version = rule_for("contract.minor_procedure_amount", when)
    if version is None:
        return []
    if "menor" not in (procedure or "").lower():
        return [_finding(version, "conforme", "no és un procediment menor")]
    if award_amount is None:
        return [_finding(version, "no_verificable", "sense import d'adjudicació")]
    threshold = _threshold(version, contract_type)
    if award_amount > threshold:
        return [
            _finding(
                version,
                "no_conforme",
                f"procediment menor amb {award_amount} € (llindar {threshold} €)",
            )
        ]
    return [_finding(version, "conforme", f"dins del llindar ({threshold} €)")]


def check_plan_entry(
    *, contract_type: str | None, estimated_amount: Decimal | None, fiscal_year: int,
) -> list[dict[str, Any]]:
    version = rule_for("plan.minor_over_threshold", date(fiscal_year, 1, 1))
    if version is None:
        return []
    if estimated_amount is None:
        return [_finding(version, "no_verificable", "sense import estimat")]
    threshold = _threshold(version, contract_type)
    if estimated_amount > threshold:
        return [
            _finding(
                version,
                "avis",
                f"import estimat {estimated_amount} € sobre el llindar del menor "
                f"({threshold} €): caldrà procediment amb publicitat",
            )
        ]
    return [_finding(version, "conforme", f"dins del llindar del menor ({threshold} €)")]


def worst_status(findings: list[dict[str, Any]]) -> str:
    order = ["no_conforme", "avis", "no_verificable", "conforme"]
    for status in order:
        if any(f["status"] == status for f in findings):
            return status
    return "conforme"
