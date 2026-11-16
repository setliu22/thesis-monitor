"""Retire observations and schedules that depended on issuer-specific shortcuts."""

from alembic import op
import sqlalchemy as sa

revision = "d51a306b127e"
down_revision = "c03e447bac10"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    companies = sa.table(
        "companies",
        sa.column("id", sa.Integer),
        sa.column("earnings_schedule", sa.JSON),
    )
    for identity, state in connection.execute(
        sa.select(companies.c.id, companies.c.earnings_schedule)
    ).all():
        if (state or {}).get("provider") != "alphavantage":
            connection.execute(
                companies.update()
                .where(companies.c.id == identity)
                .values(earnings_schedule={})
            )
    observations = sa.table(
        "observations",
        sa.column("id", sa.Integer),
        sa.column("payload", sa.JSON),
        sa.column("active", sa.Boolean),
    )
    for identity, payload in connection.execute(
        sa.select(observations.c.id, observations.c.payload).where(
            observations.c.active.is_(True)
        )
    ).all():
        if any(
            source.get("tag") == "PaymentsToAcquireProductiveAssets"
            for source in (payload or {}).get("sources", [])
        ):
            connection.execute(
                observations.update()
                .where(observations.c.id == identity)
                .values(active=False)
            )


def downgrade():
    # Historical records remain preserved. Never reactivate unsupported mappings on rollback.
    pass
