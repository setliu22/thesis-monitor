from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.db import get_session
from app.models import Observation


@pytest.fixture
def api(sessions):
    def db():
        with sessions() as s:
            yield s

    app.dependency_overrides[get_session] = db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_company_detail_and_thesis_versions(api):
    detail = api.get("/api/companies/1").json()
    assert detail["company"]["ticker"] == "CACI" and detail["observations"] == []
    assert (
        api.put(
            "/api/companies/1/thesis",
            json={"body": "Revenue and cash conversion remain strong."},
        ).status_code
        == 200
    )
    assert (
        api.put("/api/companies/1/thesis", json={"body": "Revised view."}).json()[
            "version"
        ]
        == 2
    )
    assert api.get("/api/companies/1").json()["thesis"]["body"] == "Revised view."
    assert api.get("/api/companies/999").status_code == 404


def test_thesis_history_deletes_versions_and_their_comparisons(api, sessions):
    from sqlalchemy import select
    from app.models import Analysis, Filing, Job, Review, ThesisVersion

    with sessions.begin() as s:
        filing = Filing(
            company_id=1,
            accession="history-test",
            form="10-Q",
            filed="2026-10-22",
            report_date="2026-09-30",
            document="q.htm",
        )
        first = ThesisVersion(company_id=1, version=1, body="First thesis.")
        second = ThesisVersion(company_id=1, version=2, body="Second thesis.")
        s.add_all([filing, first, second])
        s.flush()
        first_review = Review(
            company_id=1,
            filing_id=filing.id,
            thesis_id=first.id,
            model="test-model",
            version="v7-claim-review",
        )
        second_review = Review(
            company_id=1,
            filing_id=filing.id,
            thesis_id=second.id,
            model="test-model",
            version="v7-claim-review",
        )
        s.add_all([first_review, second_review])
        s.flush()
        first_analysis = Analysis(
            review_id=first_review.id,
            stage_key="filing",
            company_id=1,
            filing_id=filing.id,
            thesis_id=first.id,
            model="test-model",
            prompt_version="v7-claim-review",
            result={"summary": "First thesis result."},
        )
        second_analysis = Analysis(
            review_id=second_review.id,
            stage_key="filing",
            company_id=1,
            filing_id=filing.id,
            thesis_id=second.id,
            model="test-model",
            prompt_version="v7-claim-review",
            result={"summary": "Second thesis result."},
        )
        s.add_all([first_analysis, second_analysis])
        s.flush()
        s.add_all(
            [
                Job(
                    company_id=1,
                    kind="analysis",
                    status="queued",
                    payload={"review_id": first_review.id},
                ),
                Job(
                    company_id=1,
                    kind="analysis",
                    status="queued",
                    payload={"summary_analysis_id": first_analysis.id},
                ),
            ]
        )
        first_id, second_id = first.id, second.id
        first_review_id, first_analysis_id = first_review.id, first_analysis.id
        second_review_id, second_analysis_id = second_review.id, second_analysis.id

    versions = api.get("/api/companies/1/thesis/versions")
    assert versions.status_code == 200
    assert [version["version"] for version in versions.json()] == [2, 1]

    deleted = api.delete(f"/api/companies/1/thesis/versions/{first_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted_id"] == first_id
    assert deleted.json()["current"]["id"] == second_id
    with sessions() as s:
        assert s.get(ThesisVersion, first_id) is None
        assert s.get(Review, first_review_id) is None
        assert s.get(Analysis, first_analysis_id) is None
        assert s.get(Review, second_review_id) is not None
        assert s.get(Analysis, second_analysis_id) is not None
        assert sorted(job.status for job in s.scalars(select(Job)).all()) == [
            "cancelled",
            "cancelled",
        ]

    cleared = api.delete("/api/companies/1/thesis/versions")
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 1
    assert cleared.json()["current"] is None
    assert api.get("/api/companies/1/thesis/versions").json() == []
    with sessions() as s:
        assert s.get(ThesisVersion, second_id) is None
        assert s.get(Review, second_review_id) is None
        assert s.get(Analysis, second_analysis_id) is None


