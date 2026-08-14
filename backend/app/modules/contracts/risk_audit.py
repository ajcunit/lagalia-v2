"""Red flags d'auditoria de contractació (specs/risk-audit.md).

Només lectura sobre la BD local; llindars de 02 §2.12.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.contractors.models import Contractor
from app.modules.contracts.models import Contract
from app.modules.minor_contracts.models import MinorContract
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["audit"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
RunDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("audit:run"))]

_LIMIT = 50
_SPLIT_THRESHOLD = Decimal("15000")


async def _splitting(session: AsyncSession, today: date) -> dict[str, Any]:
    """Adjudicataris amb ≥15.000 € en menors en 365 dies.

    El dataset de menors és una fila agregada per adjudicatari i any
    (liquidacions): el «≥2 contractes» de la v1 no hi aplica; el senyal
    és la suma (vegeu specs/risk-audit.md).
    """
    since = today - timedelta(days=365)
    base = (
        select(
            MinorContract.contractor_id,
            func.count().label("contracts"),
            func.sum(MinorContract.award_amount).label("total"),
        )
        .where(
            MinorContract.contractor_id.is_not(None),
            MinorContract.award_date >= since,
            MinorContract.award_amount.is_not(None),
        )
        .group_by(MinorContract.contractor_id)
        .having(func.sum(MinorContract.award_amount) >= _SPLIT_THRESHOLD)
        .subquery()
    )
    total = (await session.execute(select(func.count()).select_from(base))).scalar_one()
    rows = (
        await session.execute(
            select(base, Contractor.canonical_name, Contractor.tax_id)
            .join(Contractor, Contractor.id == base.c.contractor_id)
            .order_by(base.c.total.desc())
            .limit(_LIMIT)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {
                "contractor_id": r.contractor_id,
                "contractor_name": r.canonical_name,
                "nif": r.tax_id,
                "contracts": r.contracts,
                "amount": r.total,
            }
            for r in rows
        ],
    }


async def _reckless_bids(session: AsyncSession) -> dict[str, Any]:
    """award ≤ 80% del pressupost sense IVA."""
    conditions = and_(
        Contract.award_amount.is_not(None),
        Contract.budget_no_vat.is_not(None),
        Contract.award_amount > 0,
        Contract.budget_no_vat > 0,
        Contract.award_amount <= Contract.budget_no_vat * Decimal("0.80"),
    )
    total = (
        await session.execute(select(func.count()).select_from(Contract).where(conditions))
    ).scalar_one()
    drop = (1 - Contract.award_amount / Contract.budget_no_vat) * 100
    rows = (
        await session.execute(
            select(Contract.id, Contract.file_code, Contract.subject, Contract.award_amount,
                   Contract.budget_no_vat, drop.label("drop_pct"))
            .where(conditions)
            .order_by(drop.desc())
            .limit(_LIMIT)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {
                "contract_id": r.id,
                "file_code": r.file_code,
                "subject": r.subject,
                "award_amount": r.award_amount,
                "budget_no_vat": r.budget_no_vat,
                "drop_pct": round(r.drop_pct, 1),
            }
            for r in rows
        ],
    }


async def _critical_renewals(session: AsyncSession, today: date) -> dict[str, Any]:
    """Fi calculada dins de 6 mesos i no finalitzat."""
    horizon = today + timedelta(days=182)
    conditions = and_(
        Contract.calculated_end_date.is_not(None),
        Contract.calculated_end_date >= today,
        Contract.calculated_end_date <= horizon,
        # En execució: el tall per dates ja ho implica; s'exclouen anul·lats.
        func.lower(Contract.status).not_like("%anul%"),
    )
    total = (
        await session.execute(select(func.count()).select_from(Contract).where(conditions))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Contract.id, Contract.file_code, Contract.subject,
                   Contract.calculated_end_date, Contract.award_amount)
            .where(conditions)
            .order_by(Contract.calculated_end_date)
            .limit(_LIMIT)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {
                "contract_id": r.id,
                "file_code": r.file_code,
                "subject": r.subject,
                "end_date": r.calculated_end_date,
                "award_amount": r.award_amount,
            }
            for r in rows
        ],
    }


async def _single_bidder(session: AsyncSession) -> dict[str, Any]:
    """Procediment competitiu amb una sola oferta (nova v2)."""
    conditions = and_(
        Contract.received_offers == 1,
        Contract.procedure.is_not(None),
        func.lower(Contract.procedure).not_like("%menor%"),
        func.lower(Contract.procedure).not_like("%sense publicitat%"),
    )
    total = (
        await session.execute(select(func.count()).select_from(Contract).where(conditions))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Contract.id, Contract.file_code, Contract.subject, Contract.procedure,
                   Contract.award_amount)
            .where(conditions)
            .order_by(Contract.award_amount.desc().nulls_last())
            .limit(_LIMIT)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {
                "contract_id": r.id,
                "file_code": r.file_code,
                "subject": r.subject,
                "procedure": r.procedure,
                "award_amount": r.award_amount,
            }
            for r in rows
        ],
    }


@router.get("/audit/red-flags", operation_id="getRedFlags")
async def get_red_flags(
    session: SessionDep, authz_ctx: RunDep, ctx: ContextDep
) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    result = {
        "splitting": await _splitting(session, today),
        "reckless_bids": await _reckless_bids(session),
        "critical_renewals": await _critical_renewals(session, today),
        "single_bidder": await _single_bidder(session),
    }
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action="audit.red_flags_run",
        success=True,
        actor_id=authz_ctx.user.id,
        resource_type="audit",
        resource_id="red-flags",
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    return result
