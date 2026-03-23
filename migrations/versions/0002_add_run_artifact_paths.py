"""add run artifact paths"""

from alembic import op
import sqlalchemy as sa


revision = "20260323_000002"
down_revision = "20260323_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("diff_path", sa.String(length=2048), nullable=True))
    op.add_column("runs", sa.Column("stdout_path", sa.String(length=2048), nullable=True))
    op.add_column("runs", sa.Column("stderr_path", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "stderr_path")
    op.drop_column("runs", "stdout_path")
    op.drop_column("runs", "diff_path")
