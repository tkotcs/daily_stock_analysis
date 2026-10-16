"""Free Runner-only frozen dispatch capture. No live mode or real credentials."""
import argparse,datetime as dt,hashlib,ipaddress,json,os,pathlib,smtplib,socket,subprocess,sys

CONTROLLER='994d81a68d070dfa59d938f5818f3155904544e9'
BUSINESS='a1daaa302b3a72fb5694c9872ceecf2c4dc0b6e4'
EXPECTED='08b09a31d1d08c4b1fa33bc92f850feb63709ace5c6f8fd43a63aa9bee82cdee'
MANIFEST='ff2c035bcabe0bd347f5f7cc5885737039481d42fa30028a43e11c8916b366d7'


def check_commit(path,expected):
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()
    if actual!=expected:raise ValueError('code_commit_mismatch')
    return actual


def check_time(lock,now,latest):
    if now.tzinfo is None:raise ValueError('timezone_required')
    expiry=min(dt.datetime.fromisoformat(lock['analysis_asof'])+dt.timedelta(hours=24),dt.datetime.fromisoformat(lock['expires_at']))
    if now>=expiry:raise ValueError('material_EXPIRED')
    if latest!='2026-10-15' or lock['target_session']!=latest:raise ValueError('latest_completed_session_mismatch')


def check_hash(body,expected):
    calculated=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if expected!=EXPECTED or calculated!=expected:raise ValueError('full_request_sha_mismatch')
    return calculated


