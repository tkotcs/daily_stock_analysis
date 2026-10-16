"""Simulated transports only. Synthetic SSE/usage is never a supplier bill."""
import asyncio,copy,json,os,pathlib,sys,tempfile
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'.github/scripts')]
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
import authorized_once as ao
from deepseek_post_guard import OnePostGuard,GuardStop,ENDPOINT
from nvda_frozen_once import dispatch_frozen,load_packet,research_quality,render_review_report

BUNDLE=ROOT/'.github/frozen/phase2r'
BODY=json.loads((BUNDLE/'ORIGINAL_REQUEST_PACKET.json').read_text('utf-8'))
PRICING=(BUNDLE/'OFFICIAL_PRICING.html').read_bytes()
SSE=b'data: {"model":"deepseek-flash","choices":[{"delta":{"content":"OFFLINE SYNTHETIC RESPONSE"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1}}\n\ndata: [DONE]\n\n'
KEY='offline-sentinel-not-a-real-key'


class Clock(datetime):
    current=datetime(2026,10,16,10,30,tzinfo=timezone.utc)
    @classmethod
    def now(cls,tz=None):return cls.current if tz is None else cls.current.astimezone(tz)


@pytest.fixture
def controlled(tmp_path,monkeypatch):
    # No system date change. This clock exists only inside this offline test process.
    Clock.current=datetime(2026,10,16,10,30,tzinfo=timezone.utc)
    monkeypatch.setattr(ao,'datetime',Clock)
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    auth={'authorize_paid_post':True,'authorization_reference':'OFFLINE SIMULATION ONLY '+ao.REVIEWED_16K_SHA,
          'secret_upload_approval_reference':'OFFLINE SIMULATION ONLY','run_id':'offline-2s-fixture',
          'fixed_commit':ao.REVIEWED_16K_FIXED,'request_sha256':ao.REVIEWED_16K_SHA,
          'pricing_sha256':__import__('hashlib').sha256(PRICING).hexdigest(),'reservation_usd':'.03',
          'analysis_asof':ao.REVIEWED_16K_ASOF,'target_session':'2026-10-15',
          'expires_at':(Clock.current+timedelta(minutes=5)).isoformat()}
    calls=[]
    def get(url,key=None):
        calls.append(url)
        if url.endswith('/models'):return b'{"data":[{"id":"deepseek-flash"}]}'
        if url.endswith('/balance'):return b'{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"29.86"}]}'
        return PRICING
    return SimpleNamespace(root=tmp_path,auth=auth,get=get,calls=calls)


def session(c):return ao.LiveSession(c.root,c.auth,KEY,c.auth['run_id'],c.get)


def test_exact_frozen_16k_accepts(controlled):
    s=session(controlled);s.approve(BODY)
    assert s.max_tokens==16384 and len(controlled.calls)==3
    assert load_packet(BUNDLE,ao.REVIEWED_16K_SHA)==BODY


@pytest.mark.parametrize('field,value',[('max_tokens',8192),('thinking',{'type':'enabled'}),
    ('stream',False),('stream_options',{}),('temperature',.71),('model','other')])
def test_any_parameter_mutation_rejected(controlled,field,value):
    body=copy.deepcopy(BODY);body[field]=value
    with pytest.raises(GuardStop,match='request_hash_mismatch'):session(controlled).approve(body)
    assert controlled.calls==[]


def test_prompt_mutation_rejected(controlled):
    body=copy.deepcopy(BODY);body['messages'][1]['content']+=' changed'
    with pytest.raises(GuardStop,match='request_hash_mismatch'):session(controlled).approve(body)
    assert controlled.calls==[]


@pytest.mark.parametrize('field,value',[('request_sha256','0'*64),('fixed_commit',ao.FIXED),
    ('analysis_asof','2026-10-16T06:00:00+00:00'),('target_session','2026-10-14')])
