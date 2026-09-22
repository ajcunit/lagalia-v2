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
from app.modules.bpm.router import router as bpm_router
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
from app.modules.help.router import router as help_router
from app.modules.minor_contracts.router import router as minor_contracts_router
from app.modules.plan.router import router as plan_router
from app.modules.public_registry.router import router as public_registry_router
from app.modules.service_accounts.router import router as service_accounts_router
from app.modules.setup.router import router as setup_router
from app.modules.sync.router import router as sync_router
from app.modules.system.router import router as system_router
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

# CORS només si s'han declarat orígens: amb el desplegament estàndard la SPA
# i l'API comparteixen origen (el proxy serveix totes dues) i no cal. Es
# configura per als casos en què el navegador ataca l'API des d'un altre
# origen (docs/06-seguretat.md §5). Mai "*": la validació de config ho
# rebutja perquè s'envien credencials.
if settings.cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Trace-Id"],
    )


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


@app.middleware("http")
async def track_api_usage(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Comptadors d'ús (specs/usage-tracking.md, B-010): per plantilla de
    ruta resolta, mai el path cru. Un error de Redis no trenca la request."""
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", None)
    if isinstance(route, str) and request.url.path.startswith("/api/"):
        from app.core.usage import record_request

        # El path de la ruta inclosa via include_router NO porta el prefix
        # /api/v1 (la declarada directament sí): es normalitza sense prefix.
        await record_request(
            request.method,
            route.removeprefix("/api/v1"),
            response.status_code,
            getattr(request.state, "user_id", None),
        )
    return response


@app.middleware("http")
async def enforce_module_flags(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Mòduls activables (specs/module-flags.md): un sol punt de tall."""
    from app.core import modules as module_flags
    from app.core.problems import _problem_response

    module = module_flags.module_for_path(request.url.path)
    if module is not None and module in await module_flags.disabled_modules():
        return _problem_response(
            403,
            f"El mòdul «{module_flags.MODULES[module]}» està desactivat",
            "module-disabled",
        )
    return await call_next(request)


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
api.include_router(system_router)
api.include_router(bpm_router)
api.include_router(public_registry_router)
api.include_router(favorites_router)
api.include_router(help_router)
api.include_router(risk_audit_router)
api.include_router(cpv_router)
api.include_router(plan_router)
api.include_router(ai_router)
api.include_router(compliance_router)
api.include_router(chat_router)
api.include_router(docgen_router)
app.include_router(api)
