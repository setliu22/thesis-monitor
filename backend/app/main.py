from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select, text, inspect, func
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError as DatabaseTimeoutError
from sqlalchemy.orm import Session
from .config import settings
from .db import get_session, sec_gate
from .models import (
    Company,
    CalendarCache,
    ThesisVersion,
    RuleVersion,
    Filing,
    Observation,
    Job,
    Analysis,
    Review,
    Snapshot,
    Alert,
    AlertEvent,
    now,
)
from .schemas import CompanyInput, ThesisInput, RuleInput, AnalysisInput
from .sec import SecClient, SecError, valid_identity, filing_path
from .financials import METRICS
from .reviews import latest_status as latest_review_status, recent_earnings_filings
from .jobs import enqueue_refresh
from .rules import latest_rules, evaluate_company

app = FastAPI(title="Thesis Monitor", version="1.0.0")


@app.exception_handler(OperationalError)
@app.exception_handler(DatabaseTimeoutError)
async def database_unavailable(request: Request, exc):
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is temporarily unreachable. Please try again shortly."},
        headers={"Retry-After": "5"},
    )

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    + ([urlparse(settings.app_origin).hostname] if settings.app_origin else []),
)


@app.middleware("http")
async def local_origin(request: Request, call_next):
    if (
        settings.production
        and (
            not settings.app_origin.startswith("https://")
            or len(settings.owner_password) < 24
        )
    ) or (settings.app_origin and not settings.owner_password):
        return JSONResponse(
            status_code=503,
            content={"detail": "Hosted access password is not configured"},
        )
    if settings.owner_password and request.url.path not in ("/health", "/ready"):
        import base64
        import secrets

        try:
            scheme, encoded = request.headers.get("authorization", "").split(" ", 1)
            credentials = base64.b64decode(encoded, validate=True).decode()
            valid = scheme.lower() == "basic" and secrets.compare_digest(
                credentials.encode(), ("owner:" + settings.owner_password).encode()
            )
        except (ValueError, UnicodeError):
            valid = False
        if not valid:
            return JSONResponse(
                status_code=401,
                content={"detail": "Sign in as owner"},
                headers={
                    "WWW-Authenticate": 'Basic realm="Thesis Monitor", charset="UTF-8"'
                },
            )
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and request.headers.get("sec-fetch-site") == "cross-site"
    ):
        return JSONResponse(
            status_code=403, content={"detail": "Cross-site changes are not allowed"}
        )
    origin = request.headers.get("origin")
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin
        not in {
            settings.app_origin,
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        }
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "Request origin is not a local application origin"},
        )
    return await call_next(request)


def record(row):
    return {
        c.key: str(v) if isinstance(v := getattr(row, c.key), Decimal) else v
        for c in inspect(row).mapper.column_attrs
    }


def analysis_record(row):
    data = record(row)
    result = dict(data["result"])
    for key in (
        "supplied_excerpts",
        "passage_catalog",
        "passage_decisions",
        "thesis_claims",
    ):
        result.pop(key, None)
    if result.get("transcript"):
        result["transcript"] = {
            k: v for k, v in result["transcript"].items() if k != "supplied_excerpts"
        }
    if "claim_assessments" in result:
        from .review_summary import SUMMARY_POLICY, current_summary, direct_findings

        summary = current_summary(result)
        if summary is None:
            result.pop("summary", None)
        result["summary_policy"] = SUMMARY_POLICY
        result["summary_eligible"] = next(direct_findings(result), None) is not None
    data["result"] = result
    return data


def company_or_404(s, company_id, lock=False):
    query = select(Company).where(Company.id == company_id, Company.watched.is_(True))
    if lock:
        query = query.with_for_update()
    company = s.scalar(query)
    if not company:
        raise HTTPException(404, "Company not found")
    return company


def require_sec():
    if not valid_identity(settings.sec_user_agent):
        raise HTTPException(
            409,
            "SEC setup needed: set SEC_USER_AGENT in .env to your name and real email, then restart API and worker.",
        )


