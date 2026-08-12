import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.jobs.models import Job, JobStatus


class JobResponse(BaseModel):
    id: uuid.UUID
    type: str
    status: JobStatus
    progress: int
    progress_message: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        # Mai el payload: només estat, progrés i resultat.
        return cls(
            id=job.id,
            type=job.type,
            status=job.status,
            progress=job.progress,
            progress_message=job.progress_message,
            result=job.result,
            error=job.error,
            attempts=job.attempts,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class EphemeralTokenRequest(BaseModel):
    purpose: Literal["job_events", "download"]
    resource: str


class EphemeralTokenResponse(BaseModel):
    token: str
    expires_at: datetime
