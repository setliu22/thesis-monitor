import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Company


@pytest.fixture
def sessions(tmp_path):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        s.add(Company(ticker="CACI", name="CACI International", cik="0000016058"))
        s.commit()
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def isolate_provider_and_migration_settings(monkeypatch):
    """Tests must never inherit live provider credentials or direct DB overrides."""
    from app.config import settings

    for field in (
        "groq_api_key",
        "resend_api_key",
        "alphavantage_api_key",
        "database_url_unpooled",
    ):
        monkeypatch.setattr(settings, field, "")
