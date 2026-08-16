"""Engine and session factory helpers."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from podcast_compactor.models.db import Base


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
