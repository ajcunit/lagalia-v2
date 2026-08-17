"""Revisió de compliment LCSP (specs/compliance-rules.md).

Determinista i auditable: persisteix cada revisió a compliance_reviews.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import legal_corpus, providers
from app.core import authz
from app.core.db import get_session
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.compliance import engine
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["compliance"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
RunDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("compliance:run"))]


class CheckBody(BaseModel):
    subject_type: Literal["contract", "minor_contract", "plan_entry"]
    subject_id: int


class PlanCheckBody(BaseModel):
    fiscal_year: int = Field(ge=2000, le=2100)


async def _persist(
    session: AsyncSession,
    subject_type: str,
    subject_id: int,
    findings: list[dict[str, Any]],
    user_id: int,
) -> str:
    status = engine.worst_status(findings)
    import json as _json

    await session.execute(
        text(
            "INSERT INTO compliance_reviews (subject_type, subject_id, status, findings, "
            "created_by) VALUES (:t, :i, :s, CAST(:f AS jsonb), :u)"
        ),
        {"t": subject_type, "i": subject_id, "s": status, "f": _json.dumps(findings), "u": user_id},
    )
    return status


async def _check_subject(
    session: AsyncSession, subject_type: str, subject_id: int
) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    if subject_type == "minor_contract":
        row = (
            await session.execute(
                text(
                    "SELECT contract_type, award_amount, award_date, duration_years, "
                    "duration_months FROM minor_contracts WHERE id = :id"
                ),
                {"id": subject_id},
            )
        ).first()
        if row is None:
            raise Problem(404, "Contracte menor desconegut", "not-found")
        return engine.check_minor(
            contract_type=row.contract_type,
            award_amount=row.award_amount,
            duration_years=row.duration_years,
            duration_months=row.duration_months,
            when=row.award_date or today,
        )
    if subject_type == "contract":
        row = (
            await session.execute(
                text(
                    "SELECT procedure, contract_type, award_amount, published_at "
                    "FROM contracts WHERE id = :id"
                ),
                {"id": subject_id},
            )
        ).first()
        if row is None:
            raise Problem(404, "Contracte desconegut", "not-found")
        return engine.check_contract(
            procedure=row.procedure,
            contract_type=row.contract_type,
            award_amount=row.award_amount,
            when=row.published_at.date() if row.published_at else today,
        )
    row = (
        await session.execute(
            text(
                "SELECT contract_type, estimated_amount, fiscal_year "
                "FROM plan_entries WHERE id = :id"
            ),
            {"id": subject_id},
        )
    ).first()
    if row is None:
        raise Problem(404, "Entrada de pla desconeguda", "not-found")
    return engine.check_plan_entry(
        contract_type=row.contract_type,
        estimated_amount=row.estimated_amount,
        fiscal_year=row.fiscal_year,
    )


class ReviewTextBody(BaseModel):
    text: str = Field(min_length=50, max_length=40000)
    subject_type: Literal["contract", "minor_contract", "plan_entry", "document"] = "document"
    subject_id: int | None = None


def _legal_review_response(
    session: AsyncSession,
    document_text: str,
    *,
    subject_type: str,
    subject_id: int | None,
    authz_ctx: authz.AuthzContext,
    ctx: RequestContext,
    audit_action: str,
) -> StreamingResponse:
    """Capa 2: revisió LLM amb RAG normatiu en streaming, persistida i auditada."""
    import json as _json

    def line(payload: dict[str, Any]) -> str:
        return _json.dumps(payload, ensure_ascii=False, default=str) + "\n"

    async def generate():
        collected: list[str] = []
        articles: list[dict[str, Any]] = []
        try:
            async for event in legal_corpus.review_text_events(
                session, document_text, user_id=authz_ctx.user.id, trace_id=ctx.trace_id
            ):
                if event["type"] == "delta":
                    collected.append(str(event["text"]))
                elif event["type"] == "articles":
                    articles = event["articles"]
                yield line(event)
            findings = [
                {
                    "rule_id": "legal.llm_review",
                    "article": ", ".join(a["article"] for a in articles[:3]) or "—",
                    "status": "avis",
                    "detail": "".join(collected)[:4000],
                }
            ]
            await _persist(session, subject_type, subject_id or 0, findings, authz_ctx.user.id)
            await record_audit(
                session, actor_type=AuditActorType.USER, action=audit_action,
                success=True, actor_id=authz_ctx.user.id, resource_type=subject_type,
                resource_id=str(subject_id or ""), ip=ctx.ip, user_agent=ctx.user_agent,
                trace_id=ctx.trace_id,
            )
            await session.commit()
            yield line({"type": "done"})
        except providers.ProviderError as exc:
            yield line({"type": "error", "detail": str(exc)})
        except Problem as exc:
            yield line({"type": "error", "detail": exc.title})

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/compliance/review-text", operation_id="reviewTextCompliance")
async def review_text(
    body: ReviewTextBody, session: SessionDep, authz_ctx: RunDep, ctx: ContextDep
) -> StreamingResponse:
    return _legal_review_response(
        session, body.text,
        subject_type=body.subject_type, subject_id=body.subject_id,
        authz_ctx=authz_ctx, ctx=ctx, audit_action="compliance.review_text",
    )


@router.post(
    "/compliance/documents/{document_id}/review/stream",
    operation_id="reviewDocumentCompliance",
)
async def review_document(
    document_id: int, session: SessionDep, authz_ctx: RunDep, ctx: ContextDep
) -> StreamingResponse:
    """Revisió legal de qualsevol document del repositori (phase_documents).

    Cal la còpia local de l'object storage (la deixa la indexació RAG): se
    n'extreu el text i es revisa amb el mateix flux que review-text.
    """
    row = (
        await session.execute(
            text(
                "SELECT contract_id, storage_key FROM phase_documents WHERE id = :id"
            ),
            {"id": document_id},
        )
    ).first()
    if row is None:
        raise Problem(404, "Document desconegut", "not-found")
    # Abast departamental també als subrecursos (06 §3): 404 si el contracte
    # pare no és visible per a l'usuari.
    from app.modules.contracts import service as contracts_service

    await contracts_service.get_scoped_contract(
        session, row.contract_id, authz_ctx.user, authz_ctx.scope
    )
    if row.storage_key is None:
        raise Problem(
            409,
            "Aquest document no té còpia local: indexa'l primer des d'IA → RAG",
            "conflict",
        )
    import asyncio as _asyncio

    from app.ai import rag
    from app.core.storage import get_storage

    try:
        content = await get_storage().get(row.storage_key)
    except Exception as exc:
        raise Problem(409, "La còpia local del document no està disponible", "conflict") from exc
    extracted = await _asyncio.to_thread(rag.extract_text, content)
    if len(extracted.strip()) < 50:
        raise Problem(422, "El document no conté text extraïble", "validation")
    return _legal_review_response(
        session, extracted,
        subject_type="document", subject_id=document_id,
        authz_ctx=authz_ctx, ctx=ctx, audit_action="compliance.review_document",
    )


@router.get("/compliance/rules", operation_id="listComplianceRules")
async def list_rules(_authz: RunDep) -> dict[str, list[dict[str, Any]]]:
    return {
        "data": [
            {
                "rule_id": v.rule_id,
                "article": v.article,
                "effective_from": v.effective_from.isoformat(),
                "effective_to": v.effective_to.isoformat() if v.effective_to else None,
                "params": v.params,
                "description": v.description,
            }
            for v in engine.RULES
        ]
    }


@router.post("/compliance/check", operation_id="runComplianceCheck")
async def run_check(
    body: CheckBody, session: SessionDep, authz_ctx: RunDep, ctx: ContextDep
) -> dict[str, Any]:
    findings = await _check_subject(session, body.subject_type, body.subject_id)
    status = await _persist(
        session, body.subject_type, body.subject_id, findings, authz_ctx.user.id
    )
    await record_audit(
        session, actor_type=AuditActorType.USER, action="compliance.check", success=True,
        actor_id=authz_ctx.user.id, resource_type=body.subject_type,
        resource_id=str(body.subject_id), ip=ctx.ip, user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )
    await session.commit()
    return {"status": status, "findings": findings}


@router.post("/compliance/check-plan", operation_id="runPlanComplianceCheck")
async def run_plan_check(
    body: PlanCheckBody, session: SessionDep, authz_ctx: RunDep, ctx: ContextDep
) -> dict[str, list[dict[str, Any]]]:
    """Batch sobre el pla de l'exercici (l'exemple del roadmap F3)."""
    entries = (
        await session.execute(
            text(
                "SELECT id, subject, quarter, contract_type, estimated_amount, fiscal_year "
                "FROM plan_entries WHERE fiscal_year = :y ORDER BY quarter, id"
            ),
            {"y": body.fiscal_year},
        )
    ).all()
    results = []
    for entry in entries:
        findings = engine.check_plan_entry(
            contract_type=entry.contract_type,
            estimated_amount=entry.estimated_amount,
            fiscal_year=entry.fiscal_year,
        )
        status = await _persist(session, "plan_entry", entry.id, findings, authz_ctx.user.id)
        results.append(
            {
                "entry_id": entry.id,
                "subject": entry.subject,
                "quarter": entry.quarter,
                "status": status,
                "findings": findings,
            }
        )
    await record_audit(
        session, actor_type=AuditActorType.USER, action="compliance.check_plan", success=True,
        actor_id=authz_ctx.user.id, resource_type="plan", resource_id=str(body.fiscal_year),
        ip=ctx.ip, user_agent=ctx.user_agent, trace_id=ctx.trace_id,
    )
    await session.commit()
    return {"data": results}
