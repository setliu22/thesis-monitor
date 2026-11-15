import json
from sqlalchemy import select, update
from .models import Company, Snapshot, Filing, Fact, Observation, now
from .financials import normalize, identity, TAGS
from .rules import evaluate_company
from .jobs import owned_job


def snapshot(s,company_id,kind,path,data):
    digest=identity(data)
    if not s.scalar(select(Snapshot.id).where(Snapshot.company_id==company_id,Snapshot.kind==kind,Snapshot.digest==digest)):
        host='data.sec.gov'
        s.add(Snapshot(company_id=company_id,kind=kind,digest=digest,source_url=f'https://{host}{path}',payload=data))


def ingest_company(sessions,company_id,client,job_id=None,owner=None):
    def guard(s):
        # Company first is the common lock order; then job ownership.
        company=s.scalar(select(Company).where(Company.id==company_id).with_for_update())
        if job_id: owned_job(s,job_id,owner)
        return company
    with sessions.begin() as s:
        company=guard(s); company.last_attempt=now(); cik=company.cik
    try:
        path=f'/submissions/CIK{cik}.json'
        submissions=client.fetch_json(path)
        with sessions.begin() as s:
            guard(s); snapshot(s,company_id,'submissions',path,submissions)
            recent=submissions.get('filings',{}).get('recent',{})
            for i,accession in enumerate(recent.get('accessionNumber',[])):
                form=recent['form'][i]
                if form not in ('10-K','10-Q','8-K','10-K/A','10-Q/A'): continue
                if s.scalar(select(Filing.id).where(Filing.accession==accession)): continue
                s.add(Filing(company_id=company_id,accession=accession,form=form,filed=recent['filingDate'][i],report_date=recent.get('reportDate',['']*len(recent['form']))[i],document=recent['primaryDocument'][i]))
        path=f'/api/xbrl/companyfacts/CIK{cik}.json'
        facts=client.fetch_json(path)
        observations=normalize(facts)
        with sessions.begin() as s:
            company=guard(s); snapshot(s,company_id,'companyfacts',path,facts)
            existing_facts=set(s.scalars(select(Fact.identity).where(Fact.company_id==company_id)))
            relevant=set(sum(TAGS.values(),[]))|{'LongTermDebtCurrent','LongTermDebtNoncurrent','LongTermDebtAndFinanceLeaseObligationsIncludingCurrentMaturities'}
            for tag,content in facts.get('facts',{}).get('us-gaap',{}).items():
                if tag not in relevant: continue
                for unit,values in content.get('units',{}).items():
                    for f in values:
                        payload={'tag':tag,'unit':unit}|f; key=identity(payload)
                        if key not in existing_facts:
                            s.add(Fact(company_id=company_id,identity=key,payload=payload)); existing_facts.add(key)
            current={o.identity:o for o in s.scalars(select(Observation).where(Observation.company_id==company_id))}
            s.execute(update(Observation).where(Observation.company_id==company_id).values(active=False))
            for item in observations:
                if item['identity'] in current:
                    current[item['identity']].active=True
                else:
                    s.add(Observation(company_id=company_id,identity=item['identity'],metric=item['metric'],period_end=item['end'],kind=item['kind'],value=item['value'],unit=item['unit'],active=True,payload=item))
            s.flush()
            latest_filing=s.scalar(select(Filing).where(Filing.company_id==company_id,Filing.form.in_(['10-K','10-Q'])).order_by(Filing.report_date.desc()).limit(1))
            latest_revenue=max((o['end'] for o in observations if o['metric']=='revenue'),default='')
            company.data_status='pending' if latest_filing and latest_filing.report_date>latest_revenue else 'current' if latest_revenue else 'unavailable'
            company.last_success=now(); company.last_error=None
            evaluate_company(s,company_id)
    except Exception as exc:
        with sessions.begin() as s:
            company=guard(s)
            company.data_status='stale' if company.last_success else 'empty'; company.last_error=str(exc)[:1000]
        raise
