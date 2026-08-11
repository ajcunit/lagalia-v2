"""Endpoints públics de setup. Prims: la lògica és al servei."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.ratelimit import enforce_rate_limit
from app.modules.setup import service
from app.modules.setup.schemas import (
    InitializeRequest,
    InitializeResponse,
    SetupStatusResponse,
)
from app.modules.users.dependencies import get_request_context
from app.modules.users.schemas import UserResponse
from app.modules.users.service import RequestContext

router = APIRouter(tags=["setup"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]

# Rate limit estricte (el contracte l'exigeix): 3 intents/hora per IP.
_SETUP_LIMIT = (3, 3600)


@router.get("/setup/status", operation_id="getSetupStatus")
async def get_setup_status(session: SessionDep) -> SetupStatusResponse:
    return SetupStatusResponse(needs_setup=await service.needs_setup(session))


@router.post("/setup/initialize", operation_id="initializeSystem", status_code=201)
async def initialize_system(
    body: InitializeRequest, session: SessionDep, ctx: ContextDep
) -> InitializeResponse:
    await enforce_rate_limit("setup", ctx.ip or "unknown", *_SETUP_LIMIT)
    admin = await service.initialize(session, body, ctx)
    return InitializeResponse(user=UserResponse.from_user(admin))
