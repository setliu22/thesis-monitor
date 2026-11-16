from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select, text, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings
from .db import get_session, sec_gate
from .models import (
    Company,
    ThesisVersion,
    RuleVersion,
    Filing,
    Observation,
    Job,
    Analysis,
    Alert,
    AlertEvent,
    now,
)
from .schemas import CompanyInput, ThesisInput, RuleInput, AnalysisInput
from .sec import SecClient, SecError, valid_identity, filing_path
from .financials import METRICS
from .jobs import enqueue_refresh
from .rules import latest_rules, evaluate_company

app = FastAPI(title="Thesis Monitor", version="1.0.0")
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


def company_or_404(s, company_id, lock=False):
    query = select(Company).where(Company.id == company_id)
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


@app.get("/api/companies")
def companies(s: Session = Depends(get_session)):
    return [record(c) for c in s.scalars(select(Company).order_by(Company.ticker))]


@app.post("/api/companies", status_code=201)
def add_company(data: CompanyInput, s: Session = Depends(get_session)):
    existing = s.scalar(select(Company).where(Company.ticker == data.ticker))
    if existing:
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
    return record(company)


@app.get("/api/companies/{company_id}")
def detail(company_id: int, s: Session = Depends(get_session)):
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

    return {
        "company": record(company) | {"stale": stale},
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
        "analyses": [
            record(a)
            for a in s.scalars(
                select(Analysis)
                .where(Analysis.company_id == company_id)
                .order_by(Analysis.id.desc())
                .limit(10)
            )
        ],
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
    s.commit()
    return record(thesis)


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
def analyze(company_id: int, data: AnalysisInput, s: Session = Depends(get_session)):
    company_or_404(s, company_id, True)
    require_sec()
    if not settings.groq_api_key:
        raise HTTPException(
            409, "Filing analysis needs GROQ_API_KEY in the server environment"
        )
    filing = s.get(Filing, data.filing_id)
    if (
        not filing
        or filing.company_id != company_id
        or filing.form not in ("10-K", "10-Q", "10-K/A", "10-Q/A")
    ):
        raise HTTPException(422, "Choose a 10-K or 10-Q filing for this company")
    thesis = s.scalar(
        select(ThesisVersion)
        .where(ThesisVersion.company_id == company_id)
        .order_by(ThesisVersion.version.desc())
        .limit(1)
    )
    if not thesis:
        raise HTTPException(409, "Save your thesis before requesting analysis")
    job = enqueue_refresh(
        s, company_id, "analysis", {"filing_id": filing.id, "thesis_id": thesis.id}
    )
    s.commit()
    return record(job)


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

# Production image includes the Vite build. API routes are registered first.
from pathlib import Path
from fastapi.staticfiles import StaticFiles

if Path("static").is_dir():
    app.mount("/", StaticFiles(directory="static", html=True), name="frontend")
