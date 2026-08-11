"""Errors HTTP segons RFC 9457 (application/problem+json).

Mai s'hi inclou el cos de la petició original (prohibició explícita del
projecte): els errors de validació només informen del camp i el motiu.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.tracing import current_trace_id

_TYPE_BASE = "https://lagalia/errors/"

MEDIA_TYPE = "application/problem+json"


class Problem(Exception):
    def __init__(
        self,
        status_code: int,
        title: str,
        error_type: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.title = title
        self.error_type = error_type
        self.detail = detail
        self.headers = headers or {}


def _problem_response(
    status_code: int,
    title: str,
    error_type: str,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": _TYPE_BASE + error_type,
        "title": title,
        "status": status_code,
    }
    if detail:
        body["detail"] = detail
    if trace_id := current_trace_id():
        body["trace_id"] = trace_id
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status_code, headers=headers, media_type=MEDIA_TYPE)


def unauthorized(detail: str | None = None) -> Problem:
    return Problem(
        status.HTTP_401_UNAUTHORIZED,
        "Cal autenticar-se o la sessió ha caducat",
        "unauthorized",
        detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def register_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def handle_problem(_request: Request, exc: Problem) -> JSONResponse:
        return _problem_response(
            exc.status_code, exc.title, exc.error_type, exc.detail, exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem_response(
            exc.status_code,
            str(exc.detail),
            "http",
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Només camp i motiu; mai el valor rebut (exclòs amb 'input').
        errors = [
            {
                "loc": [str(part) for part in err.get("loc", [])],
                "msg": err.get("msg"),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        return _problem_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Dades no vàlides",
            "validation",
            extra={"errors": errors},
        )
