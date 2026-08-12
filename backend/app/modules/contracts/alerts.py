"""Job alerts.recompute (specs/contract-actions.md).

Alertes de venciment en una sola passada set-based: el descart persistent
(alert_dismissed_end_date == calculated_end_date) inhibeix les dues alertes
mentre la data final no canviï.
"""

from typing import Any

import structlog
from sqlalchemy import bindparam, select, text

from app.core.db import session_factory
from app.jobs.registry import JobContext, job
from app.modules.config.models import Setting

logger = structlog.get_logger()

DEFAULT_WARNING_MONTHS = 6
WARNING_MONTHS_KEY = "contracts.expiry_warning_months"

# «Finalitzat» és l'estat manual de la v2; la resta són estats morts reals
# de la font (verificats a BD).
DEAD_STATUSES = ("Finalitzat", "Anul·lació", "Desert", "Desistiment", "Renúncia")

_RECOMPUTE_SQL = text(
    """
    UPDATE contracts SET
      possibly_finished = (
        status NOT IN :dead
        AND calculated_end_date IS NOT NULL
        AND calculated_end_date < CURRENT_DATE
        AND calculated_end_date IS DISTINCT FROM alert_dismissed_end_date
      ),
      expiry_warning = (
        status NOT IN :dead
        AND calculated_end_date IS NOT NULL
        AND calculated_end_date >= CURRENT_DATE
        AND calculated_end_date <= (
          CURRENT_DATE
          + make_interval(months => COALESCE(warning_months_override, :window))
        )::date
        AND calculated_end_date IS DISTINCT FROM alert_dismissed_end_date
      )
    WHERE possibly_finished IS DISTINCT FROM (
        status NOT IN :dead
        AND calculated_end_date IS NOT NULL
        AND calculated_end_date < CURRENT_DATE
        AND calculated_end_date IS DISTINCT FROM alert_dismissed_end_date
      )
      OR expiry_warning IS DISTINCT FROM (
        status NOT IN :dead
        AND calculated_end_date IS NOT NULL
        AND calculated_end_date >= CURRENT_DATE
        AND calculated_end_date <= (
          CURRENT_DATE
          + make_interval(months => COALESCE(warning_months_override, :window))
        )::date
        AND calculated_end_date IS DISTINCT FROM alert_dismissed_end_date
      )
    """
).bindparams(bindparam("dead", expanding=True))


async def warning_window_months() -> int:
    async with session_factory() as session:
        value = (
            await session.execute(select(Setting.value).where(Setting.key == WARNING_MONTHS_KEY))
        ).scalar_one_or_none()
    try:
        return int(value) if value is not None else DEFAULT_WARNING_MONTHS
    except (TypeError, ValueError):
        return DEFAULT_WARNING_MONTHS


@job("alerts.recompute")
async def recompute_alerts(ctx: JobContext) -> dict[str, Any]:
    window = await warning_window_months()
    async with session_factory() as session:
        result = await session.execute(_RECOMPUTE_SQL, {"dead": DEAD_STATUSES, "window": window})
        changed = int(getattr(result, "rowcount", 0) or 0)
        counts = (
            (
                await session.execute(
                    text(
                        "SELECT count(*) FILTER (WHERE possibly_finished) AS finished, "
                        "count(*) FILTER (WHERE expiry_warning) AS expiring FROM contracts"
                    )
                )
            )
            .mappings()
            .one()
        )
        await session.commit()
    summary = {
        "changed": changed,
        "possibly_finished": counts["finished"],
        "expiry_warning": counts["expiring"],
        "window_months": window,
    }
    logger.info("alerts_recomputed", **summary)
    return summary
