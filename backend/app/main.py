from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request, Response

from app.ai.router import router as ai_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.problems import register_problem_handlers
from app.core.tracing import new_trace_id
from app.jobs import tasks as _jobs_tasks  # noqa: F401 — registra els handlers
from app.jobs.router import router as jobs_router
from app.modules.audit.router import router as audit_router
from app.modules.chat.router import router as chat_router
from app.modules.compliance.router import router as compliance_router
from app.modules.config.router import router as config_router
from app.modules.contractors.router import router as contractors_router
from app.modules.contracts.cpv import router as cpv_router
from app.modules.contracts.risk_audit import router as risk_audit_router
from app.modules.contracts.router import router as contracts_router
from app.modules.departments.router import router as departments_router
from app.modules.docgen.router import router as docgen_router
from app.modules.favorites.router import router as favorites_router
from app.modules.minor_contracts.router import router as minor_contracts_router
from app.modules.plan.router import router as plan_router
from app.modules.public_registry.router import router as public_registry_router
from app.modules.service_accounts.router import router as service_accounts_router
from app.modules.setup.router import router as setup_router
from app.modules.sync.router import router as sync_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_router
from app.modules.webhooks.router import router as webhooks_router

configure_logging(settings.log_level, settings.log_format)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("startup", environment=settings.environment, version=settings.app_version)
    yield
    logger.info("shutdown")


app = FastAPI(
    title="LAGALia — Gestió de contractació pública",
    version=settings.app_version,
    description="API de la plataforma de gestió de contractació pública de l'Ajuntament de Cunit.",
    lifespan=lifespan,
)

register_problem_handlers(app)


@app.middleware("http")
async def trace_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    trace_id = new_trace_id()
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.unbind_contextvars("trace_id")
    response.headers["X-Trace-Id"] = trace_id
    return response


api = APIRouter(prefix="/api/v1")


@api.get("/health", tags=["system"], operation_id="getHealth")
def get_health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


api.include_router(users_router)
api.include_router(departments_router)
api.include_router(setup_router)
api.include_router(jobs_router)
api.include_router(contracts_router)
api.include_router(minor_contracts_router)
api.include_router(contractors_router)
api.include_router(tasks_router)
api.include_router(webhooks_router)
api.include_router(service_accounts_router)
api.include_router(config_router)
api.include_router(audit_router)
api.include_router(sync_router)
api.include_router(public_registry_router)
api.include_router(favorites_router)
api.include_router(risk_audit_router)
api.include_router(cpv_router)
api.include_router(plan_router)
api.include_router(ai_router)
api.include_router(compliance_router)
api.include_router(chat_router)
api.include_router(docgen_router)
app.include_router(api)