def test_review_earnings_endpoint_queues_the_selected_filing(api, sessions, monkeypatch):
    from app import analysis_dispatch, main
    from app.config import settings
    from app.models import Filing, Job, ThesisVersion
    from sqlalchemy import select

    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(main, "require_sec", lambda: None)
    woken = []
    monkeypatch.setattr(analysis_dispatch, "wake_analysis", lambda: woken.append(True))
    with sessions.begin() as s:
        filing = Filing(
            company_id=1,
            accession="review-button-test",
            form="10-Q",
            filed="2026-10-22",
            report_date="2026-09-30",
            document="q.htm",
        )
        thesis = ThesisVersion(
            company_id=1, version=1, body="Revenue growth supports my thesis."
        )
        s.add_all([filing, thesis])
        s.flush()
        filing_id, thesis_id = filing.id, thesis.id

    response = api.post(
        "/api/companies/1/analyze",
        json={"filing_id": filing_id},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert woken == [True]
    with sessions() as s:
        job = s.scalar(select(Job).where(Job.kind == "analysis"))
        assert job.status == "queued"
        assert job.payload["filing_id"] == filing_id
        assert job.payload["thesis_id"] == thesis_id


def test_rule_validation_and_versioned_edits(api):
    good = {
        "name": "Growth floor",
        "metric": "revenue_growth",
        "operator": "lt",
        "threshold": "5",
        "period_kind": "quarter",
        "enabled": True,
    }
    assert (
        api.post(
            "/api/companies/1/rules", json=good | {"metric": "imaginary"}
        ).status_code
        == 422
    )
    assert (
        api.post("/api/companies/1/rules", json=good | {"threshold": "NaN"}).status_code
        == 422
    )
    rule = api.post("/api/companies/1/rules", json=good).json()
    assert rule["version"] == 1
    edit = api.put(
        f"/api/companies/1/rules/{rule['group_key']}", json=good | {"enabled": False}
    ).json()
    assert edit["version"] == 2
    assert len(api.get("/api/companies/1").json()["rules"]) == 1


def test_saved_rule_checks_current_and_each_new_violating_period_once(
    api, sessions, monkeypatch
):
    from sqlalchemy import select, func
    from app.config import settings
    from app.models import Alert, Delivery

    monkeypatch.setattr(settings, "resend_api_key", "test-no-real-email")
    monkeypatch.setattr(settings, "email_from", "test@example.com")
    monkeypatch.setattr(settings, "alert_email", "recipient@example.com")
    with sessions() as s:
        s.add(
            Observation(
                company_id=1,
                identity="x",
                metric="revenue_growth",
                period_end="2025-06-30",
                kind="quarter",
                value=4,
                unit="%",
                active=True,
                payload={
                    "value": "4",
                    "metric": "revenue_growth",
                    "end": "2025-06-30",
                    "sources": [],
                },
            )
        )
        s.commit()
    saved = api.post(
        "/api/companies/1/rules",
        json={
            "name": "Growth floor",
            "metric": "revenue_growth",
            "operator": "lt",
            "threshold": "5",
            "period_kind": "quarter",
            "enabled": True,
        },
    )
    assert saved.status_code == 201
    assert len(api.get("/api/companies/1").json()["alerts"]) == 1
    with sessions() as s:
        assert s.scalar(select(func.count(Delivery.id))) == 1

    assert api.post("/api/companies/1/evaluate").json()["created"] == 0

    with sessions() as s:
        s.add(
            Observation(
                company_id=1,
                identity="y",
                metric="revenue_growth",
                period_end="2025-09-30",
                kind="quarter",
                value=3,
                unit="%",
                active=True,
                payload={
                    "value": "3",
                    "metric": "revenue_growth",
                    "start": "2025-07-01",
                    "end": "2025-09-30",
                    "kind": "quarter",
                    "unit": "%",
                    "sources": [],
                },
            )
        )
        s.commit()

    assert api.post("/api/companies/1/evaluate").json()["created"] == 1
    assert api.post("/api/companies/1/evaluate").json()["created"] == 0
    with sessions() as s:
        assert s.scalar(select(func.count(Alert.id))) == 2
        assert s.scalar(select(func.count(Delivery.id))) == 2

    alert = api.get("/api/companies/1").json()["alerts"][0]
    assert api.post(f"/api/alerts/{alert['id']}/acknowledge").json()["acknowledged_at"]


def test_missing_sec_setup_is_explicit(api):
    from app.config import settings

    original = settings.sec_user_agent
    settings.sec_user_agent = ""
    try:
        assert api.post("/api/companies/1/refresh").status_code == 409
        assert api.post("/api/companies", json={"ticker": "bad url"}).status_code == 422
        assert not api.get("/api/settings").json()["sec_configured"]
    finally:
        settings.sec_user_agent = original


def test_local_dev_origin_can_save_and_external_origin_is_rejected(api):
    assert (
        api.put(
            "/api/companies/1/thesis",
            json={"body": "A local thesis."},
            headers={"Origin": "http://127.0.0.1:5174"},
        ).status_code
        == 200
    )
    assert (
        api.put(
            "/api/companies/1/thesis",
            json={"body": "Injected."},
            headers={"Origin": "https://external.invalid"},
        ).status_code
        == 403
    )


def test_calendar_company_context_is_only_for_the_selected_stock(api, sessions):
    from app.models import Company, MarketEvent, Observation

    with sessions.begin() as s:
        second = Company(ticker="MSFT", name="Microsoft", cik="0000789019", invested=False)
        s.add(second)
        s.flush()
        s.add(
            MarketEvent(
                key="fed:2026-11-18",
                provider="events-fed",
                category="fed",
                title="Federal Reserve decision",
                day="2026-11-18",
                source_url="https://example.org/fed",
                status="scheduled",
                revision="rev-1",
                active=True,
                outcome={
                    "status": "reported",
                    "event_revision": "rev-1",
                    "metrics": [
                        {
                            "label": "Fed target upper limit",
                            "value": "4.00",
                            "previous": "4.25",
                            "change": "-0.25",
                            "unit": "%",
                            "direction": "down",
                            "period": "2026-11-19",
                            "previous_period": "2026-11-18",
                        }
                    ],
                },
            )
        )
        s.add(
            MarketEvent(
                key="cpi:2026-11-18",
                provider="events-bls",
                category="inflation",
                title="Consumer Price Index",
                day="2026-11-18",
                source_url="https://example.org/cpi",
                status="scheduled",
                revision="rev-cpi",
                active=True,
                outcome={
                    "status": "reported",
                    "event_revision": "rev-cpi",
                    "metrics": [
                        {
                            "label": "Monthly CPI inflation",
                            "value": "0.3502845690429321613568918",
                            "previous": "0.6485480245771867920067279",
                            "change": "-0.2982634555342546306498361",
                            "unit": "%",
                            "direction": "down",
                            "period": "2026-10-01",
                            "previous_period": "2026-09-01",
                        }
                    ],
                },
            )
        )
        for company_id, cik, debt, cash in [
            (1, "0000016058", 100, 20),
            (second.id, "0000789019", 5, 30),
        ]:
            for metric, value in [("debt", debt), ("cash", cash)]:
                s.add(
                    Observation(
                        company_id=company_id,
                        identity=f"{company_id}-{metric}",
                        metric=metric,
                        period_end="2026-09-30",
                        kind="instant",
                        value=value,
                        unit="USD",
                        active=True,
                        payload={
                            "sources": [
                                {
                                    "filed": "2026-10-22",
                                    "accn": f"{cik}-26-000001",
                                }
                            ]
                        },
                    )
                )
        s.add(
            Observation(
                company_id=second.id,
                identity="msft-operating-margin",
                metric="operating_margin",
                period_end="2026-09-30",
                kind="quarter",
                value=12.3,
                unit="%",
                active=True,
                payload={"sources": [{"filed": "2026-10-22"}]},
            )
        )
        second_id = second.id

    url = "/api/calendar?start=2026-11-01&end=2026-11-30"
    no_selection = api.get(url).json()["events"]
    assert no_selection and all(event["company_context"] == [] for event in no_selection)

    selected = api.get(url + f"&context_company_id={second_id}").json()["events"]
    fed = next(event for event in selected if event["category"] == "fed")
    assert "why_it_matters" in fed["outcome"]["metrics"][0]
    assert "borrowing" in fed["outcome"]["metrics"][0]["why_it_matters"]
    assert len(fed["company_context"]) == 1
    context = fed["company_context"][0]
    assert context["ticker"] == "MSFT"
    assert "Lower rates" in context["headline"]
    assert "long-term debt above cash" not in context["relation"].lower()
    assert {fact["metric"] for fact in context["facts"]} == {
        "debt",
        "cash",
        "operating_margin",
    }
    inflation = next(event for event in selected if event["category"] == "inflation")
    assert len(inflation["company_context"]) == 1
    assert "Slower consumer inflation" in inflation["company_context"][0]["headline"]
    assert "household spending" in inflation["company_context"][0]["relation"]
    assert api.get(url + "&context_company_id=999").status_code == 404


def test_completed_full_comparison_is_reused_without_queueing(
    api, sessions, monkeypatch
):
    from app.models import Filing, ThesisVersion, Analysis, Job, Review
    from app.reviews import ANALYSIS_VERSION as PROMPT_VERSION
    from app.config import settings
    from app import main
    from sqlalchemy import select, func

    monkeypatch.setattr(settings, "groq_api_key", "test")
    monkeypatch.setattr(main, "require_sec", lambda: None)
    with sessions.begin() as s:
        filing = Filing(
            company_id=1,
            accession="test",
            form="10-Q",
            filed="2026-10-22",
            report_date="2026-09-30",
            document="test.htm",
        )
        thesis = ThesisVersion(
            company_id=1, version=1, body="Warehouse expansion supports sales growth."
        )
        s.add_all([filing, thesis])
        s.flush()
        review = Review(
            company_id=1,
            filing_id=filing.id,
            thesis_id=thesis.id,
            model=settings.groq_model,
            version=PROMPT_VERSION,
            status="complete",
            state={"filing_ready": True, "call": {"status": "included"}},
        )
        s.add(review)
        s.flush()
        analysis = Analysis(
            review_id=review.id,
            stage_key="test",
            company_id=1,
            filing_id=filing.id,
            thesis_id=thesis.id,
            model=settings.groq_model,
            prompt_version=PROMPT_VERSION,
            result={
                "scope": "Complete call",
                "observations": [],
                "transcript": {
                    "status": "included",
                    "coverage": {"full_transcript": True},
                },
            },
        )
        s.add(analysis)
        s.flush()
        fid = filing.id
    result = api.post("/api/companies/1/analyze", json={"filing_id": fid})
    assert result.status_code == 202 and result.json()["cached"]
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Job)) == 0


