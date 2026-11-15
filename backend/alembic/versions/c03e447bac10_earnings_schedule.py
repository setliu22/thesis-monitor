"""Persist earnings calendar state."""

from alembic import op
import sqlalchemy as sa

revision = "c03e447bac10"
down_revision = "b82d5a1f0991"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "companies",
        sa.Column("earnings_schedule", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("companies", "earnings_schedule")