def source_urls(payload, cik):
    sources = []
    for source in payload.get("sources", []):
        src = source.copy()
        accn = src.get("accn", "")
        if accn and len(accn) == 20 and accn.replace("-", "").isdigit():
            src["url"] = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.html"
            )
        sources.append(src)
    return payload | {"sources": sources}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(s: Session = Depends(get_session)):
    try:
        s.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "Database unavailable")
    return {"status": "ready"}


@app.get("/api/settings")
def configuration():
    return {
        "sec_configured": valid_identity(settings.sec_user_agent),
        "llm_configured": bool(settings.groq_api_key),
        "llm_provider": "Groq",
        "llm_model": settings.groq_model,
        "refresh_seconds": settings.refresh_seconds,
        "metrics": METRICS,
        "calendar_configured": bool(settings.alphavantage_api_key),
        "calendar_provider": "Alpha Vantage",
    }


@app.get("/api/analysis-queue")
def analysis_queue(s: Session = Depends(get_session)):
    counts = {"queued": 0, "running": 0}
    for status, count in s.execute(
        select(Job.status, func.count())
        .where(Job.kind == "analysis", Job.status.in_(counts))
        .group_by(Job.status)
    ):
        counts[status] = count
    quota = s.scalar(select(CalendarCache.payload).where(CalendarCache.provider == "groq:quota:v1")) or {}
    return counts | {
        "groq": {
            "tokens_remaining": quota.get("provider_remaining"),
            "tokens_reset_at": quota.get("provider_reset"),
            "requests_remaining": quota.get("provider_requests_remaining"),
            "requests_reset_at": quota.get("provider_requests_reset"),
        }
    }


@app.get("/api/companies")
def companies(s: Session = Depends(get_session)):
    return [
        record(c)
        for c in s.scalars(
            select(Company).where(Company.watched.is_(True)).order_by(Company.ticker)
        )
    ]


@app.post("/api/companies", status_code=201)
def add_company(data: CompanyInput, s: Session = Depends(get_session)):
    existing = s.scalar(
        select(Company).where(Company.ticker == data.ticker).with_for_update()
    )
    if existing:
        existing.watched = True
        s.commit()
        return record(existing)
    require_sec()
    try:
        identity = SecClient(settings.sec_user_agent, gate=sec_gate).resolve_company(
            data.ticker
        )
    except SecError as exc:
        raise HTTPException(502, str(exc))
    try:
        company = Company(**identity)
        s.add(company)
        s.flush()
        enqueue_refresh(s, company.id)
        s.commit()
    except IntegrityError:
        s.rollback()
        company = s.scalar(select(Company).where(Company.ticker == data.ticker))
        if not company:
            raise
        company.watched = True
        s.commit()
    return record(company)


@app.delete("/api/companies/{company_id}")
def remove_company(company_id: int, s: Session = Depends(get_session)):
    from .models import Delivery, MarketEvent
    from sqlalchemy import or_

    company = company_or_404(s, company_id, True)
    company.watched = False
    for job in s.scalars(
        select(Job)
        .where(Job.company_id == company_id, Job.status.in_(["queued", "running"]))
        .with_for_update()
    ):
        job.status, job.finished_at, job.lease_until = "cancelled", now(), None
    for item in s.scalars(
        select(Delivery)
        .where(
            Delivery.status == "pending",
            or_(
                Delivery.event_id.in_(
                    select(MarketEvent.id).where(MarketEvent.company_id == company_id)
                ),
                Delivery.alert_id.in_(
                    select(Alert.id).where(Alert.company_id == company_id)
                ),
            ),
        )
        .with_for_update()
    ):
        item.status, item.error = "cancelled", "Company removed from watchlist"
    s.commit()
    return {"removed": company_id}


