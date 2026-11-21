from sqlalchemy import select
from app.models import Company, Filing, Job, Review, ThesisVersion
from app.discovery import persist_discovery, submissions_only
from app.config import settings


def submissions(*rows):
    return {
        "filings": {
            "recent": {
                "accessionNumber": [r[0] for r in rows],
                "form": [r[1] for r in rows],
                "filingDate": [r[2] for r in rows],
                "primaryDocument": ["report.htm"] * len(rows),
            }
        }
    }


def save(sessions, data):
    with sessions.begin() as s:
        persist_discovery(
            s, s.scalar(select(Company).where(Company.id == 1).with_for_update()), data
        )


def test_initial_history_bounded_then_all_new_before_facts(sessions, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "mock")
    with sessions.begin() as s:
        s.add(ThesisVersion(company_id=1, version=1, body="Backlog converts"))
    baseline = submissions(("a", "10-Q", "2025-01-01"), ("b", "10-K", "2026-01-01"))
    save(sessions, baseline)
    save(sessions, baseline)
    with sessions() as s:
        assert len(s.scalars(select(Job)).all()) == 1
    save(
        sessions,
        submissions(
            ("c", "10-Q", "2026-05-01"),
            ("d", "10-Q", "2026-09-01"),
            ("e", "8-K", "2026-09-02"),
        ),
    )
    with sessions() as s:
        assert len(s.scalars(select(Review)).all()) == 3
        assert len(s.scalars(select(Filing)).all()) == 5
        # No companyfacts were requested or needed to durably register work.
        assert s.get(Company, 1).last_success is None


def test_submissions_fallback_cached_outside_window(sessions, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "mock")
    with sessions.begin() as s:
        s.add(ThesisVersion(company_id=1, version=1, body="Revenue grows"))
        s.get(Company, 1).earnings_schedule = {"status": "outside_window"}

    class Client:
        calls = []

        def fetch_json(self, path):
            self.calls.append(path)
            assert "companyfacts" not in path
            return submissions(("late", "10-Q", "2026-11-01"))

    client = Client()
    assert submissions_only(sessions, client) == 1
    assert submissions_only(sessions, client) == 0
    assert len(client.calls) == 1
    with sessions() as s:
        assert len(s.scalars(select(Job)).all()) == 1


def test_configuration_recovery_with_existing_reviews_is_latest_only(
    sessions, monkeypatch
):
    from app.reviews import reconcile_reviews

    monkeypatch.setattr(settings, "groq_api_key", "mock")
    with sessions.begin() as s:
        s.add(ThesisVersion(company_id=1, version=1, body="Revenue grows"))
    save(sessions, submissions(("old", "10-Q", "2026-01-01")))
    monkeypatch.setattr(settings, "groq_api_key", "")
    save(
        sessions,
        submissions(("mid", "10-Q", "2026-05-01"), ("latest", "10-Q", "2026-09-01")),
    )
    monkeypatch.setattr(settings, "groq_api_key", "mock")
    reconcile_reviews(sessions)
    reconcile_reviews(sessions)
    with sessions() as s:
        assert len(s.scalars(select(Review)).all()) == 2
        newest = s.scalar(select(Filing).where(Filing.accession == "latest"))
        assert s.scalar(select(Review).where(Review.filing_id == newest.id))
