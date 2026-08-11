"""trace_id per petició: als logs, a les respostes d'error i a l'auditoria."""

import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    trace_id = uuid.uuid4().hex
    _trace_id.set(trace_id)
    return trace_id


def current_trace_id() -> str | None:
    return _trace_id.get()
