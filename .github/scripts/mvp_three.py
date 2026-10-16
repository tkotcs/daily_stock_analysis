"""Manual native DSA integration: fresh free Yahoo data, synthetic model only."""
import argparse,datetime as dt,hashlib,html,json,math,os,pathlib,re,smtplib,socket,subprocess,sys,time
from urllib.parse import urlsplit

SYMBOLS=('NVDA','MU','QQQ')
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from free_market_validation import WATCHLIST,ETFS,NAMES
NOTICE='模拟模型响应，仅验证流水线；行情为本次注明的数据来源，不是已通过验收的真实AI研报。'


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def fixture(code,context):
    t=context['today'];p=t['close'];note=NOTICE
    return {'stock_name':context.get('stock_name',code),'sentiment_score':50,'trend_prediction':'模拟观望',
      'operation_advice':'观望','decision_type':'hold','action':'watch','confidence_level':'低',
      'analysis_summary':note+' 财务仅为Yahoo聚合，发布日期未核验；没有执行综合新闻搜索，不推断不存在利空。',
      'technical_analysis':f"收盘{p}美元；MA60={t.get('ma60')}。状态与当日新穿越分别查看本地技术事实。",
      'fundamental_analysis':'仅使用随附Yahoo字段；缺失保留，ETF不适用企业财务，不推断利润质量。',
      'news_summary':'未执行新闻搜索，本轮没有新闻证据。','risk_warning':note,
      'dashboard':{'core_conclusion':{'one_sentence':note,'signal_type':'🟡观望',
          'position_advice':{'no_position':'模拟观望，不新建仓','has_position':'不生成真实仓位建议'}},
        'data_perspective':{'trend_status':{'ma_alignment':context.get('trend_analysis',{}).get('ma_alignment'),'is_bullish':False,'trend_score':50},
          'price_position':{'current_price':p,**{k:t.get(k) for k in ('ma5','ma10','ma20','ma60')}},
          'volume_analysis':{'volume_ratio':t.get('volume_ratio'),'volume_meaning':'今日量/此前5日均量，与昨日倍数不同'},
          'chip_structure':{'chip_health':'暂无可靠数据'}},
        'intelligence':{'latest_news':'未提供新闻','risk_alerts':[note,'财务并非逐项核验的官方披露'],'positive_catalysts':[],
          'earnings_outlook':'请查看财务来源审计，不补造缺失数字。'},
        'battle_plan':{'sniper_points':{'ideal_buy':'不适用：模拟观望','secondary_buy':'不适用','stop_loss':'不适用：未建立交易计划','take_profit':'不适用'},
          'position_strategy':{'suggested_position':'本轮不提供仓位建议','entry_plan':'等待真实研究单独验收','risk_control':'无交易执行'},
          'risk_plan':None,'action_checklist':['只核验流水线，不验证真实模型研究质量']},
        'phase_decision':{'phase_context':{'market':'us','trade_date':context['date']},'action_window':'研究预览',
          'immediate_action':'观望','watch_conditions':['等待真实模型独立授权及质量验收'],'next_check_time':'下一完整交易日之后',
          'confidence_reason':note,'data_limitations':['无实时行情','无新闻检索','财务公开时间未核验']}}}


