from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from app.config import settings


def test_migration_upgrades_existing_rules_and_observations(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/migration.db"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(cfg, "7af12f6bfd42")
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO companies (id,created_at,ticker,name,cik,data_status) VALUES (1,'2025-01-01','TEST','Synthetic company','0000000001','empty')"
            )
        )
        c.execute(
            text(
                "INSERT INTO rules (id,created_at,company_id,group_key,version,name,metric,operator,threshold,enabled) VALUES (1,'2025-01-01',1,'r',1,'Growth','revenue_growth','lt',5,true)"
            )
        )
        c.execute(
            text(
                "INSERT INTO observations (id,created_at,company_id,identity,metric,period_end,kind,value,unit,payload) VALUES (1,'2025-01-01',1,'x','revenue','2025-06-30','annual',100,'USD','{}')"
            )
        )
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        assert c.execute(text("SELECT active FROM observations")).scalar() == 1
        assert c.execute(text("SELECT period_kind FROM rules")).scalar() == "quarter"


def test_claim_review_migration_preserves_legacy_analysis_rows(tmp_path, monkeypatch):
    import json

    url = f"sqlite:///{tmp_path}/legacy-analysis.db"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(cfg, "c4d98e12f601")
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO companies (id,created_at,ticker,name,cik,data_status) VALUES (1,'2026-01-01','TEST','Test','0000000001','current')"
            )
        )
        c.execute(
            text(
                "INSERT INTO filings(id,created_at,company_id,accession,form,filed,report_date,document) VALUES (1,'2026-01-01',1,'0000000001-26-000001','10-Q','2026-01-01','2025-12-31','q.htm')"
            )
        )
        c.execute(
            text(
                "INSERT INTO theses(id,created_at,company_id,version,body) VALUES (1,'2026-01-01',1,1,'A saved thesis')"
            )
        )
        c.execute(
            text(
                "INSERT INTO analyses(id,created_at,company_id,filing_id,thesis_id,model,prompt_version,result) VALUES (1,'2026-01-01',1,1,1,'old','v6-full-call',:result)"
            ),
            {
                "result": json.dumps(
                    {"observations": [], "scope": "Legacy result remains readable"}
                )
            },
        )
    command.upgrade(cfg, "head")
    with engine.connect() as c:
        row = c.execute(text("SELECT review_id,stage_key,result FROM analyses")).one()
        assert row.review_id is None and row.stage_key is None
        assert json.loads(row.result)["scope"] == "Legacy result remains readable"
        assert c.execute(text("SELECT count(*) FROM reviews")).scalar() == 0
