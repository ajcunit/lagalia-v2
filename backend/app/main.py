from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request, Response

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.problems import register_problem_handlers
from app.core.tracing import new_trace_id
from app.jobs import tasks as _jobs_tasks  # noqa: F401 — registra els handlers
from app.jobs.router import router as jobs_router
from app.modules.departments.router import router as departments_router
from app.modules.setup.router import router as setup_router
from app.modules.users.router import router as users_router

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
app.include_router(api)