@app.get("/api/companies/{company_id}")
def detail(
    company_id: int,
    background_tasks: BackgroundTasks,
    s: Session = Depends(get_session),
    filing_id: int | None = None,
):
    from .analysis_dispatch import wake_analysis

    background_tasks.add_task(wake_analysis)
    company = company_or_404(s, company_id)
    thesis = s.scalar(
        select(ThesisVersion)
        .where(ThesisVersion.company_id == company_id)
        .order_by(ThesisVersion.version.desc())
        .limit(1)
    )
    observations = [
        source_urls(o.payload, company.cik)
        for o in s.scalars(
            select(Observation)
            .where(Observation.company_id == company_id, Observation.active.is_(True))
            .order_by(Observation.period_end)
        )
    ]
    filings = []
    for f in s.scalars(
        select(Filing)
        .where(Filing.company_id == company_id)
        .order_by(Filing.filed.desc())
        .limit(60)
    ):
        item = record(f)
        try:
            item["url"] = "https://www.sec.gov" + filing_path(
                company.cik, f.accession, f.document
            )
        except SecError:
            item["url"] = None
        filings.append(item)
    alerts = [
        record(a) | {"evidence": source_urls(a.evidence, company.cik)}
        for a in s.scalars(
            select(Alert)
            .where(Alert.company_id == company_id)
            .order_by(Alert.created_at.desc())
            .limit(100)
        )
    ]
    # A quarter-old statement remains current until a new report is due.
    from .earnings import refresh_due, latest_loaded_report

    latest_report = latest_loaded_report(s, company_id)
    stale = company.data_status == "stale" or refresh_due(
        company, datetime.now(timezone.utc), latest_report
    )

    review_status = latest_review_status(s, company_id, filing_id=filing_id)
    recent_filings = recent_earnings_filings(s, company_id)
    recent_reviews = [
        review_status if f.id == review_status.get("filing_id")
        else latest_review_status(s, company_id, filing_id=f.id)
        for f in recent_filings
    ]
    listed_ids = {item["id"] for item in filings}
    filings.extend(record(f) for f in recent_filings if f.id not in listed_ids)
    analysis_rows = list(
        s.scalars(
            select(Analysis)
            .where(Analysis.company_id == company_id)
            .order_by(Analysis.id.desc())
            .limit(10)
        )
    )
    for report_id in {review_status.get("filing_id"), filing_id, *(f.id for f in recent_filings)} - {None}:
        query = select(Analysis).where(
            Analysis.company_id == company_id, Analysis.filing_id == report_id
        )
        if thesis:
            query = query.order_by((Analysis.thesis_id == thesis.id).desc())
        selected_analysis = s.scalar(query.order_by(Analysis.id.desc()).limit(1))
        if selected_analysis and all(
            a.id != selected_analysis.id for a in analysis_rows
        ):
            analysis_rows.append(selected_analysis)
    return {
        "company": record(company) | {"stale": stale},
        "review": review_status,
        "recent_reviews": recent_reviews,
        "thesis": record(thesis) if thesis else None,
        "rules": [record(r) for r in latest_rules(s, company_id)],
        "observations": observations,
        "filings": filings,
        "alerts": alerts,
        "jobs": [
            record(j)
            for j in s.scalars(
                select(Job)
                .where(Job.company_id == company_id)
                .order_by(Job.id.desc())
                .limit(15)
            )
        ],
        "analyses": [analysis_record(a) for a in analysis_rows],
    }


@app.put("/api/companies/{company_id}/thesis")
def save_thesis(company_id: int, data: ThesisInput, s: Session = Depends(get_session)):
    company_or_404(s, company_id, True)
    latest = s.scalar(
        select(ThesisVersion)
        .where(ThesisVersion.company_id == company_id)
        .order_by(ThesisVersion.version.desc())
        .limit(1)
    )
    thesis = ThesisVersion(
        company_id=company_id,
        version=(latest.version + 1 if latest else 1),
        body=data.body,
    )
    s.add(thesis)
    s.flush()
    if thesis.version == 1:
        from .reviews import latest_filing, request_review

        filing = latest_filing(s, company_id)
        if filing:
            try:
                request_review(s, company_id, filing.id)
            except ValueError:
                pass
    s.commit()
    return record(thesis)


