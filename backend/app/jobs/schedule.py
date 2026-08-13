"""Definicions periòdiques. Fase 0: només el heartbeat de la maquinària."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledJob:
    job_type: str
    interval_seconds: int
    dedup_key: str


SCHEDULE: list[ScheduledJob] = [
    ScheduledJob(
        job_type="system.heartbeat",
        interval_seconds=300,
        dedup_key="system.heartbeat",
    ),
    # Recordatoris de tasques: horari, idempotent (sent_at + dedupe diari).
    ScheduledJob(
        job_type="tasks.reminders",
        interval_seconds=3600,
        dedup_key="tasks.reminders",
    ),
    # Reintents de deliveries pendents (l'emissió ja encua un dispatch).
    ScheduledJob(
        job_type="webhooks.dispatch",
        interval_seconds=300,
        dedup_key="webhooks.dispatch",
    ),
]
