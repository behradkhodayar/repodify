"""JobRepository: the pipeline's window onto persistent job state."""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from podcast_compactor.models.db import Artifact, Job, StageStatus, _now
from podcast_compactor.models.domain import JobOptions
from podcast_compactor.models.enums import JobStatus, StageName, StageState


class JobRepository:
    """CRUD + stage/artifact tracking for jobs."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def create_job(self, feed_url: str, options: JobOptions) -> str:
        with self._sf() as s:
            job = Job(
                feed_url=feed_url,
                status=JobStatus.QUEUED.value,
                options_json=options.model_dump_json(),
                report_json="{}",
            )
            s.add(job)
            s.commit()
            return job.id

    def get_job(self, job_id: str) -> Job:
        with self._sf() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            # Force-load collections before detaching.
            _ = list(job.stages), list(job.artifacts)
            s.expunge_all()
            return job

    def list_jobs(self, limit: int = 50, offset: int = 0) -> tuple[list[Job], int]:
        with self._sf() as s:
            total = s.scalar(select(func.count()).select_from(Job)) or 0
            rows = list(
                s.scalars(
                    select(Job)
                    .order_by(Job.created_at.desc(), Job.id.desc())
                    .limit(limit)
                    .offset(offset)
                ).all()
            )
            for job in rows:
                _ = list(job.stages), list(job.artifacts)
            s.expunge_all()
            return rows, total

    def set_status(self, job_id: str, status: JobStatus) -> None:
        with self._sf() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            job.status = status.value
            if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                job.finished_at = _now()
            s.commit()

    def set_options(self, job_id: str, options: JobOptions) -> None:
        """Replace the job's stored options (e.g. after an interactive voice review)."""
        with self._sf() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            job.options_json = options.model_dump_json()
            s.commit()

    def start_stage(self, job_id: str, stage: StageName) -> None:
        with self._sf() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            job.current_stage = stage.value
            job.status = JobStatus.RUNNING.value
            s.add(
                StageStatus(
                    job_id=job_id,
                    stage=stage.value,
                    state=StageState.RUNNING.value,
                    started_at=_now(),
                )
            )
            s.commit()

    def finish_stage(
        self,
        job_id: str,
        stage: StageName,
        state: StageState,
        detail: str | None = None,
    ) -> None:
        with self._sf() as s:
            row = s.scalars(
                select(StageStatus)
                .where(
                    StageStatus.job_id == job_id,
                    StageStatus.stage == stage.value,
                    StageStatus.state == StageState.RUNNING.value,
                )
                .order_by(StageStatus.started_at.desc())
            ).first()
            if row is None:
                raise KeyError(f"no running stage {stage.value} for job {job_id}")
            row.state = state.value
            row.detail = detail
            row.finished_at = _now()
            s.commit()

    def add_artifact(
        self,
        job_id: str,
        kind: str,
        uri: str,
        episode_guid: str | None = None,
    ) -> None:
        with self._sf() as s:
            s.add(
                Artifact(job_id=job_id, kind=kind, uri=uri, episode_guid=episode_guid)
            )
            s.commit()

    def set_report(self, job_id: str, report: dict) -> None:
        with self._sf() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            job.report_json = json.dumps(report)
            s.commit()
