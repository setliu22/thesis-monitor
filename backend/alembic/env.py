import os

from alembic import context
from sqlalchemy import create_engine
from app.config import settings
from app.migration_safety import assert_remote_migrations_allowed

configured_url = settings.database_url_unpooled or settings.database_url
assert_remote_migrations_allowed(
    configured_url, os.getenv("THESIS_ALLOW_REMOTE_MIGRATIONS") == "1"
)
url = (
    configured_url
    .replace("postgres://", "postgresql+psycopg://", 1)
    .replace("postgresql://", "postgresql+psycopg://", 1)
)
from app.models import Base

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
