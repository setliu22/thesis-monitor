from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from app.config import settings


def test_migration_upgrades_existing_rules_and_observations(tmp_path,monkeypatch):
    url=f'sqlite:///{tmp_path}/migration.db'
    monkeypatch.setattr(settings,'database_url',url)
    cfg=Config(str(Path(__file__).parents[1]/'alembic.ini'))
    command.upgrade(cfg,'7af12f6bfd42')
    engine=create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO companies (id,created_at,ticker,name,cik,data_status) VALUES (1,'2025-01-01','TEST','Synthetic company','0000000001','empty')"))
        c.execute(text("INSERT INTO rules (id,created_at,company_id,group_key,version,name,metric,operator,threshold,enabled) VALUES (1,'2025-01-01',1,'r',1,'Growth','revenue_growth','lt',5,true)"))
        c.execute(text("INSERT INTO observations (id,created_at,company_id,identity,metric,period_end,kind,value,unit,payload) VALUES (1,'2025-01-01',1,'x','revenue','2025-06-30','annual',100,'USD','{}')"))
    command.upgrade(cfg,'head')
    with engine.connect() as c:
        assert c.execute(text('SELECT active FROM observations')).scalar()==1
        assert c.execute(text('SELECT period_kind FROM rules')).scalar()=='quarter'
