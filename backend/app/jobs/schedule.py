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
]