def test_authorization_identity_mutation_rejected(controlled,field,value):
    controlled.auth[field]=value
    with pytest.raises(GuardStop):session(controlled)
    assert controlled.calls==[]


def test_authorization_expired(controlled):
    controlled.auth['expires_at']='2026-10-16T10:29:59+00:00'
    with pytest.raises(GuardStop,match='authorization_expired'):session(controlled)


def test_old_authorization_reference_cannot_be_reused(controlled):
    controlled.auth['authorization_reference']='Previously consumed Phase2P approval'
    with pytest.raises(GuardStop,match='new_hash_scoped_approval_required'):session(controlled)


def test_material_deadline_is_not_extended(controlled):
    controlled.auth['expires_at']='2026-10-16T20:01:00+00:00'
    with pytest.raises(GuardStop,match='extends_material_deadline'):session(controlled)


def test_material_expired_exactly_at_deadline(controlled):
    s=session(controlled);Clock.current=datetime(2026,10,16,20,tzinfo=timezone.utc)
    with pytest.raises(GuardStop,match='material_EXPIRED_no_POST'):s.check_material()
    assert controlled.calls==[]


def test_latest_session_change_rejected(controlled):
    from src.core import trading_calendar
    with patch.object(trading_calendar,'get_effective_trading_date',return_value=datetime(2026,10,16).date()):
        with pytest.raises(GuardStop,match='latest_completed_session_changed'):session(controlled)


def test_weekday_peak_rejected(controlled):
    Clock.current=datetime(2026,10,16,7,tzinfo=timezone.utc)
    with pytest.raises(GuardStop,match='peak_window_no_POST'):session(controlled)


def test_phase2u_explicit_peak_test_allowed(controlled):
    Clock.current=datetime(2026,10,16,7,tzinfo=timezone.utc)
    controlled.auth.update(allow_peak_test=True,authorization_reference='Phase2U single test '+ao.REVIEWED_16K_SHA,
                           expires_at='2026-10-16T07:05:00+00:00')
    s=session(controlled);s.approve(BODY)
    assert len(controlled.calls)==3 and s.reserve==__import__('decimal').Decimal('.03')


@pytest.mark.parametrize('value,reference',[(False,'Phase2U'),('true','Phase2U'),(True,'Phase2P')])
def test_peak_opt_in_is_strict_and_phase_scoped(controlled,value,reference):
    Clock.current=datetime(2026,10,16,7,tzinfo=timezone.utc)
    controlled.auth.update(allow_peak_test=value,authorization_reference=reference+' '+ao.REVIEWED_16K_SHA)
    with pytest.raises(GuardStop,match='peak_window_no_POST'):session(controlled)


def test_peak_opt_in_does_not_override_material_expiry(controlled):
    controlled.auth.update(allow_peak_test=True,authorization_reference='Phase2U '+ao.REVIEWED_16K_SHA)
    s=session(controlled);Clock.current=datetime(2026,10,16,20,tzinfo=timezone.utc)
    with pytest.raises(GuardStop,match='material_EXPIRED_no_POST'):s.check_material()


def test_expired_during_free_get_never_sends(controlled):
    def late_get(url,key=None):
        data=controlled.get(url,key)
        if url==ao.PRICING:Clock.current=datetime(2026,10,16,20,tzinfo=timezone.utc)
        return data
    s=ao.LiveSession(controlled.root,controlled.auth,KEY,controlled.auth['run_id'],late_get)
    with pytest.raises(GuardStop):s.approve(BODY)
    assert not (controlled.root/'POST_ATTEMPT.json').exists()


