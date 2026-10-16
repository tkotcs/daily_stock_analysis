"""One manually approved frozen request through the original DSA client; no prompt build."""
import argparse,atexit,hashlib,json,os,pathlib,smtplib,subprocess,sys
from datetime import datetime,timezone
from authorized_once import LiveSession,SafeWriter,canonical_sha,authorized_business,REVIEWED_16K_SHA
from deepseek_post_guard import OnePostGuard,GuardStop

def load_packet(bundle,expected):
    packet=json.loads((bundle/'ORIGINAL_REQUEST_PACKET.json').read_text(encoding='utf-8'))
    if canonical_sha(packet)!=expected:raise GuardStop('frozen_packet_hash_mismatch')
    return packet

def dispatch_frozen(analyzer,packet,config):
    """No analyze()/prompt builder, data fetcher, recovery helper, or retry loop."""
    kwargs=dict(packet);kwargs['model']=config.litellm_model
    kwargs['num_retries']=0  # LiteLLM/OpenAI control, excluded from the HTTP body.
    stream=analyzer._dispatch_litellm_completion(config.litellm_model,kwargs,config=config,use_channel_router=False,router_model_names=set())
    return analyzer._consume_litellm_stream(stream,model=config.litellm_model,usage_model='deepseek-flash',provider='deepseek')

def render_native_report(parsed):
    """Render locally with the upstream constructor; never dispatch a request."""
    from src.notification import NotificationService
    return NotificationService().generate_single_stock_report(parsed)

def research_quality(parsed,native_integrity):
    """Small required risk-plan gate, not a substitute for human fact review."""
    from src.trade_plan import calculate_risk_plan
    dashboard=getattr(parsed,'dashboard',None)
    dashboard=dashboard if isinstance(dashboard,dict) else {}
    battle=dashboard.get('battle_plan')
    battle=battle if isinstance(battle,dict) else {}
    try:rows,cap,errors=calculate_risk_plan(battle.get('risk_plan'))
    except (TypeError,ValueError,OverflowError):rows,cap,errors=[],None,['risk_plan_malformed']
    passed=bool(getattr(parsed,'success',False) and native_integrity and rows and not errors)
    return {'passed':passed,'risk_plan_errors':errors,'calculated_scenarios':rows,
            'shared_position_cap':cap,'native_parser_success':bool(getattr(parsed,'success',False)),
            'native_integrity':bool(native_integrity),'manual_full_fact_review_required':True,
            'published':False,'notifications_sent':0}

def render_review_report(session,parsed,native_integrity,out,key):
    quality=research_quality(parsed,native_integrity)
    session.save('RESEARCH_QUALITY_RESULT.json',quality)
    if not quality['passed']:
        session.save('PUBLISH_BLOCKED.json',{'reason':'research_quality_NO_GO','risk_plan_errors':quality['risk_plan_errors'],'render_skipped':True,'published':False,'notifications_sent':0})
        return quality
    report=render_native_report(parsed)
    (out/'NATIVE_NVDA_REPORT.md').write_text(report.replace(key,'[REDACTED]'),encoding='utf-8')
    return quality


