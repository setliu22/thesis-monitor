from sqlalchemy import select, func
from app.models import Filing, Snapshot, Company, Observation
from app.ingest import ingest_company

# Explicit synthetic SEC-shaped test data.
SUBMISSIONS = {
    "filings": {
        "recent": {
            "accessionNumber": ["0000016058-25-000001"],
            "form": ["10-K"],
            "filingDate": ["2025-08-01"],
            "reportDate": ["2025-06-30"],
            "primaryDocument": ["annual.htm"],
        }
    }
}
FACTS = {
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "start": "2024-07-01",
                            "end": "2025-06-30",
                            "filed": "2025-08-01",
                            "accn": "0000016058-25-000001",
                            "form": "10-K",
                            "val": 100,
                        }
                    ]
                }
            }
        }
    }
}


class Client:
    fail = False

    def fetch_json(self, path):
        if "submissions" in path:
            return SUBMISSIONS
        if self.fail:
            raise RuntimeError("SEC temporarily unavailable")
        return FACTS


def test_repeat_ingest_dedupes_and_failure_preserves_good_data(sessions):
    client = Client()
    ingest_company(sessions, 1, client)
    ingest_company(sessions, 1, client)
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Filing)) == 1
        assert s.scalar(select(func.count()).select_from(Snapshot)) == 2
        count = s.scalar(select(func.count()).select_from(Observation))
        assert count > 0 and s.get(Company, 1).last_success
    client.fail = True
    try:
        ingest_company(sessions, 1, client)
    except RuntimeError:
        pass
    with sessions() as s:
        assert s.get(Company, 1).data_status == "stale"
        assert s.scalar(select(func.count()).select_from(Observation)) == count


def test_discovery_before_facts_keeps_filing_and_retries(sessions):
    client = Client()
    client.fail = True
    try:
        ingest_company(sessions, 1, client)
    except RuntimeError:
        pass
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Filing)) == 1
    client.fail = False
    ingest_company(sessions, 1, client)
    with sessions() as s:
        assert s.get(Company, 1).last_success


def test_share_class_tickers_retain_their_own_filing_links(sessions):
    with sessions() as s:
        s.add(Company(ticker="ALIAS", name="Synthetic issuer alias", cik="0000016058"))
        s.commit()
    ingest_company(sessions, 1, Client())
    ingest_company(sessions, 2, Client())
    with sessions() as s:
        assert (
            s.scalar(
                select(func.count()).select_from(Filing).where(Filing.company_id == 1)
            )
            == 1
        )
        assert (
            s.scalar(
                select(func.count()).select_from(Filing).where(Filing.company_id == 2)
            )
            == 1
        )


def test_mapping_quota_wait_preserves_fresh_financial_data(sessions, monkeypatch):
    import pytest
    from app import ingest
    from app.groq_runtime import Deferred

    def wait(*args, **kwargs):
        raise Deferred(60)

    monkeypatch.setattr(ingest, "investigate", wait)
    with pytest.raises(Deferred):
        ingest_company(sessions, 1, Client())
    with sessions() as s:
        company = s.get(Company, 1)
        assert company.last_success and company.data_status == "current"
        assert company.last_error is None
        assert s.scalar(select(func.count()).select_from(Observation)) > 0
