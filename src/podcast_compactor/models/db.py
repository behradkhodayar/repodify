"""SQLAlchemy ORM models for jobs, stage status, and artifacts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    feed_url: Mapped[str]
    status: Mapped[str]
    current_stage: Mapped[str | None] = mapped_column(default=None)
    options_json: Mapped[str] = mapped_column(default="{}")
    report_json: Mapped[str] = mapped_column(default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    stages: Mapped[list[StageStatus]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="StageStatus.started_at"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class StageStatus(Base):
    __tablename__ = "stage_status"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    stage: Mapped[str]
    state: Mapped[str]
    detail: Mapped[str | None] = mapped_column(default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    job: Mapped[Job] = relationship(back_populates="stages")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    kind: Mapped[str]
    episode_guid: Mapped[str | None] = mapped_column(default=None)
    uri: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    job: Mapped[Job] = relationship(back_populates="artifacts")
