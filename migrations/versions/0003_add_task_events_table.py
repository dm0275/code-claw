"""add task events table"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_000003"
down_revision = "20260323_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])
    op.create_index("ix_task_events_timestamp", "task_events", ["timestamp"])
    op.create_index("ix_task_events_type", "task_events", ["type"])


def downgrade() -> None:
    op.drop_index("ix_task_events_type", table_name="task_events")
    op.drop_index("ix_task_events_timestamp", table_name="task_events")
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")
