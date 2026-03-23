"""create runtime tables"""

from alembic import op
import sqlalchemy as sa


revision = "20260323_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=120), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("files_modified", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("cwd", sa.String(length=1024), nullable=False),
        sa.Column("base_cwd", sa.String(length=1024), nullable=True),
        sa.Column("target_branch", sa.String(length=255), nullable=True),
        sa.Column("structured_prompt", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.JSON(), nullable=False),
        sa.Column("stderr", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_task_id", "runs", ["task_id"], unique=True)

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_approvals_created_at", "approvals", ["created_at"])
    op.create_index("ix_approvals_task_id", "approvals", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_approvals_task_id", table_name="approvals")
    op.drop_index("ix_approvals_created_at", table_name="approvals")
    op.drop_table("approvals")

    op.drop_index("ix_runs_task_id", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_table("runs")

    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_table("tasks")
