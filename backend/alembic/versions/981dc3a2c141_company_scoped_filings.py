"""Scope filing accession uniqueness to a watched company (share-class aliases)."""

from alembic import op
import sqlalchemy as sa

revision = "981dc3a2c141"
down_revision = "e13f01c9d454"
branch_labels = None
depends_on = None


def upgrade():
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("filings")
    previous = next(c for c in constraints if c["column_names"] == ["accession"])
    # SQLite's initial unnamed UNIQUE needs a convention during batch reflection.
    old_name = previous["name"] or "uq_filings_accession"
    with op.batch_alter_table(
        "filings", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}
    ) as batch:
        batch.drop_constraint(old_name, type_="unique")
        batch.create_unique_constraint(
            "uq_filings_company_accession", ["company_id", "accession"]
        )


def downgrade():
    # A global constraint cannot represent legitimate aliases; refuse lossy rollback.
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT accession FROM filings GROUP BY accession HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    if duplicates:
        raise RuntimeError(
            "Cannot downgrade while share-class duplicate accessions exist; preserve the company-scoped schema."
        )
    with op.batch_alter_table("filings") as batch:
        batch.drop_constraint("uq_filings_company_accession", type_="unique")
        batch.create_unique_constraint("uq_filings_accession", ["accession"])
