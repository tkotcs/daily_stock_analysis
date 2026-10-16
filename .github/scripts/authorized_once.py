"""Manual test safety and raw response capture; no research or budget framework."""
import gzip,hashlib,json,os,re,time,urllib.request,zlib
from datetime import datetime,timezone
from decimal import Decimal
from html.parser import HTMLParser
import httpx
from deepseek_post_guard import GuardStop

FIXED='f93a7609e569e3b6c6372e652a3d36a27225d783'
# Exact reviewed profile; no arbitrary 16K payload or business revision is accepted.
REVIEWED_16K_SHA='08b09a31d1d08c4b1fa33bc92f850feb63709ace5c6f8fd43a63aa9bee82cdee'
REVIEWED_16K_FIXED='a1daaa302b3a72fb5694c9872ceecf2c4dc0b6e4'
REVIEWED_16K_ASOF='2026-10-16T06:04:29.560325+00:00'
REVIEWED_16K_DEADLINE='2026-10-16T20:00:00+00:00'

def authorized_business(authorization):
    return REVIEWED_16K_FIXED if authorization.get('request_sha256')==REVIEWED_16K_SHA else FIXED
BASE='https://api.deepseek.com'
PRICING='https://api-docs.deepseek.com/quick_start/pricing/'
def canonical_sha(body):return hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def with_usage_options(call_kwargs):
    """Controller-only metadata option; never change original research prompt."""
    if call_kwargs.get('stream') is not True:raise GuardStop('nonstream_recovery_forbidden')
    return {**call_kwargs,'stream_options':{'include_usage':True}}
def utc():return datetime.now(timezone.utc).isoformat()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise GuardStop('GET_redirect_forbidden')
def free_get(url,key=None):
    if url not in (BASE+'/models',BASE+'/user/balance',PRICING):raise GuardStop('unapproved_GET')
    headers={'Accept':'application/json' if key else 'text/html'}
    if key:headers['Authorization']='Bearer '+key
    req=urllib.request.Request(url,headers=headers,method='GET')
    with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as response:
        if response.status!=200:raise GuardStop('GET_non_200')
        return response.read()
class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,value):self.parts.append(value)
def verify_prices(raw):
    p=Text();p.feed(raw.decode('utf-8'));text=re.sub(r'\s+',' ',' '.join(p.parts))
    # Fail closed when the official table layout, model identity or any tariff changes.
    patterns=[r'1M INPUT TOKENS \(CACHE HIT\) OFF-PEAK \$0\.003 \$0\.022 PEAK \$0\.006 \$0\.044',r'1M INPUT TOKENS \(CACHE MISS\) OFF-PEAK \$0\.15 \$0\.66 PEAK \$0\.3 \$1\.32',r'1M OUTPUT TOKENS OFF-PEAK \$0\.6 \$1\.98 PEAK \$1\.2 \$3\.96']
    if 'DeepSeek-V4.1-Flash' not in text or not all(re.search(x,text) for x in patterns):raise GuardStop('pricing_changed_or_unparseable')
    return {'peak':{'cache_hit':'.006','cache_miss':'.30','output':'1.20'},'off_peak':{'cache_hit':'.003','cache_miss':'.15','output':'.60'}}
def usage_cost(usage):
    """Peak/off-peak range; never turn missing supplier usage into zero."""
    if not isinstance(usage,dict):return {'status':'unknown_missing_usage'}
    def nonnegative(v):return type(v) is int and v>=0
    inp=usage.get('prompt_tokens');out=usage.get('completion_tokens')
    if not nonnegative(inp) or not nonnegative(out):return {'status':'unknown_invalid_usage'}
    hit=usage.get('prompt_cache_hit_tokens');miss=usage.get('prompt_cache_miss_tokens')
    if hit is None and isinstance(usage.get('prompt_tokens_details'),dict):hit=usage['prompt_tokens_details'].get('cached_tokens')
    if hit is not None and (not nonnegative(hit) or hit>inp):return {'status':'unknown_invalid_cache_usage'}
    exact_cache=nonnegative(hit) and hit<=inp
    if not exact_cache:hit=0
    if miss is not None and (not nonnegative(miss) or miss!=inp-hit):return {'status':'unknown_inconsistent_cache_usage'}
    peak=(Decimal(hit)*Decimal('.006')+Decimal(inp-hit)*Decimal('.30')+Decimal(out)*Decimal('1.20'))/1000000
    details=usage.get('completion_tokens_details')
    reasoning=details.get('reasoning_tokens') if isinstance(details,dict) else None
    if reasoning is not None and (not nonnegative(reasoning) or reasoning>out):return {'status':'unknown_invalid_reasoning_usage'}
    return {'status':'estimated_not_supplier_bill','peak_usd':str(peak),'off_peak_usd':str(peak/2),'cache_split_reported':exact_cache,'unknown_cache_assumed_all_miss':not exact_cache,'reasoning_tokens':reasoning,'reasoning_not_added_twice':True,'note':'completion_tokens includes reasoning when reported; tariff window and CNY bill reconciliation remain separate'}