def apply_supplied_news_metadata(parsed, contexts, audit):
    """Only bind saved preparation metadata; never rewrite model narrative."""
    news = audit.get('selected_news') or []
    parsed.search_performed = False
    parsed.news_result_count = None
    parsed.news_evidence_present = bool(news)
    note = '官方RSS标题及元数据已提供，未提供新闻全文；综合新闻搜索未执行。不能据此排除其他重大利空。' if news else '未提供可用官方RSS；综合新闻搜索未执行。'
    parsed.data_sources = note + ('；' + parsed.data_sources if parsed.data_sources else '')
    return parsed

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-authorized',action='store_true');parser.add_argument('--source',required=True);parser.add_argument('--bundle',required=True);parser.add_argument('--authorization',required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args()
    if not args.execute_authorized:raise SystemExit('default_off_no_POST')
    if os.getenv('GITHUB_ACTIONS')!='true' or os.getenv('GITHUB_RUN_ID')!=args.run_id or os.getenv('GITHUB_RUN_ATTEMPT')!='1':raise SystemExit('protected_manual_GitHub_run_required')
    source=pathlib.Path(args.source).resolve();bundle=pathlib.Path(args.bundle).resolve();out=pathlib.Path(args.out).resolve();out.mkdir(exist_ok=False)
    auth=json.loads(pathlib.Path(args.authorization).read_text(encoding='utf-8'))
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,encoding='utf-8').strip()==authorized_business(auth)
    assert not (source/'.env').exists()
    packet=load_packet(bundle,auth['request_sha256'])
    summary=json.loads((bundle/'CAPTURE_SUMMARY.json').read_text(encoding='utf-8'))
    if summary['request_sha256']!=auth['request_sha256'] or summary['analysis_snapshot_asof']!=auth['analysis_asof']:raise SystemExit('locked_bundle_identity_mismatch')
    now=datetime.now(timezone.utc);snapshot=datetime.fromisoformat(auth['analysis_asof'])
    if snapshot.tzinfo is None or snapshot>now or (now-snapshot).total_seconds()>86400:raise SystemExit('snapshot_invalid_or_expired_no_POST')
    key=os.getenv('DEEPSEEK_API_KEY','').strip()
    if not key:raise SystemExit('missing_key_no_POST')
    log=SafeWriter(out/'REDACTED_PROCESS.log',key);sys.stdout=log;sys.stderr=log;atexit.register(log.close)
    # Material checks in LiveSession need the pinned native trading calendar.
    sys.path.insert(0,str(source))
    session=LiveSession(out,auth,key,args.run_id)
    session.save('AUTHORIZATION_USED.json',auth)
    for name in list(os.environ):
        if name.endswith(('_API_KEY','_API_KEYS','_PASSWORD','_ACCESS_TOKEN','_APP_SECRET','_WEBHOOK_URL')) or name in ('TUSHARE_TOKEN','MODELFLARE_KEY','AIHUBMIX_KEY','TELEGRAM_BOT_TOKEN','GH_TOKEN','GITHUB_TOKEN','LITELLM_CONFIG','LLM_CHANNELS','DEEPSEEK_API_BASE','DEEPSEEK_BASE_URL','OPENAI_BASE_URL','OPENAI_API_BASE') or name.startswith('LLM_'):os.environ.pop(name,None)
    os.environ.update(DEEPSEEK_API_KEY=key,DEEPSEEK_API_BASE='https://api.deepseek.com',LITELLM_MODEL='deepseek/deepseek-flash',LITELLM_FALLBACK_MODELS='',LITELLM_LOCAL_MODEL_COST_MAP='True',REPORT_INTEGRITY_RETRY='0',ENABLE_FUNDAMENTAL_PIPELINE='false',ENABLE_REALTIME_QUOTE='false',AGENT_MODE='false',SCHEDULE_ENABLED='false',MARKET_REVIEW_ENABLED='false',DAILY_MARKET_CONTEXT_ENABLED='false',SINGLE_STOCK_NOTIFY='false',REPORT_LANGUAGE='zh',DATABASE_PATH=str(out/'native.sqlite'))
    guard=OnePostGuard(preflight=False,before_send=session.approve,on_response=session.on_response,on_error=session.on_error);guard.install()
    blocked={'notification':0,'other_network':0}
    def deny(kind):
        def stop(*a,**kw):blocked[kind]+=1;raise GuardStop('forbidden_'+kind)
        return stop
    smtplib.SMTP=deny('notification');smtplib.SMTP_SSL=deny('notification')
    import requests,curl_cffi.requests as curl
    requests.Session.request=deny('other_network');curl.Session.request=deny('other_network')
    from src.core.trading_calendar import get_effective_trading_date,_XCALS_AVAILABLE
    if not _XCALS_AVAILABLE or get_effective_trading_date('us',current_time=now).isoformat()!=auth['target_session']:raise SystemExit('approved_session_no_longer_latest_no_POST')
    from src.config import get_config
    from src.analyzer import GeminiAnalyzer
    from src.notification import NotificationService
    from src.notification_sender.email_sender import EmailSender
    NotificationService.send=deny('notification');EmailSender.send_to_email=deny('notification')
    config=get_config();analyzer=GeminiAnalyzer(config=config)
    if analyzer._router is not None or config.litellm_model!='deepseek/deepseek-flash' or config.litellm_fallback_models:raise SystemExit('unexpected_route_no_POST')
    failure=None;parsed=None;quality=None
    session.save('AUTHORIZED_REQUEST_PACKET.json',packet)
    try:
        text,usage=dispatch_frozen(analyzer,packet,config)
        session.save('NATIVE_NORMALIZED_USAGE.json',usage)
        parsed=analyzer._parse_response(text,'NVDA','英伟达');parsed.raw_response=text;parsed.model_used=config.litellm_model;parsed.report_language='zh';parsed.search_performed=False
        contexts=json.loads((bundle/'ORIGINAL_ENHANCED_CONTEXT.json').read_text(encoding='utf-8'))
        audit_path=bundle/'RESEARCH_MATERIAL_AUDIT.json'
        if audit_path.exists():
            apply_supplied_news_metadata(parsed,contexts,json.loads(audit_path.read_text(encoding='utf-8')))
        parsed.market_snapshot=analyzer._build_market_snapshot(contexts[0])
        session.save('NATIVE_ANALYSIS_RESULT.json',parsed.to_dict())
        passed,missing=analyzer._check_content_integrity(parsed,require_phase_decision=True)
        session.save('NATIVE_INTEGRITY_RESULT.json',{'passed':passed,'missing_fields':missing,'repairs_called':False,'parser_success':parsed.success})
        if auth['request_sha256']==REVIEWED_16K_SHA:
            quality=render_review_report(session,parsed,passed,out,key)
        else:
            report=render_native_report(parsed)
            (out/'NATIVE_NVDA_REPORT.md').write_text(report.replace(key,'[REDACTED]'),encoding='utf-8')
    except BaseException as exc:failure=type(exc).__name__
    finally:
        session.finish()
        session.save('POST_GUARD_RESULT.json',{'run_id':args.run_id,'authorized_sha256':auth['request_sha256'],'wire':guard.captured,'attempts':guard.attempts,'allowed_transport_attempts':guard.allowed,'blocked':guard.blocked,'error_category':failure,'other_calls':blocked,'prompt_rebuilt':False,'new_market_or_news_fetched':False,'automatic_retry':False,'actual_execution_at':now.isoformat()})
    if failure or guard.allowed!=1:raise SystemExit('STOP_review_evidence_do_not_retry')
    if quality is not None and not quality['passed']:raise SystemExit('STOP_research_quality_NO_GO_no_publish_no_retry')
    result=json.loads((out/'RESPONSE_RESULT.json').read_text(encoding='utf-8'))
    if result['result_unknown'] or result['truncated'] or result['cost_estimate']['status'].startswith('unknown') or not parsed or not parsed.success:raise SystemExit('STOP_result_requires_review_no_retry')
if __name__=='__main__':main()
