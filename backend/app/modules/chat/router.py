"""Xat general i per expedient (specs/chat.md, B-016).

Propietat estricta per usuari (404, mai 403 que confirmi existència);
abast departamental aplicat al contracte en crear el fil i a cada stream.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import analyst_agent, chat_agent, providers
from app.core import authz
from app.core.db import get_session
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.chat.models import ChatMessage, ChatRole, ChatScope, ChatThread
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["chat"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
UseDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("tools:use"))]

_HISTORY_LIMIT = 20  # torns previs que veu el model


class ThreadBody(BaseModel):
    scope: Literal["general", "contract"]
    contract_id: int | None = None


class ThreadResponse(BaseModel):
    id: int
    scope: str
    contract_id: int | None
    title: str | None
    updated_at: datetime


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: list[Any] | None = None
    created_at: datetime


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    # Acota el xat d'expedient a UN document (specs/chat.md); ignorat al general.
    document_id: int | None = Field(default=None, ge=1)


async def _own_thread(session: AsyncSession, thread_id: int, user_id: int) -> ChatThread:
    thread = (
        await session.execute(
            select(ChatThread).where(ChatThread.id == thread_id, ChatThread.user_id == user_id)
        )
    ).scalar_one_or_none()
    if thread is None:
        raise Problem(404, "Conversa desconeguda", "not-found")
    return thread


async def _check_contract_access(
    session: AsyncSession, contract_id: int, authz_ctx: authz.AuthzContext
) -> None:
    """Abast departamental també al xat: contracte no visible → 404."""
    if authz.evaluate(authz_ctx.user, "contracts:read") is None:
        raise Problem(404, "Contracte desconegut", "not-found")
    from app.modules.contracts import service as contracts_service

    await contracts_service.get_scoped_contract(
        session, contract_id, authz_ctx.user, authz_ctx.scope
    )


def _require_general_access(authz_ctx: authz.AuthzContext) -> None:
    if authz.evaluate(authz_ctx.user, "audit:run") is None:
        raise Problem(403, "Cal permís d'anàlisi per al xat general", "forbidden")


@router.get("/chat/threads", operation_id="listChatThreads")
async def list_threads(
    session: SessionDep,
    authz_ctx: UseDep,
    scope: Annotated[str | None, Query(pattern="^(general|contract)$")] = None,
    contract_id: Annotated[int | None, Query(ge=1)] = None,
) -> dict[str, list[ThreadResponse]]:
    stmt = select(ChatThread).where(ChatThread.user_id == authz_ctx.user.id)
    if scope:
        stmt = stmt.where(ChatThread.scope == ChatScope(scope))
    if contract_id:
        stmt = stmt.where(ChatThread.contract_id == contract_id)
    threads = (
        (await session.execute(stmt.order_by(ChatThread.updated_at.desc()).limit(100)))
        .scalars()
        .all()
    )
    return {
        "data": [ThreadResponse.model_validate(t, from_attributes=True) for t in threads]
    }


@router.post("/chat/threads", operation_id="createChatThread", status_code=201)
async def create_thread(
    body: ThreadBody, session: SessionDep, authz_ctx: UseDep, ctx: ContextDep
) -> ThreadResponse:
    if body.scope == "contract":
        if body.contract_id is None:
            raise Problem(422, "Cal contract_id per a un xat d'expedient", "validation")
        await _check_contract_access(session, body.contract_id, authz_ctx)
    else:
        _require_general_access(authz_ctx)
    thread = ChatThread(
        user_id=authz_ctx.user.id,
        scope=ChatScope(body.scope),
        contract_id=body.contract_id if body.scope == "contract" else None,
    )
    session.add(thread)
    await session.flush()
    await record_audit(
        session, actor_type=AuditActorType.USER, action="chat.thread_created", success=True,
        actor_id=authz_ctx.user.id, resource_type="chat", resource_id=str(thread.id),
        ip=ctx.ip, user_agent=ctx.user_agent, trace_id=ctx.trace_id,
    )
    await session.commit()
    return ThreadResponse.model_validate(thread, from_attributes=True)


@router.get("/chat/threads/{id}", operation_id="getChatThread")
async def get_thread(
    id: int, session: SessionDep, authz_ctx: UseDep
) -> dict[str, Any]:
    thread = await _own_thread(session, id, authz_ctx.user.id)
    messages = (
        (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.thread_id == thread.id)
                .order_by(ChatMessage.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "thread": ThreadResponse.model_validate(thread, from_attributes=True),
        "messages": [
            MessageResponse.model_validate(m, from_attributes=True) for m in messages
        ],
    }


@router.delete("/chat/threads/{id}", operation_id="deleteChatThread", status_code=204)
async def delete_thread(
    id: int, session: SessionDep, authz_ctx: UseDep, ctx: ContextDep
) -> None:
    thread = await _own_thread(session, id, authz_ctx.user.id)
    await session.delete(thread)
    await record_audit(
        session, actor_type=AuditActorType.USER, action="chat.thread_deleted", success=True,
        actor_id=authz_ctx.user.id, resource_type="chat", resource_id=str(id),
        ip=ctx.ip, user_agent=ctx.user_agent, trace_id=ctx.trace_id,
    )
    await session.commit()


@router.post("/chat/threads/{id}/messages/stream", operation_id="streamChatMessage")
async def stream_message(
    id: int, body: MessageBody, session: SessionDep, authz_ctx: UseDep, ctx: ContextDep
) -> StreamingResponse:
    thread = await _own_thread(session, id, authz_ctx.user.id)
    if thread.scope == ChatScope.CONTRACT:
        if thread.contract_id is None:  # defensa: mai hauria de passar
            raise Problem(409, "Fil d'expedient sense contracte", "conflict")
        await _check_contract_access(session, thread.contract_id, authz_ctx)
    else:
        _require_general_access(authz_ctx)

    history_rows = (
        (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.thread_id == thread.id)
                .order_by(ChatMessage.id.desc())
                .limit(_HISTORY_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    history = [
        {"role": m.role.value, "content": m.content} for m in reversed(history_rows)
    ]

    def line(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str) + "\n"

    async def generate():
        collected: list[str] = []
        sources: list[Any] | None = None
        try:
            if thread.scope == ChatScope.CONTRACT:
                events = chat_agent.contract_chat_events(
                    session, thread.contract_id or 0, body.content,
                    history=history, document_id=body.document_id,
                    user_id=authz_ctx.user.id, trace_id=ctx.trace_id,
                )
            else:
                events = analyst_agent.answer_events(
                    session, body.content,
                    history=history, user_id=authz_ctx.user.id, trace_id=ctx.trace_id,
                )
            async for event in events:
                if event["type"] == "delta":
                    collected.append(str(event["text"]))
                elif event["type"] == "sources":
                    sources = event["sources"]
                if event["type"] != "done":
                    yield line(event)

            # Persistència del parell pregunta/resposta al final de l'stream.
            session.add(
                ChatMessage(thread_id=thread.id, role=ChatRole.USER, content=body.content)
            )
            session.add(
                ChatMessage(
                    thread_id=thread.id,
                    role=ChatRole.ASSISTANT,
                    content="".join(collected),
                    sources=sources,
                )
            )
            if not thread.title:
                thread.title = body.content[:200]
            thread.updated_at = datetime.now(UTC)
            await record_audit(
                session, actor_type=AuditActorType.USER, action="chat.message", success=True,
                actor_id=authz_ctx.user.id, resource_type="chat", resource_id=str(thread.id),
                ip=ctx.ip, user_agent=ctx.user_agent, trace_id=ctx.trace_id,
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
