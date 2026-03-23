from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
from typing import Deque

from sqlalchemy.orm import Session, sessionmaker

from app.db import ApprovalRow, RunRow, TaskRow, session_scope
from app.models import ApprovalAction, Project, Run, Task, TaskEvent, TaskStatus, new_id


class SqlStore:
    """Persist tasks, runs, and approvals in SQL while keeping projects/events local."""

    def __init__(self, projects: list[Project], session_factory: sessionmaker[Session]) -> None:
        self._lock = Lock()
        self.projects = {project.id: project for project in projects}
        self.session_factory = session_factory
        self.events_by_task: dict[str, Deque[TaskEvent]] = defaultdict(lambda: deque(maxlen=200))

    def list_projects(self) -> list[Project]:
        return list(self.projects.values())

    def get_project(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    def add_task(self, task: Task) -> Task:
        with session_scope(self.session_factory) as session:
            session.add(_task_row_from_model(task))
        return task

    def update_task(self, task: Task) -> Task:
        with session_scope(self.session_factory) as session:
            session.merge(_task_row_from_model(task))
        return task

    def list_tasks(self) -> list[Task]:
        with session_scope(self.session_factory) as session:
            rows = session.query(TaskRow).order_by(TaskRow.created_at.desc()).all()
            return [_task_model_from_row(row) for row in rows]

    def get_task(self, task_id: str) -> Task | None:
        with session_scope(self.session_factory) as session:
            row = session.get(TaskRow, task_id)
            return _task_model_from_row(row) if row else None

    def set_run(self, run: Run) -> Run:
        with session_scope(self.session_factory) as session:
            session.merge(_run_row_from_model(run))
        return run

    def get_run(self, task_id: str) -> Run | None:
        with session_scope(self.session_factory) as session:
            row = session.query(RunRow).filter(RunRow.task_id == task_id).one_or_none()
            return _run_model_from_row(row) if row else None

    def add_approval(
        self,
        task_id: str,
        action: ApprovalAction,
        created_at: datetime,
    ) -> None:
        with session_scope(self.session_factory) as session:
            session.add(
                ApprovalRow(
                    id=new_id(),
                    task_id=task_id,
                    action=action.value,
                    approved=action is ApprovalAction.APPROVE,
                    created_at=created_at,
                )
            )

    def add_event(self, event: TaskEvent) -> TaskEvent:
        with self._lock:
            self.events_by_task[event.task_id].append(event)
            return event

    def list_events(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            return list(self.events_by_task[task_id])


def _task_row_from_model(task: Task) -> TaskRow:
    return TaskRow(
        id=task.id,
        project_id=task.project_id,
        prompt=task.prompt,
        constraints=task.constraints,
        acceptance_criteria=task.acceptance_criteria,
        status=task.status.value,
        summary=task.summary,
        files_modified=task.files_modified,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
    )


def _task_model_from_row(row: TaskRow) -> Task:
    return Task(
        id=row.id,
        project_id=row.project_id,
        prompt=row.prompt,
        constraints=list(row.constraints or []),
        acceptance_criteria=list(row.acceptance_criteria or []),
        status=TaskStatus(row.status),
        summary=row.summary,
        files_modified=list(row.files_modified or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


def _run_row_from_model(run: Run) -> RunRow:
    return RunRow(
        id=run.id,
        task_id=run.task_id,
        cwd=run.cwd,
        base_cwd=run.base_cwd,
        target_branch=run.target_branch,
        diff_path=run.diff_path,
        stdout_path=run.stdout_path,
        stderr_path=run.stderr_path,
        structured_prompt=run.structured_prompt,
        status=run.status.value,
        exit_code=run.exit_code,
        stdout=run.stdout,
        stderr=run.stderr,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _run_model_from_row(row: RunRow) -> Run:
    return Run(
        id=row.id,
        task_id=row.task_id,
        cwd=row.cwd,
        base_cwd=row.base_cwd,
        target_branch=row.target_branch,
        diff_path=row.diff_path,
        stdout_path=row.stdout_path,
        stderr_path=row.stderr_path,
        structured_prompt=row.structured_prompt,
        status=TaskStatus(row.status),
        exit_code=row.exit_code,
        stdout=list(row.stdout or []),
        stderr=list(row.stderr or []),
        created_at=row.created_at,
        completed_at=row.completed_at,
    )
