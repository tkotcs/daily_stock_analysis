"""Three fresh-process startup/transport regressions; only fake GETs and POSTs."""
import argparse,asyncio,datetime as dt,hashlib,json,os,pathlib,socket,subprocess,sys


def child(source,out,mode):
    # Deliberately do NOT register source or preload src: main() must do it.
    assert str(source) not in sys.path and 'src' not in sys.modules
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
    import authorized_once as ao
    import nvda_frozen_once as controller
    import httpx
    from deepseek_post_guard import ENDPOINT,GuardStop
    assert 'src' not in sys.modules
    def no_network(*a,**k):raise AssertionError('real_network_forbidden')
    original_connect=socket.socket.connect
    def connect(sock,address):
        if isinstance(address,tuple) and address[0] in ('127.0.0.1','::1'):return original_connect(sock,address)
        return no_network()
    socket.socket.connect=connect;socket.create_connection=no_network
    bundle=pathlib.Path(__file__).resolve().parent.parent/'frozen/phase2r'
    body=json.loads((bundle/'ORIGINAL_REQUEST_PACKET.json').read_text('utf-8'))
    gets=[];transports=[]
    def fake_get(url,key=None):
        gets.append(url)
        if url.endswith('/models'):return b'{"data":[{"id":"deepseek-flash"}]}'
        if url.endswith('/balance'):return b'{"is_available":true,"balance_infos":[{"currency":"USD","total_balance":"1"}]}'
        assert url==ao.PRICING
        return (bundle/'OFFICIAL_PRICING.html').read_bytes()
    ao.LiveSession.__init__.__defaults__=(fake_get,)
    def fake_transport(transport,request):
        transports.append('fake_sync')
        if mode!='success':raise httpx.ReadTimeout('OFFLINE simulated timeout')
        raw=b'data: {"model":"deepseek-flash","choices":[{"delta":{"content":"OFFLINE ONLY"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200,content=raw,request=request)
    async def fake_async(transport,request):
        transports.append('fake_async');raise httpx.ReadTimeout('OFFLINE simulated timeout')
    # Installed BEFORE the real guard so it delegates only to these fakes.
    httpx.HTTPTransport.handle_request=fake_transport
    httpx.AsyncHTTPTransport.handle_async_request=fake_async
    async def async_attempt():
        async with httpx.AsyncClient() as client:
            try:await client.post(ENDPOINT,json=body)
            except GuardStop:pass
    def fake_dispatch(analyzer,packet,config):
        assert 'src.core.trading_calendar' in sys.modules
        assert config.litellm_model=='deepseek/deepseek-flash' and not config.litellm_fallback_models
        assert ao.canonical_sha(packet)==ao.REVIEWED_16K_SHA
        if mode=='async_timeout':asyncio.run(async_attempt())
        else:
            with httpx.Client() as client:
                try:client.post(ENDPOINT,json=packet)
                except GuardStop:pass
        # Sync and async must share the same allowance. This explicit second
        # test attempt must be blocked before it reaches the fake transport.
        asyncio.run(async_attempt())
        assert len(transports)==1 and len(gets)==3
        raise GuardStop('OFFLINE_TEST_STOP_no_model_report')
    controller.dispatch_frozen=fake_dispatch
    now=dt.datetime.now(dt.timezone.utc)
    auth={'authorize_paid_post':True,'authorization_reference':'Phase2U OFFLINE ONLY '+ao.REVIEWED_16K_SHA,
          'secret_upload_approval_reference':'OFFLINE placeholder only','run_id':'offline-'+mode,
          'fixed_commit':ao.REVIEWED_16K_FIXED,'request_sha256':ao.REVIEWED_16K_SHA,
          'analysis_asof':ao.REVIEWED_16K_ASOF,'target_session':'2026-10-15',
          'reservation_usd':'.03','allow_peak_test':True,
          'pricing_sha256':hashlib.sha256((bundle/'OFFICIAL_PRICING.html').read_bytes()).hexdigest(),
          'expires_at':min(now+dt.timedelta(minutes=5),dt.datetime.fromisoformat(ao.REVIEWED_16K_DEADLINE)).isoformat()}
    out.parent.mkdir(parents=True,exist_ok=True)
    authfile=out.parent/('fixture-'+mode+'.json');authfile.write_text(json.dumps(auth),encoding='utf-8')
    os.environ.update(GITHUB_ACTIONS='true',GITHUB_RUN_ID=auth['run_id'],GITHUB_RUN_ATTEMPT='1',DEEPSEEK_API_KEY='offline-startup-placeholder')
    sys.argv=['nvda_frozen_once.py','--execute-authorized','--source',str(source),'--bundle',str(bundle),'--authorization',str(authfile),'--run-id',auth['run_id'],'--out',str(out)]
    try:controller.main()
    except SystemExit as exc:assert str(exc)=='STOP_review_evidence_do_not_retry'
    else:raise AssertionError('fixture_must_not_publish')
    guard=json.loads((out/'POST_GUARD_RESULT.json').read_text('utf-8'))
    assert guard['allowed_transport_attempts']==1 and guard['attempts']==2 and guard['blocked']==1
    assert len(transports)==1 and len(gets)==3
    (out/'OFFLINE_TEST_RESULT.json').write_text(json.dumps({'passed':True,'mode':mode,'fresh_process':True,
        'src_not_preloaded':True,'real_main_called':True,'LiveSession_initialized':True,'guard_installed':True,
        'fake_transports':len(transports),'explicit_second_attempt_blocked':True,'automatic_retries':0,
        'real_POSTs':0,'real_model_cost_USD':'0','all_usage_is_synthetic_not_supplier_usage':True}),encoding='utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--child',choices=['success','sync_timeout','async_timeout'])
    a=p.parse_args();source=a.source.resolve();out=a.out.resolve()
    if a.child:return child(source,out,a.child)
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for mode in ('success','sync_timeout','async_timeout'):
        env={k:v for k,v in os.environ.items() if not any(x in k for x in ('API_KEY','PASSWORD','TOKEN','APP_SECRET','WEBHOOK'))}
        env.update(PYTHONDONTWRITEBYTECODE='1',LITELLM_LOCAL_MODEL_COST_MAP='True')
        run=subprocess.run([sys.executable,'-I',str(pathlib.Path(__file__).resolve()),'--source',str(source),'--out',str(out/mode),'--child',mode],
            cwd=out,env=env,capture_output=True,timeout=90)
        (out/(mode+'-process.log')).write_bytes(run.stdout+run.stderr)
        assert run.returncode==0,'fresh-process regression failed: '+mode
        rows.append(json.loads((out/mode/'OFFLINE_TEST_RESULT.json').read_text('utf-8')))
    (out/'STARTUP_TEST_SUMMARY.json').write_text(json.dumps({'passed':len(rows),'tests':rows,'real_POSTs':0,'new_model_cost_USD':'0'},indent=2),encoding='utf-8')
    print('Three isolated startup/guard regressions passed; real POSTs 0.')


if __name__=='__main__':main()
