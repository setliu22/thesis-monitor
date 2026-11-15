from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session


def sec_gate():
    """Serialize request starts across API/worker processes, below 4 req/sec.

    Sleep inside an advisory transaction lock: each request must spend 300ms
    holding the shared gate. Scope is this database, not other applications.
    """
    with engine.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(7331842)'))
        connection.execute(text('SELECT pg_sleep(0.3)'))
