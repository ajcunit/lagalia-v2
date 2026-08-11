"""Logs estructurats amb structlog.

En producció s'emet JSON (una línia per esdeveniment); en desenvolupament,
sortida llegible per consola. Mai s'hi escriuen secrets ni cossos de petició.
"""

import logging
import sys

import structlog


def configure_logging(log_level: str, log_format: str) -> None:
    renderer: structlog.typing.Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        stream=sys.stdout,
        level=log_level.upper(),
        format="%(message)s",
    )
