"""Reversible watchlist removal without deleting investment history."""

from alembic import op
import sqlalchemy as sa

revision = "b29e7f01ac64"
down_revision = "a10c42dbf973"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "companies",
        sa.Column("watched", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("companies", "watched")