def _delete_thesis_versions(s, company_id, versions):
    version_ids = {version.id for version in versions}
    if not version_ids:
        return set()

    reviews = s.scalars(
        select(Review)
        .where(Review.company_id == company_id, Review.thesis_id.in_(version_ids))
        .with_for_update()
    ).all()
    analyses = s.scalars(
        select(Analysis)
        .where(Analysis.company_id == company_id, Analysis.thesis_id.in_(version_ids))
        .with_for_update()
    ).all()
    review_ids = {review.id for review in reviews}
    analysis_ids = {analysis.id for analysis in analyses}

    active_jobs = s.scalars(
        select(Job)
        .where(
            Job.company_id == company_id,
            Job.kind == "analysis",
            Job.status.in_(("queued", "running")),
        )
        .with_for_update()
    ).all()
    for job in active_jobs:
        payload = job.payload or {}
        if payload.get("review_id") in review_ids or payload.get(
            "summary_analysis_id"
        ) in analysis_ids:
            job.status = "cancelled"
            job.error = "The thesis version for this comparison was deleted."
            job.finished_at = now()

    for analysis in analyses:
        s.delete(analysis)
    for review in reviews:
        s.delete(review)
    for version in versions:
        s.delete(version)
    return version_ids


@app.get("/api/companies/{company_id}/thesis/versions")
def thesis_versions(company_id: int, s: Session = Depends(get_session)):
    company_or_404(s, company_id)
    versions = s.scalars(
        select(ThesisVersion)
        .where(ThesisVersion.company_id == company_id)
        .order_by(ThesisVersion.version.desc())
    ).all()
    return [record(version) for version in versions]


@app.get("/api/companies/{company_id}/thesis/versions/{thesis_id}/comparisons")
def thesis_version_comparisons(company_id: int, thesis_id: int, s: Session = Depends(get_session)):
    company_or_404(s, company_id)
    thesis = s.scalar(select(ThesisVersion).where(
        ThesisVersion.company_id == company_id, ThesisVersion.id == thesis_id,
    ))
    if thesis is None:
        raise HTTPException(404, "Thesis version not found")
    rows = s.execute(
        select(Analysis, Filing).join(Filing, Analysis.filing_id == Filing.id)
        .where(Analysis.company_id == company_id, Analysis.thesis_id == thesis_id,
               Filing.company_id == company_id)
        .order_by(Filing.report_date.desc(), Filing.filed.desc(), Analysis.id.desc())
    )
    latest = {}
    for analysis, filing in rows:
        latest.setdefault(filing.id, (analysis, filing))
    return {
        "analyses": [analysis_record(analysis) for analysis, _ in latest.values()],
        "filings": [record(filing) for _, filing in latest.values()],
    }


@app.delete("/api/companies/{company_id}/thesis/versions/{thesis_id}")
def delete_thesis_version(
    company_id: int, thesis_id: int, s: Session = Depends(get_session)
):
    company_or_404(s, company_id, True)
    version = s.scalar(
        select(ThesisVersion).where(
            ThesisVersion.company_id == company_id, ThesisVersion.id == thesis_id
        )
    )
    if not version:
        raise HTTPException(404, "Thesis version not found")
    deleted = _delete_thesis_versions(s, company_id, [version])
    s.flush()
    current = s.scalar(
        select(ThesisVersion)
        .where(ThesisVersion.company_id == company_id)
        .order_by(ThesisVersion.version.desc())
        .limit(1)
    )
    s.commit()
    return {"deleted_id": next(iter(deleted)), "current": record(current) if current else None}


@app.delete("/api/companies/{company_id}/thesis/versions")
def delete_thesis_history(company_id: int, s: Session = Depends(get_session)):
    company_or_404(s, company_id, True)
    versions = s.scalars(
        select(ThesisVersion)
        .where(ThesisVersion.company_id == company_id)
        .with_for_update()
    ).all()
    deleted = _delete_thesis_versions(s, company_id, versions)
    s.commit()
    return {"deleted": len(deleted), "current": None}


