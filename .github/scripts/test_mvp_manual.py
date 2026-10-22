"""Narrow manual-batch contract and one 35-symbol synthetic model run; no collection."""
import datetime as dt,hashlib,json,os,pathlib,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from authorized_once import MANUAL_BUSINESS,canonical_sha
from free_market_validation import WATCHLIST
from mvp_three_live import load_set,batch_spec
from remote_execution_claim import RemoteExecutionClaim
from deepseek_post_guard import GuardStop

def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def synthetic_bundle(out,source):
    sys.path.insert(0,str(source));from src.core.trading_calendar import get_effective_trading_date
    import exchange_calendars as xc,pandas as pd
    now=dt.datetime.now(dt.timezone.utc);target=get_effective_trading_date('us',current_time=now).isoformat();cal=xc.get_calendar('XNYS');previous=cal.previous_session(pd.Timestamp(target)).date().isoformat()
    deadline=min(now+dt.timedelta(hours=24),cal.session_close(cal.next_session(pd.Timestamp(target))).to_pydatetime())
    out.mkdir();pricing=(pathlib.Path(__file__).parents[1]/'frozen/mvp-three/OFFICIAL_PRICING.html').read_bytes();(out/'OFFICIAL_PRICING.html').write_bytes(pricing);members=[]
    for code in WATCHLIST:
        p=out/code;p.mkdir();context={'code':code,'stock_name':'SYNTHETIC '+code,'date':target,'today':{'date':target,'open':99,'close':100,'high':101,'low':98,'volume':1000,'volume_ratio':1,'ma5':101,'ma10':102,'ma20':103,'ma60':104},'yesterday':{'date':previous,'close':100,'volume':1000,'ma5':101,'ma10':102,'ma20':103,'ma60':104},'trend_analysis':{},'fundamental_context':{'status':'not_supported'},'fixture_only':True}
        packet={'model':'deepseek-flash','max_tokens':16384,'thinking':{'type':'disabled'},'stream':True,'stream_options':{'include_usage':True},'messages':[{'role':'user','content':'SYNTHETIC OFFLINE ONLY NEVER LIVE '+code}]}
        body=canonical(packet);ctx=canonical(context);(p/'FINAL_REQUEST.json').write_bytes(body);(p/'NATIVE_CONTEXT.json').write_bytes(ctx)
        members.append({'symbol':code,'request_sha256':canonical_sha(packet),'context_sha256':hashlib.sha256(ctx).hexdigest(),'target_session':target,'analysis_asof':now.isoformat(),'material_expires_at':deadline.isoformat(),'reservation_USD':'0.03','reservation_check':True})
    lock={'profile':'mvp_manual_v2','offline_only':True,'business_commit':MANUAL_BUSINESS,'members':members,'max_total_POSTs':35,'max_POSTs_per_symbol':1,'total_reservation_USD':'1.05','authorize_paid_POST':False,'automatic_retry':False,'fallback':False,'pricing_sha256':hashlib.sha256(pricing).hexdigest()}
    raw=canonical(lock);(out/'REQUEST_SET_LOCK.json').write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();(out/'REQUEST_SET_SHA256.txt').write_text(sha+'\n','utf-8');return lock,sha

def worker():
    # No real key, HTTP and SMTP are denied by the unchanged simulation controller.
    import socket
    original_connect=socket.socket.connect
    def deny(sock,address):
        if isinstance(address,tuple) and address[0] in ('127.0.0.1','::1'):return original_connect(sock,address)
        raise AssertionError('offline test attempted an external socket')
    socket.socket.connect=deny
    from mvp_three_live import main
    sys.argv=[sys.argv[0]]+sys.argv[2:];main()

def run(out,source):
    out.mkdir(exist_ok=False);bundle=out/'synthetic';lock,sha=synthetic_bundle(bundle,source);checks=[]
    load_set(bundle,sha);assert batch_spec(lock)[2:]==(35,'1.05');checks.append('35 ordered watchlist bindings')
    for mutation in ('count','reserve','duplicate','unknown','business','body','hash'):
        path=bundle/'REQUEST_SET_LOCK.json';old=path.read_bytes();v=json.loads(old)
        if mutation=='count':v['max_total_POSTs']=36
        elif mutation=='reserve':v['total_reservation_USD']='.09'
        elif mutation=='duplicate':v['members'][1]['symbol']=v['members'][0]['symbol']
        elif mutation=='unknown':v['members'][0]['symbol']='UNKNOWN'
        elif mutation=='business':v['business_commit']='f'*40
        elif mutation=='body':v['members'][0]['request_sha256']='e'*64
        elif mutation=='hash':pass
        raw=canonical(v);path.write_bytes(raw);s=hashlib.sha256(raw).hexdigest() if mutation!='hash' else '0'*64
        try:load_set(bundle,s)
        except GuardStop:checks.append(mutation+' rejected')
        else:raise AssertionError('mutation accepted '+mutation)
        path.write_bytes(old)
    env={k:v for k,v in os.environ.items() if not any(t in k for t in ('API_KEY','PASSWORD','TOKEN','WEBHOOK'))};env.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',LITELLM_LOCAL_MODEL_COST_MAP='True')
    script=str(pathlib.Path(__file__).resolve());dest=out/'synthetic-results'
    command=[sys.executable,'-I',script,'--worker','--source',str(source),'--bundle',str(bundle),'--out',str(dest),'--batch-sha',sha,'--simulate','--inject-failure','MU']
    p=subprocess.run(command,env=env,capture_output=True,timeout=180);(out/'PROCESS.log').write_bytes(p.stdout+p.stderr);assert p.returncode==0
    result=json.loads((dest/'BATCH_RESULT.json').read_text('utf-8'));assert result['actual_paid_POSTs']==0 and result['transport_attempts']==35 and result['successful']==34 and result['failed']==1 and result['unpublished']==35
    assert result['fake_calls']==WATCHLIST and (dest/'XLE/REPORT.html').exists() and not (dest/'MU/REPORT.html').exists()
    checks.extend(['35 simulated calls, 0 real','MU timeout no retry, other 34 retained','35 unpublished','index and independent outputs'])
    # Even a caller setting execute-authorized cannot use this synthetic/offline lock.
    denied=[sys.executable,'-I',str(pathlib.Path(__file__).parent/'mvp_three_live.py'),'--source',str(source),'--bundle',str(bundle),'--out',str(out/'forbidden'),'--batch-sha',sha,'--execute-authorized']
    p=subprocess.run(denied,env=env,capture_output=True,timeout=30);(out/'UNAUTHORIZED_ATTEMPT.log').write_bytes(p.stdout+p.stderr);assert p.returncode!=0 and b'legacy_or_offline_bundle_not_live_authorizable' in p.stderr and not (out/'forbidden').exists();checks.append('offline bundle denied before key/claim/transport')
    (out/'TEST_RESULT.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'real_model_POSTs':0,'new_model_cost_USD':'0','data_mode':'SYNTHETIC_TEST_ONLY_NOT_MARKET_EVIDENCE','no_remote_claims_created':True},indent=2),'utf-8')
    print(json.dumps({'passed':len(checks),'synthetic_success':34,'synthetic_timeout':1,'real_model_POSTs':0}))

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':worker()
    else:
        import argparse
        p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path);a=p.parse_args();run(a.out.resolve(),a.source.resolve())
