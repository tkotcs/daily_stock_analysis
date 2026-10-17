"""Only affected paired-request and native transport compatibility checks."""
import hashlib,json,os,pathlib,sys
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.github/scripts'))
from authorized_once import LiveSession,canonical_sha,usage_cost
from deepseek_post_guard import OnePostGuard,PreflightIntercept
from nvda_frozen_once import dispatch_frozen
from prepare_mode_comparison import prepare
B=None;LOCK=None

@pytest.fixture(scope='module',autouse=True)
def paired_fixture(tmp_path_factory):
    global B,LOCK
    B=tmp_path_factory.mktemp('comparison')/'requests'
    LOCK=prepare(ROOT,ROOT/'.github/frozen/mvp-three-v3',B)

def test_paired_research_material_and_prompts_identical():
    assert LOCK['authorize_paid_POST'] is False and len(LOCK['members'])==6
    for code in ('NVDA','MU','QQQ'):
        a,b=[json.loads((B/code/m/'FINAL_REQUEST.json').read_text('utf-8')) for m in ('nonthinking','thinking')]
        assert a['messages']==b['messages']
        for key in set(a)|set(b):
            if key not in ('thinking','max_tokens','reasoning_effort'):assert a.get(key)==b.get(key)
        assert 'volume_ratio classification=' in str(a['messages'])
        assert '本日无新均线互穿' in str(a['messages'])
        assert (B/code/'nonthinking/NATIVE_CONTEXT.json').read_bytes()==(B/code/'thinking/NATIVE_CONTEXT.json').read_bytes()
    assert hashlib.sha256((B/'COMPARISON_LOCK.json').read_bytes()).hexdigest()==(B/'BATCH_SHA256.txt').read_text().strip()

def test_six_native_litellm_transports_intercepted(monkeypatch):
    monkeypatch.setenv('LITELLM_LOCAL_MODEL_COST_MAP','True')
    monkeypatch.setenv('DEEPSEEK_API_KEY','offline-placeholder-no-real-key')
    monkeypatch.setenv('DEEPSEEK_API_BASE','https://api.deepseek.com')
    from src.config import Config
    from src.analyzer import GeminiAnalyzer
    config=Config(litellm_model='deepseek/deepseek-flash',deepseek_api_keys=['offline-placeholder-no-real-key'],litellm_fallback_models=[],report_integrity_retry=0)
    results=[]
    for m in LOCK['members']:
        packet=json.loads((B/m['relative_request']).read_text('utf-8'))
        guard=OnePostGuard(preflight=True);guard.install()
        try:
            analyzer=GeminiAnalyzer(config=config)
            with pytest.raises(PreflightIntercept):dispatch_frozen(analyzer,packet,config)
            assert guard.allowed==0 and guard.attempts==1 and guard.blocked==1
            assert canonical_sha(guard.captured[0]['body'])==m['request_sha256'], {k:(packet.get(k),guard.captured[0]['body'].get(k)) for k in set(packet)|set(guard.captured[0]['body']) if packet.get(k)!=guard.captured[0]['body'].get(k)}
            results.append(dict(request_id=m['request_id'],captured_sha256=canonical_sha(guard.captured[0]['body']),allowed_network_POSTs=0,attempts=1))
        finally:guard.restore()
    out=B.parent/'NATIVE_CAPTURE_RESULT.json';out.write_text(json.dumps(results,indent=2),'utf-8')

@pytest.mark.parametrize('finish,truncated', [('stop',False),('length',True)])
def test_existing_sse_reasoning_usage_and_truncation(tmp_path,finish,truncated):
    # Existing response recorder only; never authorize a model or transport.
    session=LiveSession.__new__(LiveSession)
    session.out=tmp_path;session.key='offline-placeholder';session.run_id='OFFLINE';session.started=__import__('time').monotonic()
    session.status=200;session.content_encoding='identity';session.stream_complete=True;session.stream_error=None
    usage={'prompt_tokens':100,'completion_tokens':9000,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens_details':{'reasoning_tokens':5000}}
    events=[{'model':'deepseek-flash','choices':[{'delta':{'reasoning_content':'OFFLINE synthetic reasoning'}}]}, {'model':'deepseek-flash','choices':[{'delta':{'content':'{"ok":true}' if finish=='stop' else '{"ok":'},'finish_reason':finish}]}, {'choices':[],'usage':usage}]
    session.raw=bytearray((''.join('data: '+json.dumps(x)+'\n\n' for x in events)+'data: [DONE]\n\n').encode())
    session.finish();r=json.loads((tmp_path/'RESPONSE_RESULT.json').read_text())
    assert r['truncated']==truncated and r['usage']['completion_tokens_details']['reasoning_tokens']==5000
    assert r['cost_estimate']['peak_usd']==usage_cost(usage)['peak_usd']
    assert r['cost_estimate']['reasoning_not_added_twice']
