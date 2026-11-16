from sqlalchemy import select, update
from .models import Company, Snapshot, Filing, Fact, Observation, now
from .financials import identity, TAGS, INSTANT_TAGS
from .rules import evaluate_company
from .config import settings
from .jobs import owned_job
from .mappings import (
    latest_registry,
    save_registry,
    investigate,
    normalize_mapped,
    filing_facts,
    investigation_due,
    period_anchor,
    MAPPABLE,
)


def snapshot(s, company_id, kind, path, data):
    digest = identity(data)
    if not s.scalar(
        select(Snapshot.id).where(
            Snapshot.company_id == company_id,
            Snapshot.kind == kind,
            Snapshot.digest == digest,
        )
    ):
        host = "www.sec.gov" if path.startswith("/Archives/") else "data.sec.gov"
        s.add(
            Snapshot(
                company_id=company_id,
                kind=kind,
                digest=digest,
                source_url=f"https://{host}{path}",
                payload=data,
            )
        )


def ingest_company(sessions, company_id, client, job_id=None, owner=None):
    def guard(s):
        # Company first is the common lock order; then job ownership.
        company = s.scalar(
            select(Company).where(Company.id == company_id).with_for_update()
        )
        if job_id:
            owned_job(s, job_id, owner)
        return company

    with sessions.begin() as s:
        company = guard(s)
        company.last_attempt = now()
        cik = company.cik
    try:
        path = f"/submissions/CIK{cik}.json"
        submissions = client.fetch_json(path)
        with sessions.begin() as s:
            guard(s)
            snapshot(s, company_id, "submissions", path, submissions)
            recent = submissions.get("filings", {}).get("recent", {})
            for i, accession in enumerate(recent.get("accessionNumber", [])):
                form = recent["form"][i]
                if form not in ("10-K", "10-Q", "8-K", "10-K/A", "10-Q/A"):
                    continue
                if s.scalar(
                    select(Filing.id).where(
                        Filing.company_id == company_id, Filing.accession == accession
                    )
                ):
                    continue
                s.add(
                    Filing(
                        company_id=company_id,
                        accession=accession,
                        form=form,
                        filed=recent["filingDate"][i],
                        report_date=recent.get(
                            "reportDate", [""] * len(recent["form"])
                        )[i],
                        document=recent["primaryDocument"][i],
                    )
                )
        path = f"/api/xbrl/companyfacts/CIK{cik}.json"
        facts = client.fetch_json(path)
        with sessions() as s:
            registry = latest_registry(s, company_id)
        raw_facts = facts
        baseline = normalize_mapped(facts, registry)
        anchor = period_anchor(facts)
        missing = [
            metric
            for metric in MAPPABLE
            if not any(
                o["metric"] == metric and o["end"] == anchor and o["value"] is not None
                for o in baseline
            )
        ]
        needs_saved_source = any(
            m["status"] == "accepted"
            and m["tag"] not in facts.get("facts", {}).get(m["namespace"], {})
            for m in registry.get("mappings", [])
        )
        if anchor and (
            investigation_due(registry, anchor, missing) or needs_saved_source
        ):
            # Company Facts omits issuer extensions. Inspect only the latest K/Q,
            # preserving structured contexts and excluding dimensional facts.
            from .sec import filing_path, SecError

            recent = submissions.get("filings", {}).get("recent", {})
            index = next(
                (
                    i
                    for i, form in enumerate(recent.get("form", []))
                    if form in ("10-K", "10-Q")
                ),
                None,
            )
            if index is not None and (settings.groq_api_key or needs_saved_source):
                try:
                    filing_url = filing_path(
                        cik,
                        recent["accessionNumber"][index],
                        recent["primaryDocument"][index],
                    )
                    with sessions() as s:
                        cached = s.scalar(
                            select(Snapshot)
                            .where(
                                Snapshot.company_id == company_id,
                                Snapshot.kind == "mapping_filing",
                                Snapshot.source_url
                                == "https://www.sec.gov" + filing_url,
                            )
                            .order_by(Snapshot.id.desc())
                        )
                        html = cached.payload["html"] if cached else None
                    if html is None:
                        html = client.fetch_text(filing_url)
                    additions = filing_facts(
                        html,
                        recent["accessionNumber"][index],
                        recent["filingDate"][index],
                        recent["form"][index],
                    )
                    facts = dict(facts) | {
                        "facts": {
                            ns: dict(tags)
                            for ns, tags in facts.get("facts", {}).items()
                        }
                    }
                    for ns, tags in additions.items():
                        target = facts["facts"].setdefault(ns, {})
                        for tag, body in tags.items():
                            target.setdefault(tag, body)
                    with sessions.begin() as s:
                        guard(s)
                        snapshot(
                            s, company_id, "mapping_filing", filing_url, {"html": html}
                        )
                except (SecError, ValueError, KeyError):
                    pass  # SEC access failure must not discard company-facts data.
        registry = investigate(facts, registry)
        observations = normalize_mapped(facts, registry)
        with sessions.begin() as s:
            company = guard(s)
            snapshot(s, company_id, "companyfacts", path, raw_facts)
            # Preserve owner decisions made while the network call was in flight.
            latest = latest_registry(s, company_id)
            decisions = {
                m["id"]: m
                for m in latest.get("mappings", [])
                if m["status"] in ("disabled", "accepted") or m.get("reviewed_at")
            }
            registry["mappings"] = [
                decisions.get(m["id"], m) for m in registry["mappings"]
            ]
            known = {m["id"] for m in registry["mappings"]}
            registry["mappings"].extend(
                m for m in latest.get("mappings", []) if m["id"] not in known
            )
            observations = normalize_mapped(facts, registry)
            save_registry(s, company_id, registry)
            if registry.get("attempts"):
                snapshot(s, company_id, "mapping_facts", path, facts)
            existing_facts = set(
                s.scalars(select(Fact.identity).where(Fact.company_id == company_id))
            )
            relevant = set(sum(TAGS.values(), []) + sum(INSTANT_TAGS.values(), [])) | {
                "LongTermDebtCurrent",
                "LongTermDebtNoncurrent",
                "LongTermDebtAndFinanceLeaseObligationsIncludingCurrentMaturities",
            }
            for tag, content in facts.get("facts", {}).get("us-gaap", {}).items():
                if tag not in relevant:
                    continue
                for unit, values in content.get("units", {}).items():
                    for f in values:
                        payload = {"tag": tag, "unit": unit} | f
                        key = identity(payload)
                        if key not in existing_facts:
                            s.add(
                                Fact(
                                    company_id=company_id, identity=key, payload=payload
                                )
                            )
                            existing_facts.add(key)
            current = {
                o.identity: o
                for o in s.scalars(
                    select(Observation).where(Observation.company_id == company_id)
                )
            }
            s.execute(
                update(Observation)
                .where(Observation.company_id == company_id)
                .values(active=False)
            )
            for item in observations:
                if item["identity"] in current:
                    current[item["identity"]].active = True
                else:
                    s.add(
                        Observation(
                            company_id=company_id,
                            identity=item["identity"],
                            metric=item["metric"],
                            period_end=item["end"],
                            kind=item["kind"],
                            value=item["value"],
                            unit=item["unit"],
                            active=True,
                            payload=item,
                        )
                    )
            s.flush()
            latest_filing = s.scalar(
                select(Filing)
                .where(
                    Filing.company_id == company_id, Filing.form.in_(["10-K", "10-Q"])
                )
                .order_by(Filing.report_date.desc())
                .limit(1)
            )
            latest_revenue = max(
                (o["end"] for o in observations if o["metric"] == "revenue"), default=""
            )
            company.data_status = (
                "pending"
                if latest_filing and latest_filing.report_date > latest_revenue
                else "current"
                if latest_revenue
                else "unavailable"
            )
            company.last_success = now()
            company.last_error = None
            evaluate_company(s, company_id)
    except Exception as exc:
        with sessions.begin() as s:
            company = guard(s)
            company.data_status = "stale" if company.last_success else "empty"
            company.last_error = str(exc)[:1000]
        raise