def write_rule(company_id, data, s, group_key=None):
    company_or_404(s, company_id, True)
    previous = (
        s.scalar(
            select(RuleVersion)
            .where(
                RuleVersion.company_id == company_id, RuleVersion.group_key == group_key
            )
            .order_by(RuleVersion.version.desc())
            .limit(1)
        )
        if group_key
        else None
    )
    if group_key and not previous:
        raise HTTPException(404, "Rule not found")
    rule = RuleVersion(
        company_id=company_id,
        group_key=group_key or uuid4().hex,
        version=previous.version + 1 if previous else 1,
        **data.model_dump(),
    )
    s.add(rule)
    s.flush()
    evaluate_company(s, company_id)
    s.commit()
    return record(rule)


@app.post("/api/companies/{company_id}/rules", status_code=201)
def add_rule(company_id: int, data: RuleInput, s: Session = Depends(get_session)):
    return write_rule(company_id, data, s)


@app.put("/api/companies/{company_id}/rules/{group_key}")
def edit_rule(
    company_id: int, group_key: str, data: RuleInput, s: Session = Depends(get_session)
):
    return write_rule(company_id, data, s, group_key)


@app.post("/api/companies/{company_id}/refresh", status_code=202)
def refresh(company_id: int, s: Session = Depends(get_session)):
    company_or_404(s, company_id)
    require_sec()
    job = enqueue_refresh(s, company_id)
    s.commit()
    return record(job)


@app.post("/api/companies/{company_id}/evaluate")
def evaluate(company_id: int, s: Session = Depends(get_session)):
    company_or_404(s, company_id)
    count = evaluate_company(s, company_id)
    s.commit()
    return {"created": count}


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int, s: Session = Depends(get_session)):
    alert = s.scalar(select(Alert).where(Alert.id == alert_id).with_for_update())
    if not alert:
        raise HTTPException(404, "Alert not found")
    if not alert.acknowledged_at:
        alert.acknowledged_at = now()
        s.add(AlertEvent(alert_id=alert_id, kind="acknowledged"))
    s.commit()
    return record(alert)


@app.get("/api/jobs")
def jobs(s: Session = Depends(get_session)):
    return [
        record(j) for j in s.scalars(select(Job).order_by(Job.id.desc()).limit(100))
    ]


@app.post("/api/companies/{company_id}/analyze", status_code=202)
def analyze(
    company_id: int,
    data: AnalysisInput,
    background_tasks: BackgroundTasks,
    s: Session = Depends(get_session),
):
    company_or_404(s, company_id, True)
    require_sec()
    from .reviews import request_review
    from .analysis_dispatch import wake_analysis

    try:
        if data.recent_periods and not (data.rerun or data.retry_connection):
            filings = recent_earnings_filings(s, company_id)
            if not filings:
                raise ValueError("No eligible earnings filings are available.")
            outcomes = [request_review(s, company_id, filing.id, manual=True) for filing in filings]
            s.commit()
            if any(outcome["job"] for outcome in outcomes):
                background_tasks.add_task(wake_analysis)
            return {
                "periods": len(filings),
                "cached": all(outcome["cached"] for outcome in outcomes),
            }
        outcome = request_review(
            s,
            company_id,
            data.filing_id,
            manual=True,
            rerun=data.rerun,
            retry_connection=data.retry_connection,
        )
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(
            409
            if "thesis" in message.lower() or "configure" in message.lower()
            else 422,
            message,
        ) from exc
    s.commit()
    if data.retry_connection and not outcome["job"]:
        return {"status": "connection_retry_not_needed"}
    if outcome["job"]:
        background_tasks.add_task(wake_analysis)
        return record(outcome["job"]) | {"review_id": outcome["review"].id}
    return {
        "cached": outcome["cached"],
        "review_id": outcome["review"].id,
        "status": outcome["review"].status,
    }


@app.post("/api/companies/{company_id}/analyses/{analysis_id}/summary", status_code=202)
def summarize_review(
    company_id: int,
    analysis_id: int,
    background_tasks: BackgroundTasks,
    automatic: bool = False,
    s: Session = Depends(get_session),
):
    from .analysis_dispatch import wake_analysis
    from .review_summary import request_summary

    try:
        job = request_summary(s, company_id, analysis_id, automatic=automatic)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    s.commit()
    if job:
        background_tasks.add_task(wake_analysis)
        return record(job)
    return {"cached": True}


