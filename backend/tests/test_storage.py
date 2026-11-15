from decimal import Decimal
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Base, Company, ThesisVersion, RuleVersion, Filing, Alert


def test_versions_and_uniqueness_survive_new_session(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path}/storage.db')
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        c = Company(ticker='CACI', name='CACI International', cik='0000016058')
        s.add(c); s.flush()
        s.add_all([ThesisVersion(company_id=c.id, version=1, body='First'), ThesisVersion(company_id=c.id, version=2, body='Revised')])
        r = RuleVersion(company_id=c.id, group_key='growth', version=1, name='Growth', metric='revenue_growth', operator='lt', threshold=Decimal('5'), enabled=True)
        s.add(r); s.flush()
        s.add(Filing(company_id=c.id, accession='0001-25-000001', form='10-K', filed='2025-08-01', report_date='2025-06-30', document='annual.htm'))
        s.add(Alert(company_id=c.id, rule_id=r.id, observation_key='o1', title='Growth below 5%', evidence={'value':'4'}))
        s.commit(); company_id=c.id; rule_id=r.id
    with Session(engine) as s:
        assert [t.body for t in s.scalars(select(ThesisVersion).order_by(ThesisVersion.version))] == ['First', 'Revised']
        s.add(Company(ticker='CACI', name='duplicate', cik='0000016058'))
        with pytest.raises(IntegrityError): s.commit()
        s.rollback()
        s.add(Alert(company_id=company_id, rule_id=rule_id, observation_key='o1', title='duplicate', evidence={}))
        with pytest.raises(IntegrityError): s.commit()
        s.rollback()
        s.add(Filing(company_id=company_id, accession='0001-25-000001', form='10-K', filed='2025-08-01', report_date='', document='annual.htm'))
        with pytest.raises(IntegrityError): s.commit()
