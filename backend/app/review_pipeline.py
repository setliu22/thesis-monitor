"""Versioned filing-first reviews; immutable inputs and idempotent publications."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from .config import settings
from .db import sec_gate
from .models import Company, Review, Filing, ThesisVersion, Snapshot, Analysis, now
from .financials import identity
from .jobs import owned_job, analysis_progress
from .analysis import AnalysisConfig
from .groq_runtime import GroqRunner, Limits
from .sec import SecClient, filing_path
from .transcripts import fiscal_quarter, fetch_transcript
from .feed_cache import FeedError
from . import evidence
from .local_embeddings import embed
from .reviews import ANALYSIS_VERSION, recent_earnings_periods, require_recent_earnings


def _guard(s, job, owner):
    s.scalar(select(Company).where(Company.id == job.company_id).with_for_update())
    review = s.scalar(
        select(Review).where(Review.id == job.payload["review_id"]).with_for_update()
    )
    owned_job(s, job.id, owner)
    if not review or (
        review.company_id,
        review.filing_id,
        review.thesis_id,
        review.model,
        review.version,
    ) != (
        job.company_id,
        job.payload["filing_id"],
        job.payload["thesis_id"],
        job.payload["model"],
        job.payload["analysis_version"],
    ):
        raise ValueError("Review job identity changed; request a new review.")
    return review


def _state(sessions, job, owner, changes, status=None, next_attempt=None):
    with sessions.begin() as s:
        review = _guard(s, job, owner)
        state = dict(review.state or {})
        state.update(changes)
        review.state = state
        if status:
            review.status = status
        review.next_attempt = next_attempt
        review.updated_at = now()
        review.last_error = None
        return state


def _pin(sessions, job, owner, key, kind, payload, url):
    digest = identity(payload)
    with sessions.begin() as s:
        review = _guard(s, job, owner)
        state = dict(review.state or {})
        if state.get(key):
            return state[key]
        snap = s.scalar(
            select(Snapshot).where(
                Snapshot.company_id == job.company_id,
                Snapshot.kind == kind,
                Snapshot.digest == digest,
            )
        )
        if not snap:
            snap = Snapshot(
                company_id=job.company_id,
                kind=kind,
                digest=digest,
                payload=payload,
                source_url=url,
            )
            s.add(snap)
            s.flush()
        state[key] = snap.id
        if key == "filing_snapshot_id":
            state["source_url"] = url
        review.state = state
        review.updated_at = now()
        return snap.id


def _source(sessions, snapshot_id):
    with sessions() as s:
        return s.get(Snapshot, snapshot_id).payload


def _prior(sessions, review, filing, claims):
    """Only same form and adjacent comparable reporting periods; no invented delta."""
    if not filing.report_date:
        return []
    with sessions() as s:
        rows = s.execute(
            select(Review, Filing)
            .join(Filing, Review.filing_id == Filing.id)
            .where(
                Review.company_id == review.company_id,
                Filing.form == filing.form,
                Filing.report_date < filing.report_date,
            )
            .order_by(Filing.report_date.desc())
        ).all()
        recent = recent_earnings_periods(s, review.company_id)
        for old, prior_filing in rows:
            if prior_filing.report_date not in recent:
                continue
            gap = (
                datetime.fromisoformat(filing.report_date)
                - datetime.fromisoformat(prior_filing.report_date)
            ).days
            if not (
                (350 <= gap <= 380)
                if filing.form.startswith("10-K")
                else (60 <= gap <= 120)
            ):
                continue
            state = old.state or {}

            def claim_key(c):
                return identity({k: v for k, v in c.items() if k != "id"})

            texts = {c["id"]: claim_key(c) for c in state.get("claims", [])}
            matching = {claim_key(c): c["id"] for c in claims}
            found = []
            for item in state.get("filing_evidence", []) + state.get(
                "call_evidence", []
            ):
                text = texts.get(item.get("claim_id"))
                if text in matching:
                    found.append(
                        dict(
                            item,
                            id=f"P{old.id}-{item['id']}",
                            claim_id=matching[text],
                            comparable=True,
                            prior_review_id=old.id,
                        )
                    )
            if found:
                return found
    return []


def _publish(
    sessions, job, owner, state, filing, thesis, claims, assessments, items, stage
):
    stage_key = identity(
        {
            "stage": stage,
            "filing_snapshot": state.get("filing_snapshot_id"),
            "call_snapshot": state.get("call_snapshot_id"),
            "claims": claims,
            "assessments": assessments,
        }
    )
    with sessions.begin() as s:
        review = _guard(s, job, owner)
        existing = s.scalar(
            select(Analysis.id).where(
                Analysis.review_id == review.id, Analysis.stage_key == stage_key
            )
        )
        if existing:
            saved = s.get(Analysis, existing)
            saved.result = dict(saved.result) | {
                "call": state.get("call", {}),
                "coverage": {
                    "filing": state.get("filing_coverage", {}),
                    "call": state.get("call_coverage"),
                },
            }
            return existing
        result = {
            "review_id": review.id,
            "stage": stage,
            "filing_accession": filing.accession,
            "thesis_version": thesis.version,
            "source_url": state.get("source_url"),
            "provider": "groq",
            "scope": "Selective contextual filing retrieval; available call coverage is shown separately.",
            "review_status": "unverified",
            "claims": claims,
            "no_testable_claims": not claims,
            "claim_assessments": assessments,
            "evidence": items,
            "coverage": {
                "filing": state.get("filing_coverage", {}),
                "call": state.get("call_coverage"),
            },
            "call": state.get("call", {}),
            "observations": [],
            "rejected_count": 0,
            "job_id": job.id,
        }
        analysis = Analysis(
            company_id=review.company_id,
            filing_id=review.filing_id,
            thesis_id=review.thesis_id,
            review_id=review.id,
            stage_key=stage_key,
            model=review.model,
            prompt_version=review.version,
            result=result,
        )
        s.add(analysis)
        s.flush()
        return analysis.id


def run_review(sessions, job, owner):
    with sessions.begin() as s:
        review = _guard(s, job, owner)
        if review.version != ANALYSIS_VERSION:
            raise ValueError(
                "This review version is unsupported; request a new versioned review."
            )
        review.status = "processing"
        review.updated_at = now()
        review.last_error = None
        review.next_attempt = None
        state = dict(review.state or {})
        filing = s.get(Filing, review.filing_id)
        require_recent_earnings(s, filing)
        thesis = s.get(ThesisVersion, review.thesis_id)
        company = s.get(Company, review.company_id)
        if not settings.groq_api_key:
            from .groq_runtime import PermanentFailure

            raise PermanentFailure(
                "Configure GROQ_API_KEY and explicitly retry this review."
            )
        config = AnalysisConfig(settings.groq_api_key, review.model)
    runner = GroqRunner(
        sessions,
        config.api_key,
        limits=Limits(
            tpm=settings.groq_tokens_per_minute,
            tpd=settings.groq_tokens_per_day,
            rpm=settings.groq_requests_per_minute,
            rpd=settings.groq_requests_per_day,
        ),
    )

    phase = "filing"

    def progress(value):
        analysis_progress(
            sessions,
            job.id,
            owner,
            phase + "_" + value.get("stage", "evidence"),
            value.get("completed", 0),
            value.get("total", 0),
        )

    signature = identity(
        {
            "engine": evidence.VERSION,
            "evidence_prompt": evidence.STAGE_A_PROMPT,
            "assessment_prompt": evidence.STAGE_B_PROMPT,
        }
    )
    if state.get("stage_signature") and state["stage_signature"] != signature:
        from .groq_runtime import PermanentFailure

        raise PermanentFailure(
            "This saved review uses different assessment instructions. Start a new versioned review after updating the analysis version."
        )
    if not state.get("stage_signature"):
        state = _state(sessions, job, owner, {"stage_signature": signature, "compact_evidence": True})
    if "claims" not in state:
        analysis_progress(sessions, job.id, owner, "thesis_claims", 0, 1)
        claims = evidence.select_thesis_claims(thesis.body, config, runner)
        state = _state(
            sessions, job, owner, {"claims": claims, "input_version": ANALYSIS_VERSION}
        )
    claims = state["claims"]
    if not claims:
        _publish(sessions, job, owner, state, filing, thesis, [], [], [], "filing")
        _state(sessions, job, owner, {}, status="complete")
        analysis_progress(sessions, job.id, owner, "thesis_claims", 1, 1)
        return
    if not state.get("filing_snapshot_id"):
        path = filing_path(company.cik, filing.accession, filing.document)
        raw = SecClient(settings.sec_user_agent, gate=sec_gate).fetch_text(path)
        sid = _pin(
            sessions,
            job,
            owner,
            "filing_snapshot_id",
            "review_filing",
            {"html": raw, "accession": filing.accession, "period": filing.report_date},
            "https://www.sec.gov" + path,
        )
        state = _state(
            sessions,
            job,
            owner,
            {"filing_snapshot_id": sid, "source_url": "https://www.sec.gov" + path},
        )
    filing_source = _source(sessions, state["filing_snapshot_id"])
    raw = filing_source["html"]
    if not state.get("source_url"):
        with sessions() as s:
            source_url = s.get(Snapshot, state["filing_snapshot_id"]).source_url
        state = _state(sessions, job, owner, {"source_url": source_url})
    if "prior_evidence" not in state:
        state = _state(
            sessions,
            job,
            owner,
            {"prior_evidence": _prior(sessions, review, filing, claims)},
        )
    with sessions() as s:
        recent = recent_earnings_periods(s, review.company_id)
    prior = [item for item in state["prior_evidence"] if item.get("period") in recent]
    if not state.get("filing_ready"):
        selected = state.get("filing_selection")
        if selected is None:
            selected = evidence.filing_targets(
                raw, claims, state["source_url"], filing.report_date,
                embed=embed, legacy=not state.get("compact_evidence", False),
            )
            state = _state(sessions, job, owner, {"filing_selection": selected})
        found = state.get("filing_evidence")
        if found is None:
            found = evidence.find_evidence(
                selected["targets"], claims, config, runner, progress,
                compact=state.get("compact_evidence", False),
            )
            state = _state(sessions, job, owner, {"filing_evidence": found})
        assessments = evidence.assess_claims(
            claims, found, config, runner, prior=prior, progress=progress
        )
        deadline = (
            datetime.fromisoformat(filing.filed).replace(tzinfo=timezone.utc)
            + timedelta(days=settings.transcript_followup_days)
        ).isoformat()
        state = _state(
            sessions,
            job,
            owner,
            {
                "filing_evidence": found,
                "filing_coverage": selected["coverage"],
                "filing_assessments": assessments,
                "filing_ready": True,
                "filing_status": "ready",
                "call": {"status": "pending", "deadline": deadline},
            },
            status="filing_ready",
        )
        _publish(
            sessions,
            job,
            owner,
            state,
            filing,
            thesis,
            claims,
            assessments,
            found + prior,
            "filing",
        )
    else:
        # Repair publication/acknowledgment crash boundary without redoing model work.
        _publish(
            sessions,
            job,
            owner,
            state,
            filing,
            thesis,
            claims,
            state["filing_assessments"],
            state["filing_evidence"] + prior,
            "filing",
        )
    quarter = state.get("fiscal_quarter") or fiscal_quarter(raw)
    if quarter and not state.get("fiscal_quarter"):
        state = _state(
            sessions, job, owner, {"fiscal_quarter": quarter}, status="filing_ready"
        )
    if not quarter or not settings.alphavantage_api_key:
        reason = (
            "No verified fiscal quarter is available in the filing."
            if not quarter
            else "Configure Alpha Vantage transcript access to add the matching call."
        )
        status = "unavailable" if not quarter else "configuration_missing"
        state = _state(
            sessions,
            job,
            owner,
            {"call": dict(state.get("call", {}), status=status, reason=reason)},
            status="complete",
        )
        _publish(
            sessions,
            job,
            owner,
            state,
            filing,
            thesis,
            claims,
            state["filing_assessments"],
            state["filing_evidence"] + prior,
            "filing",
        )
        return
    if not state.get("call_snapshot_id"):
        if (
            state.get("call", {}).get("probed")
            and state["call"].get("deadline", "") <= now()
        ):
            state = _state(
                sessions,
                job,
                owner,
                {
                    "call": dict(
                        state["call"],
                        status="unavailable",
                        reason="The bounded transcript follow-up window ended.",
                        next_attempt=None,
                    )
                },
                status="complete",
            )
            _publish(
                sessions,
                job,
                owner,
                state,
                filing,
                thesis,
                claims,
                state["filing_assessments"],
                state["filing_evidence"] + prior,
                "filing",
            )
            return
        try:
            payload = fetch_transcript(
                company.ticker, quarter, settings.alphavantage_api_key, sessions
            )
        except FeedError as exc:
            kind = getattr(exc, "kind", "pending")
            if kind == "provider":
                from .groq_runtime import Deferred

                raise Deferred(
                    3600,
                    "The transcript provider is temporarily unavailable. The filing review is ready.",
                    kind="provider",
                ) from None
            if kind == "malformed":
                raise ValueError(
                    "The transcript provider returned invalid evidence. The filing review remains available; retry after the source is corrected."
                ) from None
            if kind in ("configuration", "unavailable"):
                state = _state(
                    sessions,
                    job,
                    owner,
                    {
                        "call": dict(
                            state["call"],
                            status="configuration_missing"
                            if kind == "configuration"
                            else "unavailable",
                            reason=str(exc),
                            next_attempt=None,
                        )
                    },
                    status="complete",
                )
                _publish(
                    sessions,
                    job,
                    owner,
                    state,
                    filing,
                    thesis,
                    claims,
                    state["filing_assessments"],
                    state["filing_evidence"] + prior,
                    "filing",
                )
                return
            deadline = state["call"].get("deadline")
            retry = bool(deadline and now() < deadline)
            next_at = (
                min(
                    (
                        datetime.now(timezone.utc)
                        + timedelta(hours=settings.transcript_retry_hours)
                    ).isoformat(),
                    deadline,
                )
                if retry
                else None
            )
            state = _state(
                sessions,
                job,
                owner,
                {
                    "call": dict(
                        state["call"],
                        status="pending" if retry else "unavailable",
                        probed=True,
                        reason=str(exc),
                        next_attempt=next_at,
                    )
                },
                status="filing_ready" if retry else "complete",
                next_attempt=next_at,
            )
            _publish(
                sessions,
                job,
                owner,
                state,
                filing,
                thesis,
                claims,
                state["filing_assessments"],
                state["filing_evidence"] + prior,
                "filing",
            )
            return
        sid = _pin(
            sessions,
            job,
            owner,
            "call_snapshot_id",
            "review_call",
            payload,
            payload["source_url"],
        )
        state = _state(
            sessions,
            job,
            owner,
            {"call_snapshot_id": sid, "call": dict(state["call"], status="processing")},
            status="filing_ready",
        )
    phase = "call"
    payload = _source(sessions, state["call_snapshot_id"])
    if "call_evidence" not in state:
        selected = state.get("call_selection")
        if selected is None:
            selected = evidence.retrieve_call_targets(payload, claims, filing.report_date, embed=embed)
            state = _state(sessions, job, owner, {"call_selection": selected})
        found = evidence.find_evidence(
            selected["targets"], claims, config, runner, progress,
            compact=state.get("compact_evidence", False),
        )
        state = _state(
            sessions,
            job,
            owner,
            {"call_evidence": found, "call_coverage": selected["coverage"]},
            status="filing_ready",
        )
    phase = "combined"
    combined = state["filing_evidence"] + state["call_evidence"]
    assessments = evidence.assess_claims(
        claims, combined, config, runner, prior=prior, progress=progress
    )
    state = _state(
        sessions,
        job,
        owner,
        {
            "combined_assessments": assessments,
            "call": dict(state["call"], status="included", reason=None),
        },
        status="complete",
    )
    _publish(
        sessions,
        job,
        owner,
        state,
        filing,
        thesis,
        claims,
        assessments,
        combined + prior,
        "combined",
    )
