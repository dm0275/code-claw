from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy.orm import Session, sessionmaker

from app.db import ApprovalRow, init_db
from app.main import create_app
from app.models import Project
from app.services import EventBroker, TaskService, WorkspaceManager
from app.sql_store import SqlStore
from tests.support import InstantRunner, init_git_repo, wait_for_status

DEFAULT_POSTGRES_HOST = os.environ.get("CODECLAW_TEST_POSTGRES_HOST", "127.0.0.1")
DEFAULT_POSTGRES_PORT = int(os.environ.get("CODECLAW_TEST_POSTGRES_PORT", "5432"))
DEFAULT_POSTGRES_USER = os.environ.get("CODECLAW_TEST_POSTGRES_USER", "codeclaw")
DEFAULT_POSTGRES_PASSWORD = os.environ.get("CODECLAW_TEST_POSTGRES_PASSWORD", "codeclaw")
DEFAULT_POSTGRES_ADMIN_DB = os.environ.get("CODECLAW_TEST_POSTGRES_ADMIN_DB", "postgres")


def postgres_admin_url() -> str:
    return (
        os.environ.get("CODECLAW_TEST_POSTGRES_ADMIN_URL")
        or (
            f"postgresql://{DEFAULT_POSTGRES_USER}:{DEFAULT_POSTGRES_PASSWORD}"
            f"@{DEFAULT_POSTGRES_HOST}:{DEFAULT_POSTGRES_PORT}/{DEFAULT_POSTGRES_ADMIN_DB}"
        )
    )


def postgres_database_url(database_name: str) -> str:
    return (
        f"postgresql+psycopg://{DEFAULT_POSTGRES_USER}:{DEFAULT_POSTGRES_PASSWORD}"
        f"@{DEFAULT_POSTGRES_HOST}:{DEFAULT_POSTGRES_PORT}/{database_name}"
    )


def alembic_config(database_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def wait_for_admin_connection(
    admin_url: str,
    timeout_seconds: float = 30.0,
    interval_seconds: float = 0.5,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with psycopg.connect(admin_url, autocommit=True):
                return
        except psycopg.OperationalError as exc:
            last_error = exc
            time.sleep(interval_seconds)

    if last_error is not None:
        raise last_error
    raise TimeoutError("Timed out waiting for Postgres to accept admin connections")


def postgres_session_factory() -> sessionmaker[Session]:
    database_name = f"codeclaw_test_{uuid.uuid4().hex}"
    admin_url = postgres_admin_url()
    database_url = postgres_database_url(database_name)

    wait_for_admin_connection(admin_url)

    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    command.upgrade(alembic_config(database_url), "head")
    return init_db(database_url)


def test_sql_store_and_service_work_against_live_postgres(tmp_path: Path) -> None:
    session_factory = postgres_session_factory()
    database_name = session_factory.kw["bind"].url.database

    try:
        project_root = tmp_path / "project"
        project_root.mkdir()
        init_git_repo(project_root)

        project = Project(id="demo", name="Demo", path=str(project_root), default_branch="main")
        store = SqlStore(projects=[project], session_factory=session_factory)
        service = TaskService(
            store=store,
            workspace_manager=WorkspaceManager(state_root=tmp_path / "state"),
            broker=EventBroker(),
        )
        service.runner = InstantRunner()
        client = TestClient(create_app(service))

        task_response = client.post(
            "/tasks",
            json={
                "project_id": "demo",
                "prompt": "Persist through live Postgres",
                "constraints": ["Keep runtime state in Postgres"],
                "acceptance_criteria": ["Task is reloadable after restart"],
            },
        )
        assert task_response.status_code == 201
        task_id = task_response.json()["id"]

        detail = wait_for_status(client, task_id, "awaiting_approval")
        assert detail["run"]["exit_code"] == 0
        assert detail["task"]["summary"] == "Instant runner completed"

        restarted_store = SqlStore(projects=[project], session_factory=session_factory)
        restarted_service = TaskService(
            store=restarted_store,
            workspace_manager=WorkspaceManager(state_root=tmp_path / "state"),
            broker=EventBroker(),
        )

        reloaded_detail = restarted_service.get_task_detail(task_id)
        assert reloaded_detail.task.prompt == "Persist through live Postgres"
        assert reloaded_detail.run is not None
        assert reloaded_detail.run.task_id == task_id

        with session_factory() as session:
            approvals = session.query(ApprovalRow).filter(ApprovalRow.task_id == task_id).all()

        assert approvals == []
    finally:
        session_factory.kw["bind"].dispose()
        with psycopg.connect(postgres_admin_url(), autocommit=True) as connection:
            connection.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (database_name,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name))
            )