@pytest.mark.parametrize('mode',['sync','async','shared_sync_then_async'])
def test_timeout_has_one_simulated_transport_no_second(controlled,mode):
    s=session(controlled);sent=[]
    def sync(t,r):sent.append('sync');raise httpx.ReadTimeout('synthetic timeout')
    async def async_fake(t,r):sent.append('async');raise httpx.ReadTimeout('synthetic timeout')
    async def attempt():
        async with httpx.AsyncClient() as c:
            with pytest.raises(GuardStop):await c.post(ENDPOINT,json=BODY)
    with patch.object(httpx.HTTPTransport,'handle_request',sync),patch.object(httpx.AsyncHTTPTransport,'handle_async_request',async_fake):
        g=OnePostGuard(preflight=False,before_send=s.approve,on_response=s.on_response,on_error=s.on_error);g.install()
        try:
            if mode!='async':
                with httpx.Client() as c:
                    with pytest.raises(GuardStop):c.post(ENDPOINT,json=BODY)
            else:asyncio.run(attempt())
            if mode=='sync':
                with httpx.Client() as c:
                    with pytest.raises(GuardStop,match='second_POST_blocked'):c.post(ENDPOINT,json=BODY)
            else:asyncio.run(attempt())
            assert len(sent)==g.allowed==1 and g.blocked==1
        finally:g.restore()


def test_native_sdk_exact_body_and_zero_retries_simulated(controlled):
    from src.config import Config
    from src.analyzer import GeminiAnalyzer
    sent=[]
    def fake(t,r):
        sent.append(json.loads(r.content))
        return httpx.Response(200,stream=httpx.ByteStream(SSE),headers={'content-type':'text/event-stream'},request=r)
    config=Config(litellm_model='deepseek/deepseek-flash',deepseek_api_keys=[KEY],litellm_fallback_models=[],report_integrity_retry=0)
    with patch.dict(os.environ,{'DEEPSEEK_API_BASE':ao.BASE}),patch.object(httpx.HTTPTransport,'handle_request',fake):
        analyzer=GeminiAnalyzer(config=config)
        assert analyzer._router is None
        analyzer.analyze=lambda *a,**k:(_ for _ in ()).throw(AssertionError('prompt rebuild forbidden'))
        s=session(controlled);g=OnePostGuard(preflight=False,before_send=s.approve,on_response=s.on_response,on_error=s.on_error);g.install()
        try:
            text,_=dispatch_frozen(analyzer,BODY,config)
            assert text=='OFFLINE SYNTHETIC RESPONSE' and sent==[BODY] and g.allowed==1
        finally:g.restore()


@pytest.mark.parametrize('plan',[None,'invalid',{},[],{'max_position_pct':1,'scenarios':[{'entry':100}]}])
def test_missing_or_invalid_risk_plan_quality_NO_GO(plan):
    result=SimpleNamespace(success=True,dashboard={'battle_plan':{'risk_plan':plan}})
    quality=research_quality(result,True)
    assert not quality['passed'] and quality['risk_plan_errors'] and not quality['published']


def test_absent_risk_plan_quality_NO_GO():
    assert not research_quality(SimpleNamespace(success=True,dashboard={}),True)['passed']


def test_good_plan_only_eligible_for_manual_review():
    plan={'max_position_pct':20,'scenarios':[{'entry':100,'stop':95,'target':110,'position_pct':10,'trigger':'synthetic close','invalidation':'synthetic condition'}]}
    result=SimpleNamespace(success=True,dashboard={'battle_plan':{'risk_plan':plan}})
    quality=research_quality(result,True)
    assert quality['passed'] and quality['calculated_scenarios'][0]['loss_pct']==5
    assert quality['manual_full_fact_review_required'] and not quality['published']


@pytest.mark.parametrize('plan',[None,{},'invalid'])
def test_quality_failure_never_calls_renderer_or_writes_report(controlled,plan):
    parsed=SimpleNamespace(success=True,dashboard={'battle_plan':{'risk_plan':plan}})
    with patch('nvda_frozen_once.render_native_report',side_effect=AssertionError('must not render')):
        quality=render_review_report(session(controlled),parsed,True,controlled.root,KEY)
    assert not quality['passed'] and (controlled.root/'PUBLISH_BLOCKED.json').exists()
    assert not (controlled.root/'NATIVE_NVDA_REPORT.md').exists()
