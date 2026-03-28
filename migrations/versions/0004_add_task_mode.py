"""add task mode"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_000004"
down_revision = "20260328_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="change"),
    )
    op.alter_column("tasks", "mode", server_default=None)


def downgrade() -> None:
    op.drop_column("tasks", "mode")
