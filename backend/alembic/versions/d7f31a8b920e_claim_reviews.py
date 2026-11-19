"""Durable versioned narrative reviews and idempotent stage publications."""

from alembic import op
import sqlalchemy as sa

revision = "d7f31a8b920e"
down_revision = "c4d98e12f601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column(
            "company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False
        ),
        sa.Column(
            "filing_id", sa.Integer(), sa.ForeignKey("filings.id"), nullable=False
        ),
        sa.Column(
            "thesis_id", sa.Integer(), sa.ForeignKey("theses.id"), nullable=False
        ),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("next_attempt", sa.String(40)),
        sa.Column("last_error", sa.Text()),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "filing_id",
            "thesis_id",
            "model",
            "version",
            name="uq_review_identity",
        ),
    )
    op.create_index("ix_reviews_company_id", "reviews", ["company_id"])
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("review_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("stage_key", sa.String(64), nullable=True))
        batch.create_foreign_key(
            "fk_analyses_review_id", "reviews", ["review_id"], ["id"]
        )
        batch.create_unique_constraint("uq_analysis_stage", ["review_id", "stage_key"])
        batch.create_index("ix_analyses_review_id", ["review_id"])


def downgrade():
    with op.batch_alter_table("analyses") as batch:
        batch.drop_index("ix_analyses_review_id")
        batch.drop_constraint("uq_analysis_stage", type_="unique")
        batch.drop_constraint("fk_analyses_review_id", type_="foreignkey")
        batch.drop_column("stage_key")
        batch.drop_column("review_id")
    op.drop_index("ix_reviews_company_id", table_name="reviews")
    op.drop_table("reviews")
