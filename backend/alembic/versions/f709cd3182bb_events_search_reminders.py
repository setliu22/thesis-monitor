"""Scheduled market events, investment flag and reminder outbox support."""

from alembic import op
import sqlalchemy as sa

revision = "f709cd3182bb"
down_revision = "e64d021c90ae"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "companies",
        sa.Column("invested", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "market_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("key", sa.String(250), unique=True, nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("starts_at", sa.String(40)),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id")),
    )
    for name in ("provider", "category", "day", "company_id"):
        op.create_index("ix_market_events_" + name, "market_events", [name])
    op.create_table(
        "reminder_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("days", sa.JSON(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
    )
    with op.batch_alter_table("deliveries") as batch:
        batch.alter_column("alert_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("event_id", sa.Integer()))
        batch.add_column(sa.Column("event_revision", sa.String(64)))
        batch.add_column(sa.Column("reminder_days", sa.Integer()))
        batch.add_column(sa.Column("reminder_key", sa.String(100)))
        batch.add_column(sa.Column("expires_at", sa.String(40)))
        batch.create_foreign_key(
            "fk_delivery_event", "market_events", ["event_id"], ["id"]
        )
        batch.create_unique_constraint("uq_delivery_reminder_key", ["reminder_key"])
        batch.create_index("ix_deliveries_event_id", ["event_id"])


def downgrade():
    raise RuntimeError(
        "Preserve event delivery history; restore from backup for schema rollback."
    )
