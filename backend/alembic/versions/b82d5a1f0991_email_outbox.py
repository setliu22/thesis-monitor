"""Durable email outbox."""

from alembic import op
import sqlalchemy as sa

revision = "b82d5a1f0991"
down_revision = "981dc3a2c141"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column(
            "alert_id",
            sa.Integer(),
            sa.ForeignKey("alerts.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("key", sa.String(80), unique=True, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.String(40), nullable=False),
        sa.Column("first_attempt", sa.String(40)),
        sa.Column("owner", sa.String(80)),
        sa.Column("provider_id", sa.String(100)),
        sa.Column("error", sa.String(250)),
    )
    op.create_index("ix_deliveries_due", "deliveries", ["status", "available_at"])


def downgrade():
    op.drop_table("deliveries")
