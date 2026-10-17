"""Prepared manual watchlist adapter using the existing client/session/guard.

Default OFF. No collection, retries, fallback, notification or budget database.
"""
import argparse,atexit,datetime as dt,hashlib,html,json,os,pathlib,smtplib,subprocess,sys
from decimal import Decimal

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from authorized_once import LiveSession,SafeWriter,canonical_sha,free_get,MANUAL_BUSINESS
from free_market_validation import WATCHLIST
from deepseek_post_guard import OnePostGuard,GuardStop,ENDPOINT
from nvda_frozen_once import dispatch_frozen,render_native_report
from remote_execution_claim import GitHubAPI,RemoteExecutionClaim

SYMBOLS=('NVDA','MU','QQQ');BUSINESS='a1daaa302b3a72fb5694c9872ceecf2c4dc0b6e4'


def batch_spec(lock):
    if lock.get('profile')=='mvp_three_v1':return BUSINESS,list(SYMBOLS),3,'0.09'
    if lock.get('profile')!='mvp_manual_v2':raise GuardStop('batch_profile_invalid')
    symbols=[m.get('symbol') for m in lock.get('members',[])]
    if not symbols or len(symbols)>len(WATCHLIST) or len(set(symbols))!=len(symbols) or symbols!=[c for c in WATCHLIST if c in symbols]:
        raise GuardStop('manual_batch_watchlist_or_order_invalid')
    return MANUAL_BUSINESS,symbols,len(symbols),str(Decimal('.03')*len(symbols))