@app.get("/api/reviews/{review_id}/sources/{source_kind}")
def review_source(review_id: int, source_kind: str, s: Session = Depends(get_session)):
    review = s.get(Review, review_id)
    if not review or source_kind not in ("filing", "call"):
        raise HTTPException(404, "Saved review source not found")
    snapshot_id = (review.state or {}).get(source_kind + "_snapshot_id")
    snap = s.get(Snapshot, snapshot_id) if snapshot_id else None
    if not snap or snap.company_id != review.company_id:
        raise HTTPException(404, "This source has not been saved yet")
    if source_kind == "call":
        return {
            "kind": "call",
            "provider": "Alpha Vantage",
            "symbol": snap.payload.get("symbol"),
            "quarter": snap.payload.get("quarter"),
            "turns": snap.payload.get("turns", []),
            "source_url": snap.source_url,
        }
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(snap.payload.get("html", ""), "html.parser")
    for el in soup(["script", "style", "noscript", "ix:hidden", "ix:header"]):
        el.decompose()
    return {
        "kind": "filing",
        "text": soup.get_text(" ", strip=True),
        "source_url": snap.source_url,
    }


@app.get("/api/notifications")
def notifications(s: Session = Depends(get_session)):
    from .models import Delivery
    from .notifications import configured

    return {
        "configured": configured(),
        "recipient": settings.alert_email,
        "deliveries": [
            record(row)
            for row in s.scalars(
                select(Delivery).order_by(Delivery.id.desc()).limit(50)
            )
        ],
    }


from .calendar_api import router as calendar_router

app.include_router(calendar_router)


@app.get("/api/companies/{company_id}/metric-mappings")
def metric_mappings(company_id: int, s: Session = Depends(get_session)):
    from .mappings import latest_registry

    company_or_404(s, company_id)
    return latest_registry(s, company_id)


@app.delete("/api/companies/{company_id}/metric-mappings/{mapping_id}")
def disable_metric_mapping(
    company_id: int, mapping_id: str, s: Session = Depends(get_session)
):
    from .mappings import latest_registry, save_registry
    from .jobs import enqueue_refresh
    import copy

    company_or_404(s, company_id, True)
    registry = copy.deepcopy(latest_registry(s, company_id))
    item = next((m for m in registry["mappings"] if m["id"] == mapping_id), None)
    if item is None:
        raise HTTPException(404, "Mapping not found")
    item["status"] = "disabled"
    save_registry(s, company_id, registry)
    enqueue_refresh(s, company_id)
    s.commit()
    return {"disabled": mapping_id}


@app.post("/api/companies/{company_id}/metric-mappings/{mapping_id}/approve")
def approve_metric_mapping(
    company_id: int, mapping_id: str, s: Session = Depends(get_session)
):
    from .mappings import latest_registry, save_registry
    import copy

    company_or_404(s, company_id, True)
    registry = copy.deepcopy(latest_registry(s, company_id))
    item = next((m for m in registry["mappings"] if m["id"] == mapping_id), None)
    if item is None or item["status"] != "pending":
        raise HTTPException(409, "Choose a pending mapping")
    if not item.get("structural_checks_passed"):
        raise HTTPException(
            409,
            "Source units and multiple reporting periods must pass validation before approval",
        )
    item["status"] = "accepted"
    item["reviewed_at"] = now()
    item["validation"] = (
        "Definition reviewed by owner; source units and multiple reporting periods validated"
    )
    save_registry(s, company_id, registry)
    enqueue_refresh(s, company_id)
    s.commit()
    return {"approved": mapping_id}


# Production image includes the Vite build. API routes are registered first.
from pathlib import Path
from fastapi.staticfiles import StaticFiles

if Path("static").is_dir():
    app.mount("/", StaticFiles(directory="static", html=True), name="frontend")
