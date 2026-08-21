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
    # Indicadors de venciment (expiry_warning/possibly_finished): diaris i
    # també al final de la cadena nocturna. Sense això no es calculaven mai
    # (el job existia sense cap productor — es va veure a producció com a
    # «cap contracte amb fi propera» després de la primera càrrega).
    ScheduledJob(
        job_type="alerts.recompute",
        interval_seconds=86400,
        dedup_key="alerts.recompute",
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
    # Retenció de dades (B-006): purga diària d'auditoria i IA caducades,
    # amb terminis configurables per settings (indicacions del DPO).
    ScheduledJob(
        job_type="retention.purge",
        interval_seconds=86400,
        dedup_key="retention.purge",
    ),
    # Purga d'índexs temporals de projectes del generador: diària.
    ScheduledJob(
        job_type="docgen.purge_expired",
        interval_seconds=86400,
        dedup_key="docgen.purge_expired",
    ),
    # L'informe d'auditoria NO és aquí: és programable i desactivat de
    # sèrie (settings reports.audit_*; vegeu scheduler._tick_reports).
    # Reintents de deliveries pendents (l'emissió ja encua un dispatch).
    ScheduledJob(
        job_type="webhooks.dispatch",
        interval_seconds=300,
        dedup_key="webhooks.dispatch",
    ),
    # Estat del sistema (B-022): healthchecks dels connectors habilitats i
    # mesura de l'storage — el que no pot anar dins d'una request.
    ScheduledJob(
        job_type="system.status_snapshot",
        interval_seconds=900,
        dedup_key="system.status_snapshot",
    ),
]