def load_set(bundle,approved_sha):
    raw=(bundle/'REQUEST_SET_LOCK.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=approved_sha:raise GuardStop('batch_hash_mismatch')
    lock=json.loads(raw)
    business,symbols,cap,reserve=batch_spec(lock)
    if lock.get('business_commit')!=business:raise GuardStop('batch_profile_invalid')
    if lock.get('authorize_paid_POST') is not False or lock.get('max_total_POSTs')!=cap or lock.get('max_POSTs_per_symbol')!=1 or lock.get('total_reservation_USD')!=reserve:raise GuardStop('batch_call_limits_invalid')
    if lock.get('automatic_retry') is not False or lock.get('fallback') is not False:raise GuardStop('retry_or_fallback_forbidden')
    members=lock['members']
    if [m.get('symbol') for m in members]!=symbols:raise GuardStop('batch_symbols_or_duplicates_invalid')
    packets={};contexts={}
    for m in members:
        code=m['symbol'];body=(bundle/code/'FINAL_REQUEST.json').read_bytes();context=(bundle/code/'NATIVE_CONTEXT.json').read_bytes()
        packet=json.loads(body)
        if hashlib.sha256(body).hexdigest()!=m['request_sha256'] or canonical_sha(packet)!=m['request_sha256']:raise GuardStop('full_request_hash_mismatch')
        if hashlib.sha256(context).hexdigest()!=m['context_sha256'] or json.loads(context)['code']!=code:raise GuardStop('context_identity_mismatch')
        if packet.get('model')!='deepseek-flash' or packet.get('thinking')!={'type':'disabled'} or packet.get('max_tokens')!=16384 or packet.get('stream') is not True or packet.get('stream_options')!={'include_usage':True}:raise GuardStop('request_parameters_changed')
        if m.get('reservation_USD')!='0.03' or not m.get('reservation_check'):raise GuardStop('unreviewed_reservation')
        packets[code]=packet;contexts[code]=json.loads(context)
    if hashlib.sha256((bundle/'OFFICIAL_PRICING.html').read_bytes()).hexdigest()!=lock['pricing_sha256']:raise GuardStop('pricing_material_mismatch')
    return lock,packets,contexts


def render_status_index(rows,mode):
    text='<h1>手动研究报告目录</h1><p>模型完成不等于内容获准发布；全部待人工审阅。</p>'
    for label,success in [('执行成功（仍未发布）',True),('执行失败',False)]:
        text+='<h2>'+label+'</h2><ul>'
        for row in rows:
            if bool(row.get('execution_success'))!=success:continue
            code=row['symbol'];link=f'<a href="{code}/REPORT.html">{code}</a>' if success else html.escape(code)
            text+='<li>'+link+' '+html.escape(row['status']+' '+row.get('reason',''))+f'；未发布 <a href="{code}/STATUS.json">状态</a></li>'
        text+='</ul>'
    note='合成数据/模拟模型，不是真实行情或研究验收。' if mode=='SIMULATED' else '真实模型原文，待人工审阅。'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><body><p>'+html.escape(mode+' '+note)+'</p>'+text+'</body></html>'


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--bundle',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--batch-sha',required=True)
    group=p.add_mutually_exclusive_group(required=True);group.add_argument('--simulate',action='store_true');group.add_argument('--execute-authorized',action='store_true')
    p.add_argument('--authorization',type=pathlib.Path);p.add_argument('--inject-failure',choices=WATCHLIST)
    a=p.parse_args();source=a.source.resolve();bundle=a.bundle.resolve();out=a.out.resolve()
    if a.inject_failure and not a.simulate:raise GuardStop('fault_injection_is_offline_only')
    lock,packets,contexts=load_set(bundle,a.batch_sha)
    business,symbols,cap,reserve=batch_spec(lock)
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()!=business or (source/'.env').exists():raise GuardStop('business_or_env_mismatch')
    sys.path.insert(0,str(source))  # Before LiveSession calendar/material checks.
    claim=None
    if a.execute_authorized:
        if lock.get('profile')!='mvp_manual_v2' or lock.get('offline_only'):raise GuardStop('legacy_or_offline_bundle_not_live_authorizable')
        if os.getenv('GITHUB_ACTIONS')!='true' or os.getenv('GITHUB_RUN_ATTEMPT')!='1' or not a.authorization:raise GuardStop('protected_first_manual_run_required')
        approval=json.loads(a.authorization.read_text('utf-8'))
        if approval.get('authorize_paid_posts') is not True or approval.get('batch_sha256')!=a.batch_sha or approval.get('run_id')!=os.getenv('GITHUB_RUN_ID') or approval.get('max_total_POSTs')!=cap or approval.get('reservation_USD')!=reserve or a.batch_sha not in approval.get('authorization_reference',''):raise GuardStop('new_explicit_batch_authorization_required')
        key=os.getenv('DEEPSEEK_API_KEY','').strip()
        if not key:raise GuardStop('missing_key_no_POST')
        claim=RemoteExecutionClaim(GitHubAPI(os.getenv('GITHUB_REPOSITORY',''),os.getenv('GITHUB_TOKEN','')),
                                   a.batch_sha,approval['run_id'],os.getenv('GITHUB_SHA',''),symbols=symbols)
        # Validate expiry/calendar BEFORE consuming remote reservations.
        now=dt.datetime.now(dt.timezone.utc)
        from src.core.trading_calendar import get_effective_trading_date,_XCALS_AVAILABLE
        if not _XCALS_AVAILABLE:raise GuardStop('calendar_unavailable_no_claim')
        for member in lock['members']:
            if now>=dt.datetime.fromisoformat(member['material_expires_at']) or get_effective_trading_date('us',current_time=now).isoformat()!=member['target_session']:
                raise GuardStop('material_EXPIRED_no_claim_no_POST')
    else:
        approval={'run_id':'OFFLINE-MVP','authorization_reference':'OFFLINE ONLY '+a.batch_sha,'secret_upload_approval_reference':'OFFLINE placeholder'};key='offline-three-placeholder'
    for name in list(os.environ):
        if any(x in name for x in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')) or name in ('GH_TOKEN','GITHUB_TOKEN','LLM_CHANNELS','LITELLM_CONFIG','OPENAI_BASE_URL','OPENAI_API_BASE','DEEPSEEK_BASE_URL'):
            os.environ.pop(name,None)
    os.environ.update(DEEPSEEK_API_BASE='https://api.deepseek.com',LITELLM_LOCAL_MODEL_COST_MAP='True',DEEPSEEK_API_KEY=key)
    out.mkdir(parents=True,exist_ok=False);rows=[];total=0
    if claim:
        try:
            records=claim.reserve(lock['members'])
            (out/'REMOTE_CLAIM.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        except GuardStop:
            (out/'CLAIM_BLOCKED.json').write_text(json.dumps({'reason':'remote_reservation_failed_or_unknown_no_retry',
                'actual_paid_POSTs':0,'partial_reservations_never_released':True}),encoding='utf-8')
            raise
    os.environ.update(DATABASE_PATH=str(out/'native.sqlite'),LOG_DIR=str(out/'logs'),REPORTS_DIR=str(out/'reports'),
                      SCHEDULE_ENABLED='false',MARKET_REVIEW_ENABLED='false',DAILY_MARKET_CONTEXT_ENABLED='false',
                      AGENT_MODE='false',SINGLE_STOCK_NOTIFY='false',SEARXNG_PUBLIC_INSTANCES_ENABLED='false')
    if a.simulate:os.environ['LLM_USAGE_HMAC_SECRET']='offline-mvp-public-fixture-signing-key-not-a-real-key'
    log=SafeWriter(out/'REDACTED_PROCESS.log',key);stdout,stderr=sys.stdout,sys.stderr;sys.stdout=sys.stderr=log;atexit.register(log.close)
    def deny(*args,**kwargs):raise GuardStop('unapproved_network_or_notification')
    import requests,curl_cffi.requests as curl,httpx
    requests.Session.request=deny;curl.Session.request=deny;smtplib.SMTP=deny;smtplib.SMTP_SSL=deny
    from src.config import Config
    from src.analyzer import GeminiAnalyzer
    from src.notification import NotificationService
    NotificationService.send=deny
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
    config=Config(litellm_model='deepseek/deepseek-flash',deepseek_api_keys=[key],litellm_fallback_models=[],report_integrity_retry=0)
    analyzer=GeminiAnalyzer(config=config)
    if analyzer._router is not None:raise GuardStop('router_forbidden')
    fake_symbol={'code':None};fake_calls=[]
    if a.simulate:
        def get(url,unused=None):
            if url.endswith('/models'):return b'{"data":[{"id":"deepseek-flash"}]}'
            if url.endswith('/balance'):return b'{"is_available":true,"balance_infos":[{"currency":"USD","total_balance":"1"}]}'
            return (bundle/'OFFICIAL_PRICING.html').read_bytes()
        from mvp_three import fixture
        def fake(transport,request):
            code=fake_symbol['code'];fake_calls.append(code)
            if a.inject_failure==code:raise httpx.ReadTimeout('OFFLINE injected timeout')
            text=json.dumps(fixture(code,contexts[code]),ensure_ascii=False)
            sse='data: '+json.dumps({'model':'deepseek-flash','choices':[{'index':0,'delta':{'content':text},'finish_reason':'stop'}]},ensure_ascii=False)+'\n\ndata: [DONE]\n\n'
            return httpx.Response(200,content=sse.encode(),headers={'content-type':'text/event-stream'},request=request)
        httpx.HTTPTransport.handle_request=fake
    else:get=free_get
    try:
        for member in lock['members']:
            code=member['symbol'];dest=out/code;dest.mkdir();fake_symbol['code']=code
            row={'symbol':code,'mode':'SIMULATED' if a.simulate else 'REAL_MODEL_PENDING_MANUAL_REVIEW','published':False,'request_sha256':member['request_sha256']}
            guard=None;session=None
            try:
                if total>=cap:raise GuardStop('batch_POST_cap')
                expiry=min(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=15),dt.datetime.fromisoformat(member['material_expires_at']))
                auth={'test_profile':lock['profile'],'authorize_paid_post':True,'authorization_reference':approval['authorization_reference']+' '+member['request_sha256'],
                      'secret_upload_approval_reference':approval.get('secret_upload_approval_reference','existing approved repository Secret'),'run_id':approval['run_id'],'fixed_commit':business,
                      'batch_sha256':a.batch_sha,'request_sha256':member['request_sha256'],'symbol':code,'analysis_asof':member['analysis_asof'],'target_session':member['target_session'],
                      'material_expires_at':member['material_expires_at'],'expires_at':expiry.isoformat(),'pricing_sha256':lock['pricing_sha256'],'reservation_usd':'.03','allow_peak_test':True}
                session=LiveSession(dest,auth,key,approval['run_id'],get=get)
                session.save('AUTHORIZATION_USED.json',auth)
                def approve(body):
                    session.approve(body)
                    if claim:claim.before_send(code,canonical_sha(body))
                    session.check_material()
                    if dt.datetime.now(dt.timezone.utc)>=expiry:raise GuardStop('authorization_expired_during_remote_check')
                guard=OnePostGuard(preflight=False,before_send=approve,on_response=session.on_response,on_error=session.on_error);guard.install()
                text,usage=dispatch_frozen(analyzer,packets[code],config)
                session.finish();response=json.loads((dest/'RESPONSE_RESULT.json').read_text('utf-8'))
                if response['result_unknown'] or response['truncated'] or response['finish_reason']!='stop':raise GuardStop('response_unknown_or_truncated_do_not_retry')
                if not a.simulate and response['cost_estimate']['status'].startswith('unknown'):raise GuardStop('supplier_usage_unknown_do_not_retry')
                _,model_json=analyzer._extract_analysis_json_object(text);session.save('PARSED_MODEL_JSON.json',model_json)
                parsed=analyzer._parse_response(text,code,contexts[code].get('stock_name',code));parsed.raw_response=text;parsed.report_language='zh';parsed.model_used='deepseek/deepseek-flash';parsed.search_performed=False
                parsed.market_snapshot=analyzer._build_market_snapshot(contexts[code])
                passed,missing=analyzer._check_content_integrity(parsed,require_phase_decision=True)
                session.save('NATIVE_INTEGRITY.json',{'passed':passed,'missing':missing,'manual_fact_review_required':True})
                if not parsed.success or not passed:raise GuardStop('native_JSON_or_integrity_failed_no_repair')
                note='模拟响应，不是供应商调用' if a.simulate else '真实DeepSeek响应，尚待人工事实审阅，不代表发布通过'
                md='# '+code+'\n\n> '+note+'；日线截止'+member['target_session']+'。\n\n'+render_native_report(parsed)
                (dest/'REPORT.md').write_text(md.replace(key,'[REDACTED]'),encoding='utf-8')
                import markdown2
                body=markdown2.markdown(md,safe_mode='escape',extras=['tables'])
                (dest/'REPORT.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font:16px/1.7 system-ui;max-width:960px;padding:16px;overflow-wrap:anywhere}pre{white-space:pre-wrap}table{display:block;overflow:auto}</style><body>'+body.replace(key,'[REDACTED]')+'</body></html>',encoding='utf-8')
                from src.trade_plan import calculate_risk_plan,is_watch_plan
                plan=(model_json.get('dashboard') or {}).get('battle_plan',{}).get('risk_plan')
                _,_,risk_errors=calculate_risk_plan(plan)
                if plan is None:risk_errors=[]  # No proposed trade, not fabricated numeric levels.
                session.save('RISK_PLAN_CHECK.json',{'errors':risk_errors,'watch_only':plan is None or is_watch_plan(plan),'manual_facts_review_required':True,'publish_accepted':False})
                row['status']='parsed_preview_requires_manual_review'
                row['risk_plan_errors']=risk_errors
                row['execution_success']=True
            except BaseException as exc:row.update(status='failed_no_retry',error_category=type(exc).__name__,reason=str(exc) if isinstance(exc,GuardStop) else 'inspect_redacted_evidence')
            finally:
                if session:session.finish()
                if guard:guard.restore();total+=guard.allowed
                row['transport_attempts']=guard.allowed if guard else 0;row['actual_paid_POSTs']=0 if a.simulate else row['transport_attempts']
                row['automatic_retry']=False
                (dest/'STATUS.json').write_text(json.dumps(row,ensure_ascii=False,indent=2).replace(key,'[REDACTED]'),encoding='utf-8');rows.append(row)
        summary={'mode':'SIMULATED' if a.simulate else 'REAL_MODEL_PENDING_MANUAL_REVIEW','batch_sha256':a.batch_sha,'symbols':rows,'transport_attempts':total,'actual_paid_POSTs':0 if a.simulate else total,'published':False,'fake_calls':fake_calls if a.simulate else None}
        summary.update(successful=sum(r.get('execution_success',False) for r in rows),failed=sum(r['status']=='failed_no_retry' for r in rows),unpublished=len(rows))
        (out/'index.html').write_text(render_status_index(rows,summary['mode']),encoding='utf-8')
        (out/'BATCH_RESULT.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:log.close();sys.stdout,sys.stderr=stdout,stderr
    print('Batch stopped after its authorized independent slots; no retry or notification.')


if __name__=='__main__':main()