def run_symbol(source,out,code,offline=None,inject=False):
    out.mkdir(parents=True,exist_ok=False);start=time.monotonic();trace=[];restricted=False
    def persist():save(out/'HTTP_TRACE.json',trace)
    import atexit;atexit.register(persist)
    for k in list(os.environ):
        if any(x in k for x in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')) or k in ('GH_TOKEN','GITHUB_TOKEN','LLM_CHANNELS','LITELLM_CONFIG','OPENAI_BASE_URL'):os.environ.pop(k,None)
    os.environ.update(DEEPSEEK_API_KEY='mvp-simulation-placeholder',LITELLM_MODEL='deepseek/deepseek-flash',
        LITELLM_CONFIG=str(source/'.github/phase2l-deepseek.yaml'),DEEPSEEK_API_BASE='https://api.deepseek.com',
        STOCK_ANALYSIS_MAX_TOKENS='16384',LITELLM_FALLBACK_MODELS='',LITELLM_LOCAL_MODEL_COST_MAP='True',
        REPORT_INTEGRITY_RETRY='0',GEMINI_REQUEST_DELAY='0',DATABASE_PATH=str(out/'native.sqlite'),
        LOG_DIR=str(out/'logs'),REPORTS_DIR=str(out/'reports'),ENABLE_REALTIME_QUOTE='false',ENABLE_CHIP_DISTRIBUTION='false',
        ENABLE_FUNDAMENTAL_PIPELINE='true',FUNDAMENTAL_RETRY_MAX='0',SEARXNG_PUBLIC_INSTANCES_ENABLED='false',
        AGENT_MODE='false',AGENT_SKILLS='',SINGLE_STOCK_NOTIFY='false',MARKET_REVIEW_ENABLED='false',
        DAILY_MARKET_CONTEXT_ENABLED='false',AUTO_BACKTEST_ENABLED='false',SCHEDULE_ENABLED='false',REPORT_LANGUAGE='zh',
        LLM_USAGE_HMAC_SECRET='offline-mvp-public-fixture-signing-key-not-a-real-credential')
    assert not (source/'.env').exists()
    sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent),str(source)]
    import httpx,requests,curl_cffi.requests as curl,yfinance as yf,pandas as pd
    from phase2j_free_guard import free_yahoo_get
    from deepseek_post_guard import GuardStop,OnePostGuard
    def deny(*a,**k):raise GuardStop('MVP_non_free_network_or_mail_forbidden')
    original=curl.Session.request
    def request(session,method,url,*a,**kw):
        nonlocal restricted
        if offline or restricted or not free_yahoo_get(method,url):return deny()
        kw['timeout']=15;kw['allow_redirects']=False
        row={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'method':method,'host':urlsplit(str(url)).hostname,'path':urlsplit(str(url)).path}
        try:
            response=original(session,method,url,*a,**kw);row['status']=response.status_code
            if response.status_code in (403,429):restricted=True
            if '/finance/chart/' in row['path']:
                name='chart-'+str(len(trace))+'.json';save(out/name,response.json());row['response_file']=name
            return response
        except Exception as e:row['error']=type(e).__name__;raise
        finally:trace.append(row);persist()
    curl.Session.request=request;requests.Session.request=deny
    original_connect=socket.socket.connect
    def connect(sock,address):
        if isinstance(address,tuple) and address[0] in ('127.0.0.1','::1'):return original_connect(sock,address)
        return deny()
    socket.socket.connect=connect;socket.create_connection=deny;smtplib.SMTP=deny;smtplib.SMTP_SSL=deny
    from src.core.trading_calendar import get_effective_trading_date
    from src.config import get_config
    from src.storage import get_db
    from src.core.pipeline import StockAnalysisPipeline
    from src.stock_analyzer import StockTrendAnalyzer
    from src.notification import NotificationService
    from src.enums import ReportType
    NotificationService.send=deny
    now=dt.datetime.now(dt.timezone.utc);target=get_effective_trading_date('us',current_time=now).isoformat()
    config=get_config();config.gemini_request_delay=0
    pipeline=StockAnalysisPipeline(config=config,max_workers=1,daily_market_context_enabled=False,daily_market_context_allow_generate=False)
    manager=pipeline.fetcher_manager;db=get_db();end=(dt.date.fromisoformat(target)+dt.timedelta(days=1)).isoformat()
    raw_fin={};factory=yf.Ticker
    class Recorder:
        def __init__(self,symbol):self.inner=factory(symbol)
        def get_info(self):
            value=self.inner.get_info();raw_fin['info']=value;return value
        def __getattr__(self,key):
            value=getattr(self.inner,key)
            if key in ('quarterly_income_stmt','quarterly_cashflow'):
                value.to_csv(out/(key+'.csv'));raw_fin[key+'_periods']=[str(x) for x in value.columns]
            return value
    yf.Ticker=Recorder
    if offline:
        frame=pd.read_csv(offline/(code+'-daily.csv'));frame['date']=pd.to_datetime(frame['date']).dt.date
        target=str(frame['date'].max());provider='SAVED_OFFLINE_FIXTURE_NOT_LATEST'
    else:frame,provider=manager.get_daily_data(code,days=180,end_date=end)
    assert len(frame)>=60 and str(frame['date'].max())[:10]==target,'latest_or_history_invalid'
    for _,r in frame.iterrows():
        assert all(math.isfinite(float(r[k])) for k in ('open','high','low','close','volume'))
        assert 0<float(r['low'])<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] and r['volume']>=0
    frame.to_csv(out/'DAILY.csv',index=False);db.save_daily_data(frame,code,provider)
    # The MVP is completed-session only, including when the Runner starts
    # during the next session. Any native refill must retain the same cutoff.
    daily=manager.get_daily_data
    def completed_daily(symbol,*a,**k):
        k['end_date']=end
        return daily(symbol,*a,**k)
    manager.get_daily_data=completed_daily
    if not offline:
        from history_identity_validation import match_source
        charts=[]
        for record in trace:
            if record.get('response_file'):charts.extend(json.loads((out/record['response_file']).read_text('utf-8')).get('chart',{}).get('result') or [])
        from data_provider import YfinanceFetcher
        alias=YfinanceFetcher()._convert_stock_code(code)
        meta=next(c['meta'] for c in reversed(charts) if c['meta'].get('symbol')==alias)
        assert meta['currency']=='USD' and meta['exchangeTimezoneName']=='America/New_York'
        assert re.search(NAMES[code],meta.get('longName') or meta.get('shortName') or '',re.I),'security_name_mismatch'
        assert meta['instrumentType']==('ETF' if code in ETFS else 'EQUITY')
        check=[{'date':str(r['date'])[:10],**{k:float(r[k]) for k in ('open','high','low','close','volume')}} for _,r in frame.iterrows()]
        matched=match_source(check,charts,alias);assert matched==len(frame)
        save(out/'PRICE_AUDIT.json',{'canonical_symbol':code,'provider_symbol':alias,'metadata':meta,'target':target,'matched_OHLCV_rows':matched,'fetched_at':now.isoformat(),'adjustment':'native yfinance auto_adjust=True','cache_restored':False,'identity_scope':'Yahoo metadata and source OHLCV; not independent legal issuer verification','ADR_ratio':None if code=='SKHY' else 'not_applicable_or_not_checked','identity_limit':'ADR conversion ratio unverified; USD quote never mixed with KRW financial figures' if code=='SKHY' else 'provider identity does not independently prove SpaceX issuer identity' if code=='SPCX' else None})
    # Use the native pipeline's same-database path; no model receives stale caches.
    if offline:pipeline.fetch_and_save_stock_data=lambda *a,**k:(True,None)
    manager._cache_stock_name(code,(meta.get('longName') or meta.get('shortName')) if not offline else code)
    if code in ETFS or offline:
        manager.get_fundamental_context=lambda *a,**k:manager.build_not_supported_fundamental_context(code,'ETF企业财务不适用' if code in ETFS else '离线夹具不请求财务；字段缺失')
    else:
        # Reuse the native Yahoo adapter and native block format; no realtime
        # valuation providers or paid search are needed for this narrow MVP.
        def fundamental(*a,**k):
            from data_provider.yfinance_fundamental_adapter import YfinanceFundamentalAdapter
            try:bundle=YfinanceFundamentalAdapter().get_fundamental_bundle(code)
            except BaseException as e:bundle={'earnings':{},'errors':[type(e).__name__]}
            save(out/'YAHOO_ADAPTER_BUNDLE.json',bundle)
            ctx=manager.build_not_supported_fundamental_context(code,'MVP仅启用Yahoo财务；其他模块未配置')
            ctx['earnings']=manager._build_fundamental_block('partial' if bundle.get('earnings') else 'failed',bundle.get('earnings',{}),bundle.get('source_chain',[]),bundle.get('errors',[]))
            return ctx
        manager.get_fundamental_context=fundamental
    contexts=[];fixtures=[];tech=[]
    original_trend=pipeline.trend_analyzer.analyze
    def trend(df,symbol,*a,**k):
        result=original_trend(df,symbol,*a,**k)
        assert len(df)>=60 and math.isclose(result.ma60,float(df.close.tail(60).mean()),rel_tol=1e-12)
        row={'rows_read':len(df),'same_database':str(db._engine.url.database),'MA60_verified':True,**result.to_dict()}
        tech.append(row);save(out/'TECHNICAL.json',row);return result
    pipeline.trend_analyzer.analyze=trend
    analyzer=pipeline.analyzer;assert analyzer._router and not config.litellm_fallback_models
    analyzer._router.num_retries=0
    native_analyze=analyzer.analyze
    def analyze(context,*a,**k):
        assert tech and context['date']==target
        contexts.append(context);save(out/'NATIVE_CONTEXT.json',context)
        f=fixture(code,context);fixtures.append(f);save(out/'SIMULATED_MODEL.json',f)
        return native_analyze(context,*a,**k)
    analyzer.analyze=analyze
    dispatch=analyzer._dispatch_litellm_completion
    def usage(model,kwargs,*a,**k):
        from authorized_once import with_usage_options
        kwargs['num_retries']=0
        return dispatch(model,with_usage_options(kwargs),*a,**k)
    analyzer._dispatch_litellm_completion=usage
    fake_calls=[]
    def fake(transport,request):
        fake_calls.append(1)
        if inject:raise GuardStop('OFFLINE_injected_model_failure')
        text=json.dumps(fixtures[-1],ensure_ascii=False)
        sse='data: '+json.dumps({'id':'offline-mvp','object':'chat.completion.chunk','created':int(time.time()),'model':'deepseek-flash','choices':[{'index':0,'delta':{'content':text},'finish_reason':'stop'}]},ensure_ascii=False)+'\n\ndata: [DONE]\n\n'
        return httpx.Response(200,content=sse.encode(),headers={'content-type':'text/event-stream'},request=request)
    httpx.HTTPTransport.handle_request=fake
    guard=OnePostGuard(preflight=False);guard.install()
    result=None
    try:result=pipeline.process_single_stock(code,skip_analysis=False,report_type=ReportType.SIMPLE,current_time=now)
    finally:
        guard.restore();save(out/'SIMULATED_TRANSPORT.json',{'fixture_only':True,'fake_calls':len(fake_calls),'guard_attempts':guard.attempts,'real_POSTs':0,'supplier_usage':None,'model_cost_USD':'0','wire':guard.captured})
        from data_provider.yfinance_fundamental_adapter import _pick_row,_latest_value,_INCOME_REVENUE_KEYS,_INCOME_NET_PROFIT_KEYS,_CASHFLOW_OP_KEYS
        bundle_path=out/'YAHOO_ADAPTER_BUNDLE.json'
        report=(json.loads(bundle_path.read_text('utf-8')).get('earnings',{}).get('financial_report') or {}) if bundle_path.exists() else {}
        fields={}
        for name,table,keys in [('revenue','quarterly_income_stmt',_INCOME_REVENUE_KEYS),('net_profit_parent','quarterly_income_stmt',_INCOME_NET_PROFIT_KEYS),('operating_cash_flow','quarterly_cashflow',_CASHFLOW_OP_KEYS)]:
            path=out/(table+'.csv');df=pd.read_csv(path,index_col=0) if path.exists() else pd.DataFrame()
            row=_pick_row(df,keys) if not df.empty else None
            direct=_latest_value(row);value=report.get(name)
            valid=row.dropna() if row is not None else None
            period=str(valid.index[0]) if valid is not None and not valid.empty else None
            mode='not_applicable_ETF' if code in ETFS else 'missing' if value is None else 'quarterly_Yahoo_not_officially_verified' if direct is not None else 'estimated_revenue_times_margin' if name=='net_profit_parent' else 'TTM_or_unknown_info_fallback'
            fields[name]={'value':value,'classification':mode,'direct_statement_value':direct,'actual_series_period':period,'adapter_report_date':report.get('report_date'),'currency':report.get('currency'),'source_url':f'https://finance.yahoo.com/quote/{code}/'+('cash-flow/' if table=='quarterly_cashflow' else 'financials/'),'publication_timestamp':None}
        save(out/'FINANCIAL_AUDIT.json',{'fetched_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Yahoo native adapter','official_GAAP_verified':False,'publication_time_verified':False,'enterprise_applicable':code not in ETFS,'fields':fields,'raw_fields':raw_fin,'notes':'季度列见CSV；info回退可能TTM，净利润回退可能推算；不能作为官方当期数字','context':contexts[-1].get('fundamental_context') if contexts else None})
    assert result and result.success,'native_pipeline_or_parser_failed'
    valid,missing=analyzer._check_content_integrity(result,require_phase_decision=True)
    assert valid,str(missing)
    assert len(fake_calls)==1 and guard.allowed==1
    wire=guard.captured[0]['body'];assert wire['max_tokens']==16384 and wire['thinking']=={'type':'disabled'} and wire['stream_options']=={'include_usage':True}
    save(out/'FINAL_REQUEST.json',wire)
    from authorized_once import canonical_sha
    save(out/'REQUEST_IDENTITY.json',{'sha256':canonical_sha(wire),'new_paid_authorization':False,'symbol':code,'session':target})
    result.search_performed=False;result.report_language='zh'
    result.data_sources=NOTICE+'；Yahoo真实日线；未执行新闻搜索；'+(result.data_sources or '')
    md='# '+code+' 流水线模拟报告\n\n> '+NOTICE+'\n\n'+NotificationService().generate_single_stock_report(result)
    (out/'REPORT.md').write_text(md,encoding='utf-8')
    import markdown2
    body=markdown2.markdown(md,safe_mode='escape',extras=['tables'])
    (out/'REPORT.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>html{overflow-x:hidden}body{font:16px/1.7 system-ui;width:100%;max-width:960px;box-sizing:border-box;margin:auto;padding:16px;overflow-wrap:anywhere}blockquote{margin:12px 0;padding:12px;background:#fff3cd}pre{white-space:pre-wrap;word-break:break-word;max-width:100%}table{display:block;max-width:100%;overflow-x:auto}td,th{padding:6px;border:1px solid #ccc;min-width:55px}</style><body>'+body+'</body></html>',encoding='utf-8')
    return {'symbol':code,'status':'success_simulated_model','session':target,'rows':len(frame),'technical_rows':tech[-1]['rows_read'],'real_POSTs':0,'news':'not_configured','financial_limitations':True,'seconds':round(time.monotonic()-start,2),'data_mode':'offline_saved' if offline else 'fresh_Yahoo_this_run'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path)
    p.add_argument('--child',choices=WATCHLIST);p.add_argument('--offline-data',type=pathlib.Path);p.add_argument('--inject-failure',choices=WATCHLIST)
    p.add_argument('--universe',choices=('three','watchlist35'),default='three');p.add_argument('--only',help='Free recovery subset; use a NEW output directory')
    a=p.parse_args();source=a.source.resolve();out=a.out.resolve();offline=a.offline_data.resolve() if a.offline_data else None
    if a.child:
        status=None
        try:status=run_symbol(source,out,a.child,offline,a.inject_failure==a.child)
        except BaseException as e:
            out.mkdir(parents=True,exist_ok=True);status={'symbol':a.child,'status':'failed','error':type(e).__name__+':'+str(e),'real_POSTs':0}
            import traceback;(out/'ERROR.txt').write_text(traceback.format_exc(),encoding='utf-8')
        save(out/'STATUS.json',status);return
    out.mkdir(parents=True,exist_ok=False);rows=[];rate_limited=False
    symbols=a.only.split(',') if a.only else WATCHLIST if a.universe=='watchlist35' else SYMBOLS
    assert len(symbols)==len(set(symbols)) and all(c in WATCHLIST for c in symbols)
    for code in symbols:
        if rate_limited:
            (out/code).mkdir();row={'symbol':code,'status':'failed','error':'Yahoo_429_batch_circuit_open_no_more_requests','real_POSTs':0};save(out/code/'STATUS.json',row);rows.append(row);continue
        env={k:v for k,v in os.environ.items() if not any(x in k for x in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')) and k not in ('GH_TOKEN','GITHUB_TOKEN','PYTHONPATH')}
        cmd=[sys.executable,'-I',str(pathlib.Path(__file__).resolve()),'--source',str(source),'--out',str(out/code),'--child',code]
        if offline:cmd+=['--offline-data',str(offline)]
        if a.inject_failure:cmd+=['--inject-failure',a.inject_failure]
        try:
            run=subprocess.run(cmd,env=env,capture_output=True,timeout=240);(out/(code+'-process.log')).write_bytes(run.stdout+run.stderr)
            row=json.loads((out/code/'STATUS.json').read_text('utf-8'))
        except Exception as e:
            (out/code).mkdir(exist_ok=True);row={'symbol':code,'status':'failed','error':type(e).__name__,'real_POSTs':0};save(out/code/'STATUS.json',row)
        rows.append(row)
        trace=out/code/'HTTP_TRACE.json'
        if trace.exists():rate_limited=any(r.get('status')==429 for r in json.loads(trace.read_text('utf-8')))
    save(out/'RESULTS.json',{'run_id':os.getenv('GITHUB_RUN_ID'),'commit':os.getenv('GITHUB_SHA'),'mode':'OFFLINE_saved' if offline else 'LIVE_FREE_DATA_MOCK_MODEL','symbols':rows,'real_POSTs':0,'new_model_cost_USD':'0','mail_sent':0})
    text=f'<h1>DSA {len(rows)}标的MVP</h1><p>'+NOTICE+'</p><ul>'
    for row in rows:
        code=row['symbol'];link=f'<a href="{code}/REPORT.html">{code}</a>' if row['status'].startswith('success') else code
        text+='<li>'+link+' '+html.escape(str(row.get('session',''))+' '+row['status']+' '+row.get('error',''))+'</li>'
    (out/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><body>'+text+'</ul></body></html>',encoding='utf-8')
    print(json.dumps(rows,ensure_ascii=False))


if __name__=='__main__':main()
