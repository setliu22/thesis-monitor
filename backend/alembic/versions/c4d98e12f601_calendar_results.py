"""Persist release results on calendar events."""

from alembic import op
import sqlalchemy as sa

revision = "c4d98e12f601"
down_revision = "b29e7f01ac64"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "market_events",
        sa.Column("outcome", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade():
    op.drop_column("market_events", "outcome")