def test_saved_source_is_on_demand_and_not_in_polling_payload(api,sessions):
    from app.models import Review,Snapshot,Filing,ThesisVersion
    with sessions.begin() as s:
        f=Filing(company_id=1,accession='0000016058-26-000099',form='10-Q',filed='2026-11-18',report_date='2026-09-30',document='q.htm')
        t=ThesisVersion(company_id=1,version=1,body='Demand will grow.')
        snap=Snapshot(company_id=1,kind='review_call',digest='f'*64,source_url='https://example.org/provider',payload={'symbol':'CACI','quarter':'2026Q3','turns':[{'speaker':'CEO','content':'FULL SOURCE ONLY ON DEMAND'}]})
        s.add_all([f,t,snap]);s.flush()
        r=Review(company_id=1,filing_id=f.id,thesis_id=t.id,model='mock',version='v7-claim-review',state={'call_snapshot_id':snap.id,'private_source':'FULL SOURCE ONLY ON DEMAND'})
        s.add(r);s.flush();rid=r.id
    assert 'FULL SOURCE ONLY ON DEMAND' not in api.get('/api/companies/1').text
    saved=api.get(f'/api/reviews/{rid}/sources/call')
    assert saved.status_code==200 and saved.json()['turns'][0]['content']=='FULL SOURCE ONLY ON DEMAND'
