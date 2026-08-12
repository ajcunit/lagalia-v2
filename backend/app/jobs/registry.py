"""Registre de handlers de jobs.

Cada tipus de job registra una coroutine que rep un JobContext.
El runner s'encarrega de la resta (estats, progrés, esdeveniments).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class JobContext:
    job_id: uuid.UUID
    payload: dict[str, Any] | None
    set_progress: Callable[[int, str | None], Awaitable[None]]


JobHandler = Callable[[JobContext], Awaitable[dict[str, Any] | None]]

_REGISTRY: dict[str, JobHandler] = {}


def job(type_name: str) -> Callable[[JobHandler], JobHandler]:
    def register(handler: JobHandler) -> JobHandler:
        if type_name in _REGISTRY:
            raise ValueError(f"Tipus de job duplicat: {type_name}")
        _REGISTRY[type_name] = handler
        return handler

    return register


def get_handler(type_name: str) -> JobHandler:
    if type_name not in _REGISTRY:
        raise LookupError(f"Tipus de job desconegut: {type_name}")
    return _REGISTRY[type_name]
