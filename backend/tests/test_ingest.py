from sqlalchemy import select, func
from app.models import Filing, Snapshot, Company, Observation
from app.ingest import ingest_company

# Explicit synthetic SEC-shaped test data.
SUBMISSIONS={'filings':{'recent':{'accessionNumber':['0000016058-25-000001'],'form':['10-K'],'filingDate':['2025-08-01'],'reportDate':['2025-06-30'],'primaryDocument':['annual.htm']}}}
FACTS={'facts':{'us-gaap':{'Revenues':{'units':{'USD':[{'start':'2024-07-01','end':'2025-06-30','filed':'2025-08-01','accn':'0000016058-25-000001','form':'10-K','val':100}]}}}}}
class Client:
    fail=False
    def fetch_json(self,path):
        if 'submissions' in path: return SUBMISSIONS
        if self.fail: raise RuntimeError('SEC temporarily unavailable')
        return FACTS


def test_repeat_ingest_dedupes_and_failure_preserves_good_data(sessions):
    client=Client()
    ingest_company(sessions,1,client)
    ingest_company(sessions,1,client)
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Filing))==1
        assert s.scalar(select(func.count()).select_from(Snapshot))==2
        count=s.scalar(select(func.count()).select_from(Observation))
        assert count>0 and s.get(Company,1).last_success
    client.fail=True
    try: ingest_company(sessions,1,client)
    except RuntimeError: pass
    with sessions() as s:
        assert s.get(Company,1).data_status=='stale'
        assert s.scalar(select(func.count()).select_from(Observation))==count


def test_discovery_before_facts_keeps_filing_and_retries(sessions):
    client=Client(); client.fail=True
    try: ingest_company(sessions,1,client)
    except RuntimeError: pass
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Filing))==1
    client.fail=False
    ingest_company(sessions,1,client)
    with sessions() as s: assert s.get(Company,1).last_success
