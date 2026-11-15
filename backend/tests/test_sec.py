import httpx
import pytest
from app.sec import SecClient, SecError, valid_identity


def test_identity_and_url_restriction():
    assert not valid_identity('')
    assert not valid_identity('Someone fake@example.com')
    assert valid_identity('Project Maintainer person@real-domain.org')
    with pytest.raises(SecError): SecClient('').fetch_json('/submissions/CIK0000016058.json')
    client=SecClient('Project Maintainer person@real-domain.org')
    for path in ['https://evil.com/a','/../foo','/Archives/edgar/data/1/2/../../secret']:
        with pytest.raises(SecError): client.fetch_json(path)


def test_retry_then_parses_real_response_boundary():
    calls=[]; sleeps=[]
    def handler(req):
        calls.append(req)
        if len(calls)<3: return httpx.Response(429,headers={'Retry-After':'0'})
        return httpx.Response(200,json={'cik':'0000016058'})
    client=SecClient('Project Maintainer person@real-domain.org',transport=httpx.MockTransport(handler),sleep=sleeps.append)
    assert client.fetch_json('/submissions/CIK0000016058.json')['cik']=='0000016058'
    assert len(calls)==3 and calls[0].url.host=='data.sec.gov'


def test_bounded_retries_and_response_size():
    calls=[]
    def handler(req):
        calls.append(req); return httpx.Response(503)
    client=SecClient('Project Maintainer person@real-domain.org',transport=httpx.MockTransport(handler),sleep=lambda _:None)
    with pytest.raises(SecError): client.fetch_json('/submissions/CIK0000016058.json')
    assert len(calls)==3
    client=SecClient('Project Maintainer person@real-domain.org',transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*100)),max_bytes=20)
    with pytest.raises(SecError): client.fetch_json('/submissions/CIK0000016058.json')


def test_shared_gate_is_used_for_each_http_attempt():
    ticks=[]
    client=SecClient('Project Maintainer person@real-domain.org',transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'ok':True})),gate=lambda:ticks.append('gate'))
    assert client.fetch_json('/submissions/CIK0000016058.json')=={'ok':True}
    assert ticks==['gate']
