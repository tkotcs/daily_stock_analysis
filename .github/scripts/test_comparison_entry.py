"""Only paired-profile compatibility; never a real model request."""
import copy,datetime as dt,hashlib,json,os,pathlib,subprocess,sys
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'.github/scripts'));sys.path.insert(0,str(ROOT))
from mvp_three_live import load_set,batch_spec
from authorized_once import LiveSession,canonical_sha,COMPARISON_PROFILE,COMPARISON_BUSINESS
from deepseek_post_guard import GuardStop
from remote_execution_claim import RemoteExecutionClaim
from test_remote_execution_claim import DatabaseAPI,initialize
B=ROOT/'.github/frozen/mode-comparison-v1';SHA=(B/'BATCH_SHA256.txt').read_text().strip()

def test_exact_frozen_six_slot_profile():
    lock,packets,contexts=load_set(B,SHA)
    assert batch_spec(lock)[2:]==(6,'0.27') and len(packets)==6
    for c in ('NVDA','MU','QQQ'):
        assert packets[c+'_nonthinking']['messages']==packets[c+'_thinking']['messages']
        assert contexts[c+'_nonthinking']==contexts[c+'_thinking']
    with pytest.raises(GuardStop,match='batch_hash_mismatch'):load_set(B,'0'*64)

@pytest.mark.parametrize('slot,limit,reserve',[('NVDA_nonthinking',16384,'0.03'),('NVDA_thinking',32768,'0.06')])
def test_existing_session_accepts_only_bound_mode(tmp_path,slot,limit,reserve):
    lock,packets,_=load_set(B,SHA);m=next(m for m in lock['members'] if m['request_id']==slot)
    auth=dict(test_profile=COMPARISON_PROFILE,authorize_paid_post=True,authorization_reference=SHA+' '+m['request_sha256'],secret_upload_approval_reference='OFFLINE',run_id='OFFLINE',fixed_commit=COMPARISON_BUSINESS,batch_sha256=SHA,request_sha256=m['request_sha256'],symbol=m['symbol'],request_id=slot,comparison_mode=m['mode'],analysis_asof=m['analysis_asof'],target_session=m['target_session'],material_expires_at=m['material_expires_at'],expires_at=min(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10),dt.datetime.fromisoformat(m['material_expires_at'])).isoformat(),pricing_sha256=lock['pricing_sha256'],reservation_usd=reserve,allow_peak_test=True)
    def get(url,key=None):
        if url.endswith('/models'):return b'{"data":[{"id":"deepseek-flash"}]}'
        if url.endswith('/balance'):return b'{"is_available":true,"balance_infos":[{"currency":"USD","total_balance":"1"}]}'
        return (B/'OFFICIAL_PRICING.html').read_bytes()
    session=LiveSession(tmp_path,auth,'OFFLINE_KEY','OFFLINE',get=get)
    assert session.max_tokens==limit;session.approve(packets[slot])
    changed=copy.deepcopy(packets[slot]);changed['messages'][0]['content']+='UNAUTHORIZED'
    with pytest.raises(GuardStop,match='request_hash_mismatch'):session.approve(changed)
    expired={**auth,'expires_at':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1)).isoformat()}
    with pytest.raises(GuardStop,match='authorization_expired'):LiveSession(tmp_path,expired,'OFFLINE_KEY','OFFLINE',get=get)

def test_paired_remote_slots_share_existing_atomic_consumption(tmp_path):
    lock,_,_=load_set(B,SHA);slots=batch_spec(lock)[1];path=tmp_path/'fake-refs.sqlite';initialize(path)
    claim=RemoteExecutionClaim(DatabaseAPI(path),SHA,'123','a'*40,symbols=slots,paired_modes=True)
    members=[{**m,'symbol':m['request_id']} for m in lock['members']]
    claim.reserve(members)
    for m in members:claim.before_send(m['symbol'],m['request_sha256'])
    assert len(claim.sent)==6
    with pytest.raises(GuardStop):claim.before_send(members[0]['symbol'],members[0]['request_sha256'])
    other=RemoteExecutionClaim(DatabaseAPI(path),SHA,'124','a'*40,symbols=slots,paired_modes=True)
    with pytest.raises(GuardStop):other.reserve(members)
    with pytest.raises(GuardStop):RemoteExecutionClaim(DatabaseAPI(path),SHA,'125','a'*40,symbols=slots) # old profiles stay restricted

@pytest.mark.parametrize('inject,success,attempts',[(None,6,6),('MU_thinking',5,6)])
def test_six_slot_native_pipeline_and_failure_isolation(tmp_path,inject,success,attempts):
    source=pathlib.Path(os.environ.get('DSA_FIXED_SOURCE',ROOT.parent/'dsa-mode-business-577')).resolve()
    env={k:v for k,v in os.environ.items() if not any(x in k for x in ('API_KEY','PASSWORD','TOKEN','WEBHOOK'))};env.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    out=tmp_path/'result';cmd=[sys.executable,str(ROOT/'.github/scripts/mvp_three_live.py'),'--source',str(source),'--bundle',str(B),'--out',str(out),'--batch-sha',SHA,'--simulate']
    if inject:cmd+=['--inject-failure',inject]
    result=subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',timeout=100)
    assert result.returncode==0,result.stderr
    data=json.loads((out/'BATCH_RESULT.json').read_text('utf-8'))
    assert data['successful']==success and data['transport_attempts']==attempts and data['actual_paid_POSTs']==0
    assert len(data['fake_calls'])==len(set(data['fake_calls']))==6
    assert not data['published'] and len(data['symbols'])==6
    for row in data['symbols']:
        assert row['transport_attempts']==1 and row['automatic_retry'] is False
        if row.get('execution_success'):assert all((out/row['symbol']/f).exists() for f in ('REPORT.html','REPORT.md','PARSED_MODEL_JSON.json'))


def test_workflow_routes_comparison_without_old_jobs_or_free_secrets():
    import yaml
    workflow=yaml.load((ROOT/'.github/workflows/04-nvda-free-preflight.yml').read_text('utf-8'),Loader=yaml.BaseLoader)
    assert set(workflow['on'])=={'workflow_dispatch'}
    assert workflow['on']['workflow_dispatch']['inputs']['execute_live']['default']=='false'
    jobs=workflow['jobs'];free=jobs['paired_free'];live=jobs['paired_live']
    assert 'secrets.' not in json.dumps(free) and '!inputs.execute_live' in free['if']
    assert live['environment']=='nvda-one-call-approval' and 'inputs.execute_live' in live['if']
    for name,job in jobs.items():
        assert 'strategy' not in job
        if name not in ('paired_free','paired_live'):assert '!inputs.comparison_modes' in job['if']
    assert '32768' not in json.dumps(jobs['once']) # old paid profile unchanged
