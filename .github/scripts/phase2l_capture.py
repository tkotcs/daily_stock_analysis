"""Offline native DSA/LiteLLM YAML capture; no live mode or credential input."""
import argparse, copy, hashlib, ipaddress, json, os, pathlib, smtplib, socket, subprocess, sys

def main():
    p=argparse.ArgumentParser()
    for name in ('source','fixtures','out'): p.add_argument('--'+name,required=True,type=pathlib.Path)
    a=p.parse_args(); source=a.source.resolve(); fixtures=a.fixtures.resolve(); out=a.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()=='f93a7609e569e3b6c6372e652a3d36a27225d783'
    before={p.relative_to(fixtures).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.rglob('*') if p.is_file()}
    for k in list(os.environ):
        if any(s in k for s in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')) or k in ('LLM_CHANNELS','LITELLM_CONFIG','OPENAI_BASE_URL'):os.environ.pop(k,None)
    root=pathlib.Path(__file__).resolve().parents[2]
    os.environ.update(DEEPSEEK_API_KEY='offline-placeholder-never-transmitted',LITELLM_CONFIG=str(root/'.github/phase2l-deepseek.yaml'),LITELLM_MODEL='deepseek/deepseek-flash',LITELLM_FALLBACK_MODELS='',LITELLM_LOCAL_MODEL_COST_MAP='True',REPORT_INTEGRITY_RETRY='0',REPORT_LANGUAGE='zh',SINGLE_STOCK_NOTIFY='false',MARKET_REVIEW_ENABLED='false',AGENT_MODE='false',DATABASE_PATH=str(out/'offline.sqlite'))
    sys.path.insert(0,str(source))
    original=socket.socket.connect
    def deny(*args,**kwargs):raise AssertionError('external_network_or_notification_forbidden')
    def connect(sock,address):
        if isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback:return original(sock,address)
        return deny()
    socket.socket.connect=connect;socket.create_connection=deny;smtplib.SMTP=deny;smtplib.SMTP_SSL=deny
    from deepseek_post_guard import OnePostGuard, PreflightIntercept
    from phase2l_inputs import correct_inputs
    from authorized_once import canonical_sha,with_usage_options
    packet=json.loads((fixtures/'ORIGINAL_REQUEST_PACKET.json').read_text('utf-8'))
    context=json.loads((fixtures/'ORIGINAL_ENHANCED_CONTEXT.json').read_text('utf-8'))[0]
    packet,context,changes=correct_inputs(packet,context)
    from src.config import get_config
    from src.analyzer import GeminiAnalyzer
    from src.notification import NotificationService
    NotificationService.send=deny
    config=get_config();analyzer=GeminiAnalyzer(config=config)
    assert len(config.llm_model_list)==1 and not config.litellm_fallback_models
    assert analyzer._router is not None
    # Upstream ignores YAML router_settings; do not pretend otherwise.
    previous_retries=analyzer._router.num_retries
    analyzer._router.num_retries=0
    original_dispatch=analyzer._dispatch_litellm_completion
    def dispatch(model,kwargs,*args,**kw):return original_dispatch(model,with_usage_options(kwargs),*args,**kw)
    analyzer._dispatch_litellm_completion=dispatch
    guard=OnePostGuard(preflight=True);guard.install();intercepted=False
    try:
        analyzer._call_litellm_impl(packet['messages'][1]['content'],{'temperature':.7,'max_output_tokens':8192},system_prompt=packet['messages'][0]['content'],stream=True)
    except PreflightIntercept:intercepted=True
    finally:guard.restore()
    assert intercepted and guard.allowed==0 and guard.attempts==1
    wire=guard.captured[0]['body']
    assert wire['thinking']=={'type':'disabled'} and wire['model']=='deepseek-flash'
    assert wire['max_tokens']==8192 and wire['stream_options']=={'include_usage':True}
    assert wire['messages']==packet['messages']
    def save(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('ORIGINAL_REQUEST_PACKET.json',wire);save('PREPARED_CONTEXT.json',context);save('INPUT_CORRECTIONS.json',changes)
    summary={'request_sha256':canonical_sha(wire),'business_commit':'f93a7609e569e3b6c6372e652a3d36a27225d783','source_material':'saved Phase2K frozen inputs; offline replay, not fresh quotes','target_session':context['date'],'analysis_asof':'2026-10-15T12:42:02.263395+00:00','model':wire['model'],'endpoint':guard.captured[0]['url'],'thinking':wire['thinking'],'max_tokens':wire['max_tokens'],'include_usage':True,'router_single_deployment':True,'upstream_router_default_retries':previous_retries,'controller_router_retries':analyzer._router.num_retries,'fallbacks':[],'guard_attempts':guard.attempts,'blocked_before_network':guard.blocked,'real_paid_POSTs':guard.allowed,'real_key_injected':False,'mandatory_schema_changed':False}
    import tiktoken
    summary['cl100k_input_estimate']=sum(len(tiktoken.get_encoding('cl100k_base').encode(m['content'])) for m in wire['messages'])+4*len(wire['messages'])+3
    summary['compact_json_bytes']=len(json.dumps(wire,ensure_ascii=False,separators=(',',':')).encode())
    save('CAPTURE_SUMMARY.json',summary)
    # Historical raw responses: native parser and integrity only, no repair call.
    records=[]
    for label in ('2E','2H','2K'):
        raw=(fixtures/(label+'_MODEL_RAW_TEXT.txt')).read_text('utf-8')
        parsed=analyzer._parse_response(raw,'NVDA','英伟达')
        passed,missing=analyzer._check_content_integrity(parsed,require_phase_decision=True)
        if label=='2K':
            assert not parsed.success and not passed
            records.append({'case':label,'parser_success':False,'native_integrity_passed':False,'publish_allowed':False,'render_skipped':'invalid response must not produce a publishable fallback score','repairs':0})
        else:
            assert parsed.success and passed
            md=NotificationService().generate_single_stock_report(parsed)
            (out/(label+'_REPLAY.md')).write_text(md,encoding='utf-8')
            records.append({'case':label,'parser_success':True,'native_integrity_passed':True,'publish_allowed':False,'reason':'historical manual fact review failed; successful rendering does not establish quality','repairs':0})
    save('HISTORICAL_REPLAY.json',records)
    assert before=={p.relative_to(fixtures).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.rglob('*') if p.is_file()}
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