def main():
    p=argparse.ArgumentParser()
    for name in ('source','controller','bundle','out'):p.add_argument('--'+name,required=True,type=pathlib.Path)
    p.add_argument('--expected-sha',required=True)
    args=p.parse_args();source=args.source.resolve();controller=args.controller.resolve();bundle=args.bundle.resolve();out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    def save(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    for key in list(os.environ):
        if any(x in key for x in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')) or key in ('GH_TOKEN','GITHUB_TOKEN','LITELLM_CONFIG','LLM_CHANNELS','OPENAI_BASE_URL','OPENAI_API_BASE'):
            os.environ.pop(key,None)
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
    os.environ['DEEPSEEK_API_BASE']='https://api.deepseek.com'
    os.environ['REPORT_INTEGRITY_RETRY']='0'
    assert os.getenv('GITHUB_RUN_ATTEMPT','1')=='1','rerun_forbidden'
    check_commit(source,BUSINESS);check_commit(controller,CONTROLLER)
    assert not (source/'.env').exists()
    manifest=(bundle/'MANIFEST.json').read_bytes()
    assert hashlib.sha256(manifest).hexdigest()==MANIFEST
    for item in json.loads(manifest):
        path=(bundle/item['path']).resolve();assert path.is_relative_to(bundle)
        raw=path.read_bytes();assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
    raw=(bundle/'ORIGINAL_REQUEST_PACKET.json').read_bytes();body=json.loads(raw);lock=json.loads((bundle/'REQUEST_LOCK.json').read_text('utf-8'))
    sha=check_hash(body,args.expected_sha)
    assert hashlib.sha256(raw).hexdigest()==sha and lock['request_sha256']==sha
    assert body['model']=='deepseek-flash' and body['thinking']=={'type':'disabled'} and body['max_tokens']==16384
    assert body['stream'] is True and body['stream_options']=={'include_usage':True}
    sys.path[:0]=[str(controller/'.github/scripts'),str(source)]
    from src.core.trading_calendar import get_effective_trading_date,_XCALS_AVAILABLE
    assert _XCALS_AVAILABLE,'calendar_required'
    now=dt.datetime.now(dt.timezone.utc);latest=get_effective_trading_date('us',current_time=now).isoformat()
    check_time(lock,now,latest)
    negatives=[]
    for label,operation,expected in [
        ('wrong_hash',lambda:check_hash(body,'0'*64),'full_request_sha_mismatch'),
        ('expired',lambda:check_time(lock,dt.datetime.fromisoformat(lock['expires_at']),latest),'material_EXPIRED'),
        ('wrong_code',lambda:check_commit(source,'0'*40),'code_commit_mismatch')]:
        try:operation()
        except ValueError as exc:
            assert str(exc)==expected;negatives.append({'case':label,'rejected':True,'reason':str(exc),'real_POSTs':0})
        else:raise AssertionError('negative_case_not_blocked')
    save('NEGATIVE_BINDING_TESTS.json',negatives)
    # Prevent actual external sockets even if a client bypassed HTTPX.
    original_connect=socket.socket.connect
    def deny(*a,**k):raise AssertionError('external_network_or_SMTP_forbidden_free_preflight')
    def connect(sock,address):
        if isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback:return original_connect(sock,address)
        return deny()
    socket.socket.connect=connect;socket.create_connection=deny;smtplib.SMTP=deny;smtplib.SMTP_SSL=deny
    from src.config import Config
    from src.analyzer import GeminiAnalyzer
    from nvda_frozen_once import dispatch_frozen
    from authorized_once import canonical_sha
    from deepseek_post_guard import OnePostGuard,PreflightIntercept
    config=Config(litellm_model='deepseek/deepseek-flash',deepseek_api_keys=['phase2t-placeholder-never-transmitted'],litellm_fallback_models=[],report_integrity_retry=0)
    analyzer=GeminiAnalyzer(config=config)
    assert analyzer._router is None and not config.litellm_fallback_models
    analyzer.analyze=lambda *a,**k:(_ for _ in ()).throw(AssertionError('prompt_regeneration_forbidden'))
    guard=OnePostGuard(preflight=True);guard.install();intercepted=False
    try:dispatch_frozen(analyzer,body,config)
    except PreflightIntercept:intercepted=True
    finally:guard.restore()
    assert intercepted and guard.attempts==1 and guard.allowed==0 and len(guard.captured)==1
    wire=guard.captured[0];assert canonical_sha(wire['body'])==sha and wire['url']=='https://api.deepseek.com/chat/completions'
    assert wire['network_sent'] is False
    check_time(lock,dt.datetime.now(dt.timezone.utc),get_effective_trading_date('us',current_time=dt.datetime.now(dt.timezone.utc)).isoformat())
    (out/'FINAL_REQUEST.json').write_bytes(raw)
    (out/'REQUEST_LOCK.json').write_bytes((bundle/'REQUEST_LOCK.json').read_bytes())
    save('SDK_WIRE_CAPTURE.json',guard.captured)
    save('FREE_PREFLIGHT_RESULT.json',{'run_id':os.getenv('GITHUB_RUN_ID'),'attempt':os.getenv('GITHUB_RUN_ATTEMPT'),
        'workflow_commit':os.getenv('GITHUB_SHA'),'controller_commit':CONTROLLER,'business_commit':BUSINESS,
        'checked_UTC':now.isoformat(),'latest_completed_XNYS':latest,'request_sha256':sha,
        'thinking':body['thinking'],'max_tokens':body['max_tokens'],'stream_options':body['stream_options'],
        'intercepted_first_POST':intercepted,'guard_attempts':guard.attempts,'guard_blocked':guard.blocked,
        'real_paid_POSTs':guard.allowed,'real_key_injected':False,'placeholder_only':True,
        'fallback_models':[],'router_present':False,'SDK_num_retries':0,'HTTPX_transport_retries':0,
        'notifications':0,'new_supplier_usage':None,'new_real_cost_USD':'0','negative_cases_passed':len(negatives),
        'paid_Environment_approval_bypassed':False,'free_job_has_no_paid_Environment_or_secret':True})
    files=[{'path':f.relative_to(out).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(out.rglob('*')) if f.is_file()]
    save('MANIFEST.json',files)
    print(json.dumps({'request_sha256':sha,'intercepted':True,'real_paid_POSTs':0,'negative_cases_passed':3}))


if __name__=='__main__':main()
