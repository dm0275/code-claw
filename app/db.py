from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import JSON, Boolean, DateTime, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://codeclaw:codeclaw@127.0.0.1:5432/codeclaw"


def database_url() -> str:
    """Return the configured database URL for runtime state persistence."""
    return (
        os.environ.get("CODECLAW_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(120), index=True)
    prompt: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String(32), default="change")
    constraints: Mapped[list[str]] = mapped_column(JSON)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    files_modified: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cwd: Mapped[str] = mapped_column(String(1024))
    base_cwd: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    target_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    diff_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    stdout_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    stderr_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    structured_prompt: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(32), index=True)
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    stdout: Mapped[list[str]] = mapped_column(JSON)
    stderr: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRow(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32))
    approved: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TaskEventRow(Base):
    __tablename__ = "task_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    message: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def make_engine(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured runtime database."""
    return create_engine(url or database_url(), future=True)


def make_session_factory(url: str | None = None) -> sessionmaker[Session]:
    """Create a session factory bound to the configured runtime database."""
    engine = make_engine(url)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(url: str | None = None) -> sessionmaker[Session]:
    """Return a ready-to-use session factory for an already-migrated database."""
    return make_session_factory(url)


def create_all_tables(url: str | None = None) -> sessionmaker[Session]:
    """Create all ORM tables directly for isolated tests and temporary bootstraps."""
    session_factory = make_session_factory(url)
    Base.metadata.create_all(session_factory.kw["bind"])
    return session_factory


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Open a transaction-scoped SQLAlchemy session."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
