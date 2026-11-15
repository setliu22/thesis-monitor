"""SEC boundary: fixed endpoints, bounded reads, conservative throttling."""
import json
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx


class SecError(RuntimeError):
    pass


def valid_identity(identity: str) -> bool:
    email=re.search(r'[\w.+-]+@([\w.-]+\.[a-zA-Z]{2,})',identity)
    return bool(email and len(identity.split())>=2 and email.group(1).lower() not in ('example.com','example.org','example.net'))


_gate=threading.Lock()
_last_request=0.0


class SecClient:
    def __init__(self, user_agent: str, transport=None, sleep=time.sleep, max_bytes=30_000_000):
        self.user_agent=user_agent; self.transport=transport; self.sleep=sleep; self.max_bytes=max_bytes

    def _url(self,path):
        if not valid_identity(self.user_agent):
            raise SecError('SEC setup needed: set SEC_USER_AGENT to your name and real contact email, then restart API and worker.')
        patterns=[r'/submissions/CIK\d{10}\.json',r'/api/xbrl/companyfacts/CIK\d{10}\.json',r'/files/company_tickers_exchange\.json',r'/Archives/edgar/data/\d+/\d+/[A-Za-z0-9_.-]+']
        if '..' in path or not any(re.fullmatch(p,path) for p in patterns):
            raise SecError('Unapproved SEC resource path')
        host='www.sec.gov' if path.startswith(('/files/','/Archives/')) else 'data.sec.gov'
        return f'https://{host}{path}'

    def _fetch(self,path):
        global _last_request
        url=self._url(path)
        for attempt in range(3):
            with _gate:
                self.sleep(max(0,0.3-(time.monotonic()-_last_request)))
                _last_request=time.monotonic()
            try:
                with httpx.Client(transport=self.transport,timeout=25,follow_redirects=False,headers={'User-Agent':self.user_agent,'Accept-Encoding':'gzip, deflate'}) as client:
                    with client.stream('GET',url) as response:
                        if response.status_code==429 or response.status_code>=500:
                            if attempt==2: raise SecError(f'SEC unavailable (HTTP {response.status_code}); retry later.')
                            retry=response.headers.get('Retry-After','')
                            try: wait=float(retry)
                            except ValueError:
                                try: wait=(parsedate_to_datetime(retry)-datetime.now(timezone.utc)).total_seconds()
                                except (ValueError,TypeError): wait=2**attempt
                            if wait>60: raise SecError('SEC requested a long retry delay; the durable job will retry later.')
                            self.sleep(max(0,wait)); continue
                        if response.status_code!=200:
                            raise SecError(f'SEC returned HTTP {response.status_code}; check access policy and try later.')
                        data=bytearray()
                        for part in response.iter_bytes():
                            data.extend(part)
                            if len(data)>self.max_bytes: raise SecError('SEC response exceeds configured size limit')
                        return bytes(data)
            except (httpx.TimeoutException,httpx.NetworkError) as exc:
                if attempt==2: raise SecError('SEC request timed out or network unavailable') from exc
                self.sleep(2**attempt)
        raise SecError('SEC retry limit reached')

    def fetch_json(self,path: str) -> dict:
        try: return json.loads(self._fetch(path))
        except (ValueError,UnicodeDecodeError) as exc: raise SecError('SEC returned invalid JSON') from exc

    def fetch_text(self,path: str) -> str:
        return self._fetch(path).decode('utf-8',errors='replace')

    def resolve_company(self,ticker: str) -> dict:
        data=self.fetch_json('/files/company_tickers_exchange.json')
        fields=data['fields']
        for row in data['data']:
            item=dict(zip(fields,row))
            if item['ticker'].upper()==ticker.upper():
                return {'ticker':item['ticker'].upper(),'name':item['name'],'cik':str(item['cik']).zfill(10)}
        raise SecError('Ticker not found in the SEC exchange mapping')


def filing_path(cik: str, accession: str, document: str) -> str:
    if not re.fullmatch(r'\d{10}',cik) or not re.fullmatch(r'\d{10}-\d{2}-\d{6}',accession) or not re.fullmatch(r'[A-Za-z0-9_.-]+',document) or '..' in document:
        raise SecError('Invalid filing identifier')
    return f'/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{document}'
