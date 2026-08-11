from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI

from app.core.config import settings
from app.core.logging import configure_logging

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

api = APIRouter(prefix="/api/v1")


@api.get("/health", tags=["system"], operation_id="getHealth")
def get_health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


app.include_router(api)