class SafeWriter:
    """Buffer complete lines so a key split over write() calls is also redacted."""
    encoding='utf-8'
    def __init__(self,path,key):self.file=path.open('x',encoding='utf-8');self.key=key;self.pending=''
    def write(self,value):
        self.pending+=str(value)
        while '\n' in self.pending:
            line,self.pending=self.pending.split('\n',1);self.file.write(line.replace(self.key,'[REDACTED]')+'\n')
        return len(value)
    def flush(self):
        if not self.file.closed:self.file.flush()
    def close(self):
        if not self.file.closed:self.file.write(self.pending.replace(self.key,'[REDACTED]'));self.pending='';self.file.close()

class LiveSession:
    def __init__(self,out,authorization,key,run_id,get=free_get):
        self.out=out;self.auth=authorization;self.key=key;self.run_id=run_id;self.get=get;self.started=None;self.status=None;self.raw=bytearray();self.stream_complete=False;self.stream_error=None;self.content_encoding='identity'
        if not key or not run_id or os.getenv('GITHUB_RUN_ATTEMPT','1')!='1':raise GuardStop('key_run_id_or_attempt_invalid')
        if authorization.get('authorize_paid_post') is not True or not authorization.get('authorization_reference') or not authorization.get('secret_upload_approval_reference'):raise GuardStop('separate_explicit_approvals_required')
        self.reviewed_16k=authorization.get('request_sha256')==REVIEWED_16K_SHA
        self.max_tokens=16384 if self.reviewed_16k else 8192
        if authorization.get('run_id')!=run_id or authorization.get('fixed_commit')!=authorized_business(authorization):raise GuardStop('authorization_identity_mismatch')
        try:expires=datetime.fromisoformat(authorization['expires_at'])
        except Exception:raise GuardStop('authorization_expiry_required') from None
        if expires.tzinfo is None or datetime.now(timezone.utc)>=expires:raise GuardStop('authorization_expired')
        if self.reviewed_16k:
            if REVIEWED_16K_SHA not in str(authorization.get('authorization_reference','')):raise GuardStop('new_hash_scoped_approval_required')
            if authorization.get('analysis_asof')!=REVIEWED_16K_ASOF or authorization.get('target_session')!='2026-10-15':raise GuardStop('frozen_material_identity_mismatch')
            if expires>datetime.fromisoformat(REVIEWED_16K_DEADLINE):raise GuardStop('authorization_extends_material_deadline')
            self.check_material()
        try:self.reserve=Decimal(str(authorization['reservation_usd']))
        except Exception:raise GuardStop('invalid_reservation') from None
        if not self.reserve.is_finite() or not 0<self.reserve<=Decimal('.03'):raise GuardStop('reservation_outside_authorized_limit')
    def save(self,name,value):
        text=json.dumps(value,ensure_ascii=False,indent=2)
        (self.out/name).write_text(text.replace(self.key,'[REDACTED]'),encoding='utf-8')
    def approve(self,body):
        if datetime.now(timezone.utc)>=datetime.fromisoformat(self.auth['expires_at']):raise GuardStop('authorization_expired')
        self.check_material()
        if canonical_sha(body)!=self.auth.get('request_sha256'):raise GuardStop('request_hash_mismatch')
        if body.get('model')!='deepseek-flash' or body.get('max_tokens')!=self.max_tokens or body.get('stream') is not True:raise GuardStop('request_parameters_changed')
        if body.get('stream_options')!={'include_usage':True}:raise GuardStop('stream_usage_option_required')
        if set(body)-{'model','max_tokens','stream','stream_options','temperature','messages','thinking'}:raise GuardStop('unreviewed_request_parameters')
        if 'thinking' in body and body['thinking']!={'type':'disabled'}:raise GuardStop('unreviewed_thinking_mode')
        if self.reviewed_16k and body.get('thinking')!={'type':'disabled'}:raise GuardStop('thinking_disabled_required')
        content=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
        if self.key.encode() in content:raise GuardStop('credential_in_request_body')
        allowance=len(content)+1024
        estimate=(Decimal(allowance)*Decimal('.30')+Decimal(self.max_tokens)*Decimal('1.20'))/1000000
        if estimate>self.reserve:raise GuardStop('estimated_reservation_exceeded')
        # No model-generating request in these three read-only GETs, no retries.
        models=json.loads(self.get(BASE+'/models',self.key))
        if 'deepseek-flash' not in [m.get('id') for m in models.get('data',[])]:raise GuardStop('flash_model_unavailable')
        balance=json.loads(self.get(BASE+'/user/balance',self.key))
        if balance.get('is_available') is not True:raise GuardStop('account_unavailable')
        infos=[{k:b.get(k) for k in ('currency','total_balance')} for b in balance.get('balance_infos',[])]
        if not infos or not any(Decimal(str(b['total_balance']))>0 for b in infos):raise GuardStop('balance_not_positive')
        pricing=self.get(PRICING)
        if hashlib.sha256(pricing).hexdigest()!=self.auth.get('pricing_sha256'):raise GuardStop('pricing_snapshot_changed')
        rates=verify_prices(pricing)
        if datetime.now(timezone.utc)>=datetime.fromisoformat(self.auth['expires_at']):raise GuardStop('authorization_expired_during_preflight')
        self.check_material()
        # Atomic exclusive local marker. A new Runner needs a different authorized run_id;
        # reruns of the same GitHub run are forbidden. This is not a budget ledger.
        with (self.out/'POST_ATTEMPT.json').open('x',encoding='utf-8') as f:
            json.dump({'run_id':self.run_id,'request_sha256':canonical_sha(body),'state':'reserved_before_transport_may_be_charged','at':utc(),'reservation_usd':str(self.reserve)},f)
        self.save('LIVE_PREFLIGHT.json',{'checked_at':utc(),'model_available':True,'balance':infos,'pricing_sha256':hashlib.sha256(pricing).hexdigest(),'rates':rates,'input_byte_allowance_not_formal_token_bound':allowance,'peak_estimate_usd':str(estimate),'reservation_usd':str(self.reserve)})
        self.started=time.monotonic()
    def check_material(self):
        if not self.reviewed_16k:return
        now=datetime.now(timezone.utc)
        if now>=datetime.fromisoformat(REVIEWED_16K_DEADLINE):raise GuardStop('material_EXPIRED_no_POST')
        from src.core.trading_calendar import get_effective_trading_date,_XCALS_AVAILABLE
        if not _XCALS_AVAILABLE or get_effective_trading_date('us',current_time=now).isoformat()!='2026-10-15':raise GuardStop('latest_completed_session_changed')
        # Conservative off-peak rule: block weekday peak windows even on holidays.
        if now.weekday()<5 and (1<=now.hour<4 or 6<=now.hour<10):raise GuardStop('peak_window_no_POST')
    def on_error(self,category):
        self.stream_error=category;self.finish();raise GuardStop('POST_result_unknown_do_not_retry')
    def on_response(self,response,is_async):
        self.status=response.status_code
        self.content_encoding=response.headers.get('content-encoding','identity').lower()
        if response.is_stream_consumed:
            self.content_encoding='identity'  # HTTPX preloaded content has already been decoded.
            self.add(response.content);self.stream_complete=True;self.finish()
        elif is_async:response.stream=AsyncCapture(response.stream,self)
        else:response.stream=SyncCapture(response.stream,self)
        # HTTP errors/redirects must not enter SDK recovery.
        if self.status!=200:
            if is_async:return self.async_failure(response)
            try:response.read()
            finally:response.close()
            self.stream_error='HTTP_non_200';self.finish();raise GuardStop('HTTP_failure_do_not_retry')
    async def async_failure(self,response):
        try:await response.aread()
        finally:await response.aclose()
        self.stream_error='HTTP_non_200';self.finish();raise GuardStop('HTTP_failure_do_not_retry')
    def add(self,data):self.raw.extend(data)
    def finish(self):
        if self.started is None:return
        raw=bytes(self.raw);safe=raw.replace(self.key.encode(),b'[REDACTED]')
        parts=[];reasoning=[];usage=None;finish=None;model=None;done=False;parse_errors=0
        decoded=raw
        try:
            if self.content_encoding=='gzip':decoded=gzip.decompress(raw)
            elif self.content_encoding=='deflate':decoded=zlib.decompress(raw)
            elif self.content_encoding not in ('identity',''):raise ValueError('unsupported_content_encoding')
        except Exception:decoded=b'';parse_errors+=1
        if self.key.encode() in decoded and self.content_encoding not in ('identity',''):safe=decoded.replace(self.key.encode(),b'[REDACTED]')
        (self.out/'RAW_RESPONSE_BODY.bin').write_bytes(safe)
        decoded=decoded.replace(self.key.encode(),b'[REDACTED]')
        for line in decoded.decode('utf-8',errors='replace').splitlines():
            if not line.startswith('data:'):continue
            data=line[5:].strip()
            if data=='[DONE]':done=True;continue
            try:x=json.loads(data)
            except ValueError:parse_errors+=1;continue
            if not isinstance(x,dict) or not isinstance(x.get('choices',[]),list):parse_errors+=1;continue
            model=x.get('model',model);usage=x.get('usage') or usage
            for c in x.get('choices',[]):
                if not isinstance(c,dict) or not isinstance(c.get('delta',{}),dict):parse_errors+=1;continue
                delta=c.get('delta') or {}
                if any(not isinstance(delta.get(k,''),(str,type(None))) for k in ('content','reasoning_content')):parse_errors+=1;continue
                parts.append(delta.get('content') or '');reasoning.append(delta.get('reasoning_content') or '')
                finish=c.get('finish_reason') or finish
        (self.out/'MODEL_RAW_TEXT.txt').write_text(''.join(parts),encoding='utf-8')
        (self.out/'MODEL_REASONING_TEXT.txt').write_text(''.join(reasoning),encoding='utf-8')
        self.save('RESPONSE_RESULT.json',{'run_id':self.run_id,'http_status':self.status,'response_model':model,'finish_reason':finish,'usage':usage,'cost_estimate':usage_cost(usage),'elapsed_seconds':round(time.monotonic()-self.started,3),'raw_body_sha256':hashlib.sha256(raw).hexdigest(),'content_encoding':self.content_encoding,'secret_redaction_changed_raw':safe!=raw,'sse_done':done,'transport_stream_complete':self.stream_complete,'parse_errors':parse_errors,'error_category':self.stream_error,'truncated':finish=='length','result_unknown':self.status!=200 or not done or not finish or self.stream_error is not None or bool(parse_errors),'automatic_retry':False})
class SyncCapture(httpx.SyncByteStream):
    def __init__(self,inner,owner):self.inner=inner;self.owner=owner
    def __iter__(self):
        try:
            for chunk in self.inner:self.owner.add(chunk);yield chunk
            self.owner.stream_complete=True
        except Exception as exc:self.owner.on_error(type(exc).__name__)
        finally:self.owner.finish()
    def close(self):self.inner.close();self.owner.finish()
class AsyncCapture(httpx.AsyncByteStream):
    def __init__(self,inner,owner):self.inner=inner;self.owner=owner
    async def __aiter__(self):
        try:
            async for chunk in self.inner:self.owner.add(chunk);yield chunk
            self.owner.stream_complete=True
        except Exception as exc:self.owner.on_error(type(exc).__name__)
        finally:self.owner.finish()
    async def aclose(self):await self.inner.aclose();self.owner.finish()
