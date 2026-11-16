"""Track provider delivery receipts independently from send attempts."""

from alembic import op
import sqlalchemy as sa

revision = "a10c42dbf973"
down_revision = "f709cd3182bb"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("deliveries", sa.Column("receipt_event", sa.String(40)))
    op.add_column("deliveries", sa.Column("receipt_next_at", sa.String(40)))
    op.add_column("deliveries", sa.Column("receipt_error", sa.String(250)))
    op.create_index("ix_deliveries_receipt_next_at", "deliveries", ["receipt_next_at"])
    op.execute(
        "UPDATE deliveries SET receipt_next_at = available_at WHERE status = 'accepted' AND provider_id IS NOT NULL"
    )


def downgrade():
    op.drop_index("ix_deliveries_receipt_next_at", table_name="deliveries")
    for column in ("receipt_error", "receipt_next_at", "receipt_event"):
        op.drop_column("deliveries", column)
