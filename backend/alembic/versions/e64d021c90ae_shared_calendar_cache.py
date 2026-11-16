"""Persist one leased calendar cache across the entire watchlist."""

from alembic import op
import sqlalchemy as sa

revision = "e64d021c90ae"
down_revision = "d51a306b127e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "calendar_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(50), unique=True, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("last_attempt", sa.String(40)),
        sa.Column("error", sa.Text()),
        sa.Column("owner", sa.String(80)),
        sa.Column("lease_until", sa.String(40)),
    )


def downgrade():
    op.drop_table("calendar_cache")
