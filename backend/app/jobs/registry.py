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


@dataclass(frozen=True)
class RetryPolicy:
    """Política de reintents per tipus (specs/jobs-queue.md, B-009).

    max_attempts=1 = comportament clàssic (una fallada → failed). Amb més
    intents, la fallada re-encua amb backoff exponencial i, esgotats tots,
    el job passa a l'estat `dead` (safata de morts, re-encuable a mà).
    """

    max_attempts: int = 1
    backoff_seconds: int = 60

    def delay_for(self, attempt: int) -> int:
        return self.backoff_seconds * (2 ** max(0, attempt - 1))


_POLICIES: dict[str, RetryPolicy] = {}

_DEFAULT_POLICY = RetryPolicy()


def job(
    type_name: str, *, max_attempts: int = 1, backoff_seconds: int = 60
) -> Callable[[JobHandler], JobHandler]:
    def register(handler: JobHandler) -> JobHandler:
        if type_name in _REGISTRY:
            raise ValueError(f"Tipus de job duplicat: {type_name}")
        _REGISTRY[type_name] = handler
        _POLICIES[type_name] = RetryPolicy(max_attempts, backoff_seconds)
        return handler

    return register


def get_policy(type_name: str) -> RetryPolicy:
    return _POLICIES.get(type_name, _DEFAULT_POLICY)


def get_handler(type_name: str) -> JobHandler:
    if type_name not in _REGISTRY:
        raise LookupError(f"Tipus de job desconegut: {type_name}")
    return _REGISTRY[type_name]
