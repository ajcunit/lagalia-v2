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
    # Escombrat de jobs estancats (B-009): allibera dedup_keys bloquejats.
    ScheduledJob(
        job_type="jobs.sweep",
        interval_seconds=900,
        dedup_key="jobs.sweep",
    ),
    # Recordatoris de tasques: horari, idempotent (sent_at + dedupe diari).
    ScheduledJob(
        job_type="tasks.reminders",
        interval_seconds=3600,
        dedup_key="tasks.reminders",
    ),
    # Vigilància de consolidació del BOE: diària (08 §3).
    ScheduledJob(
        job_type="sync.boe_norms",
        interval_seconds=86400,
        dedup_key="sync.boe_norms",
    ),
    # Purga d'índexs temporals de projectes del generador: diària.
    ScheduledJob(
        job_type="docgen.purge_expired",
        interval_seconds=86400,
        dedup_key="docgen.purge_expired",
    ),
    # Informe d'auditoria per a Intervenció: mensual (30 dies).
    ScheduledJob(
        job_type="reports.audit_monthly",
        interval_seconds=30 * 86400,
        dedup_key="reports.audit_monthly",
    ),
    # Reintents de deliveries pendents (l'emissió ja encua un dispatch).
    ScheduledJob(
        job_type="webhooks.dispatch",
        interval_seconds=300,
        dedup_key="webhooks.dispatch",
    ),
]
