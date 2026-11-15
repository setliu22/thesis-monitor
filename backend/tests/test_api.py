from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.db import get_session
from app.models import Company, Observation

@pytest.fixture
def api(sessions):
    def db():
        with sessions() as s: yield s
    app.dependency_overrides[get_session]=db
    with TestClient(app) as client: yield client
    app.dependency_overrides.clear()


def test_company_detail_and_thesis_versions(api):
    detail=api.get('/api/companies/1').json()
    assert detail['company']['ticker']=='CACI' and detail['observations']==[]
    assert api.put('/api/companies/1/thesis',json={'body':'Revenue and cash conversion remain strong.'}).status_code==200
    assert api.put('/api/companies/1/thesis',json={'body':'Revised view.'}).json()['version']==2
    assert api.get('/api/companies/1').json()['thesis']['body']=='Revised view.'
    assert api.get('/api/companies/999').status_code==404


def test_rule_validation_and_versioned_edits(api):
    good={'name':'Growth floor','metric':'revenue_growth','operator':'lt','threshold':'5','period_kind':'quarter','enabled':True}
    assert api.post('/api/companies/1/rules',json=good|{'metric':'imaginary'}).status_code==422
    assert api.post('/api/companies/1/rules',json=good|{'threshold':'NaN'}).status_code==422
    rule=api.post('/api/companies/1/rules',json=good).json()
    assert rule['version']==1
    edit=api.put(f"/api/companies/1/rules/{rule['group_key']}",json=good|{'enabled':False}).json()
    assert edit['version']==2
    assert len(api.get('/api/companies/1').json()['rules'])==1


def test_saved_rule_evaluation_and_acknowledgment(api,sessions):
    with sessions() as s:
        s.add(Observation(company_id=1,identity='x',metric='revenue_growth',period_end='2025-06-30',kind='quarter',value=4,unit='%',active=True,payload={'value':'4','metric':'revenue_growth','end':'2025-06-30','sources':[]})); s.commit()
    api.post('/api/companies/1/rules',json={'name':'Growth floor','metric':'revenue_growth','operator':'lt','threshold':'5','period_kind':'quarter','enabled':True})
    assert api.post('/api/companies/1/evaluate').json()['created']==1
    assert api.post('/api/companies/1/evaluate').json()['created']==0
    alert=api.get('/api/companies/1').json()['alerts'][0]
    assert api.post(f"/api/alerts/{alert['id']}/acknowledge").json()['acknowledged_at']


def test_missing_sec_setup_is_explicit(api):
    from app.config import settings
    original=settings.sec_user_agent; settings.sec_user_agent=''
    try:
        assert api.post('/api/companies/1/refresh').status_code==409
        assert api.post('/api/companies',json={'ticker':'bad url'}).status_code==422
        assert not api.get('/api/settings').json()['sec_configured']
    finally: settings.sec_user_agent=original


def test_local_dev_origin_can_save_and_external_origin_is_rejected(api):
    assert api.put('/api/companies/1/thesis',json={'body':'A local thesis.'},headers={'Origin':'http://127.0.0.1:5174'}).status_code==200
    assert api.put('/api/companies/1/thesis',json={'body':'Injected.'},headers={'Origin':'https://external.invalid'}).status_code==403
