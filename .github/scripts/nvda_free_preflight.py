"""Fixed upstream native request construction; fake credential; POST never sent."""
import argparse,contextlib,hashlib,importlib.metadata,json,math,os,pathlib,sqlite3,subprocess,sys,time
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit
parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
G=pathlib.Path(args.source).resolve();C=pathlib.Path(args.out).resolve();C.mkdir(exist_ok=False)
if os.getenv('GITHUB_RUN_ATTEMPT','1')!='1':raise SystemExit('manual rerun forbidden')
FIXED='2b896241f69d0177c2b6f298cf69042b8531dd76'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=G,encoding='utf-8').strip()==FIXED
sys.path[:0]=[str(G),str(G/'.github/scripts')]
# Never pass the actual key to the model SDK, or serialize inherited environment.
for name in list(os.environ):
    if name.endswith(('_API_KEY','_API_KEYS','_PASSWORD','_ACCESS_TOKEN','_APP_SECRET','_WEBHOOK_URL')) or name in ('TUSHARE_TOKEN','MODELFLARE_KEY','AIHUBMIX_KEY','TELEGRAM_BOT_TOKEN','GH_TOKEN','GITHUB_TOKEN','LITELLM_CONFIG','LLM_CHANNELS','DEEPSEEK_API_BASE','DEEPSEEK_BASE_URL','OPENAI_BASE_URL','OPENAI_API_BASE') or name.startswith('LLM_'):
        os.environ.pop(name,None)
os.environ.update(DEEPSEEK_API_KEY='preflight-placeholder-never-transmitted',LITELLM_MODEL='deepseek/deepseek-flash',LITELLM_FALLBACK_MODELS='',GENERATION_BACKEND='litellm',GENERATION_FALLBACK_BACKEND='litellm',DATABASE_PATH=str(C/'fresh-upstream.sqlite'),LOG_DIR=str(C/'logs'),REPORTS_DIR=str(C/'reports'),SCHEDULE_ENABLED='false',MARKET_REVIEW_ENABLED='false',DAILY_MARKET_CONTEXT_ENABLED='false',AGENT_MODE='false',AGENT_SKILLS='',SINGLE_STOCK_NOTIFY='false',AUTO_BACKTEST_ENABLED='false',SEARXNG_PUBLIC_INSTANCES_ENABLED='false',MAX_WORKERS='1',ENABLE_CHIP_DISTRIBUTION='false',ENABLE_REALTIME_QUOTE='false',ENABLE_FUNDAMENTAL_PIPELINE='false',REPORT_INTEGRITY_RETRY='0',LITELLM_LOCAL_MODEL_COST_MAP='True',REPORT_LANGUAGE='zh')
os.environ['DEEPSEEK_API_BASE']='https://api.deepseek.com'
assert not (G/'.env').exists()
from free_market_validation import Limits,SafetyStop
limits=Limits(C);logical=[];wire=[];trend=[];reads=[];context=[]

import requests,curl_cffi.requests as curl,httpx,smtplib
for cls in (requests.Session,curl.Session):
    original=cls.request
    def observed(self,*a,_original=original,**kw):
        method=a[0] if a else kw.get('method');url=a[1] if len(a)>1 else kw.get('url')
        parsed=urlsplit(str(url))
        if parsed.scheme=='https' and parsed.hostname=='openaipublic.blob.core.windows.net' and parsed.path in ('/encodings/cl100k_base.tiktoken','/encodings/o200k_base.tiktoken') and str(method).upper()=='GET':
            assert not any(k.lower()=='authorization' for k in kw.get('headers',{}))
            row={'method':'GET','host':parsed.hostname,'path':parsed.path,'at':datetime.now(timezone.utc).isoformat(),'free_tokenizer_asset':True}
        else:row=limits.check(url);row['method']=method
        try:return limits.record(row,_original(self,*a,**kw))
        except Exception as e:
            row['error_category']=type(e).__name__;limits.http.append(row);raise
    cls.request=observed
from deepseek_post_guard import OnePostGuard,PreflightIntercept
guard=OnePostGuard(preflight=True);guard.install();wire=guard.captured
smtplib.SMTP=limits.forbid('smtp');smtplib.SMTP_SSL=limits.forbid('smtp')
import litellm
from src.notification import NotificationService
from src.notification_sender.email_sender import EmailSender
NotificationService.send=limits.forbid('notification');EmailSender.send_to_email=limits.forbid('notification')
from src.core.trading_calendar import get_effective_trading_date
from src.config import get_config
from src.storage import get_db,DatabaseManager
from data_provider import DataFetcherManager
from src.core.pipeline import StockAnalysisPipeline
from src.stock_analyzer import StockTrendAnalyzer
from src.analyzer import GeminiAnalyzer
from src.enums import ReportType
now=datetime.now(timezone.utc);target=get_effective_trading_date('us',current_time=now).isoformat();end=(datetime.fromisoformat(target)+timedelta(days=1)).date().isoformat()
config=get_config();db=get_db();manager=DataFetcherManager();fresh_error=None;origin='current_live_original_API'
try:
    frame,provider=manager.get_daily_data('NVDA',days=90,end_date=end)
    if frame.empty or str(frame['date'].max())[:10]!=target or len(frame)<60:raise ValueError('latest_or_minimum_history_not_met')
except BaseException as e:
    (C/'FAILED_PRICE_PREFLIGHT.json').write_text(json.dumps({'category':type(e).__name__,'no_cached_fallback':True,'paid_posts':0,'target_session':target},indent=2),encoding='utf-8')
    (C/'HTTP_TRACE.json').write_text(json.dumps(limits.http,indent=2),encoding='utf-8')
    raise
db.save_daily_data(frame,'NVDA',provider)
from history_identity_validation import validate_rows,match_source
import exchange_calendars as xc
check_rows=[{'date':str(row['date'])[:10],**{k:float(row[k]) for k in ('open','high','low','close','volume')}} for _,row in frame.iterrows()]
check_rows.sort(key=lambda x:x['date'])
start=(datetime.fromisoformat(end)-timedelta(days=180)).date().isoformat()
expected=[d.date().isoformat() for d in xc.get_calendar('XNYS').sessions_in_range(start,target)]
charts=[]
for item in limits.http:
    if item.get('response_file'):charts.extend(json.loads((C/item['response_file']).read_text(encoding='utf-8')).get('chart',{}).get('result') or [])
assert not validate_rows(check_rows,target,expected)
assert match_source(check_rows,charts,'NVDA')==len(check_rows)
meta=next(c['meta'] for c in reversed(charts) if c['meta'].get('symbol')=='NVDA')
assert meta['currency']=='USD' and meta['exchangeTimezoneName']=='America/New_York' and 'nvidia' in meta.get('longName','').lower()
original_read=DatabaseManager.get_data_range
def observe_read(self,code,*a,**kw):
    bars=original_read(self,code,*a,**kw);reads.append({'code':code,'start':str(a[0]),'end':str(a[1]),'rows':len(bars),'database_path':str(self._engine.url.database)})
    return bars
DatabaseManager.get_data_range=observe_read
original_trend=StockTrendAnalyzer.analyze
def observe_trend(self,df,code,*a,**kw):
    result=original_trend(self,df,code,*a,**kw)
    expected=sum(float(v) for v in df['close'].iloc[-60:])/60
    trend.append({'code':code,'rows':len(df),'close':result.current_price,'ma60':result.ma60,'ma20':result.ma20,'ma60_verified':len(df)>=60 and math.isclose(result.ma60,expected,rel_tol=1e-12)})
    return result
StockTrendAnalyzer.analyze=observe_trend
original_analyze=GeminiAnalyzer.analyze
def observe_analyze(self,enhanced,*a,**kw):
    context.append(enhanced);return original_analyze(self,enhanced,*a,**kw)
GeminiAnalyzer.analyze=observe_analyze
original_dispatch=GeminiAnalyzer._dispatch_litellm_completion
def observe_dispatch(self,model,call_kwargs,*a,**kw):
    safe={k:v for k,v in call_kwargs.items() if k not in ('api_key','headers','extra_headers','client')}
    logical.append(safe);return original_dispatch(self,model,call_kwargs,*a,**kw)
GeminiAnalyzer._dispatch_litellm_completion=observe_dispatch
pipeline=StockAnalysisPipeline(config=config,max_workers=1,daily_market_context_enabled=False,daily_market_context_allow_generate=False)
outcome='not_captured';error=None
try:pipeline.process_single_stock('NVDA',skip_analysis=False,report_type=ReportType.SIMPLE,current_time=now)
except PreflightIntercept:outcome='native_SDK_POST_captured_not_transmitted'
except BaseException as e:error={'category':type(e).__name__,'error_redacted':True}
versions={}
for name in ('litellm','openai','httpx','yfinance','pandas','tiktoken'):
    try:versions[name]=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:pass
packet=wire[0]['body'] if wire else (logical[0] if logical else {})
canonical=json.dumps(packet,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
messages=packet.get('messages',[]);content=json.dumps(messages,ensure_ascii=False,separators=(',',':'));byte_size=len(content.encode());chars=len(content)
estimated=None;token_error=None
try:
    import tiktoken
    estimated=sum(len(tiktoken.get_encoding('cl100k_base').encode(str(m.get('content','')))) for m in messages)+4*len(messages)+3
except Exception as e:token_error=type(e).__name__
with contextlib.closing(sqlite3.connect(C/'fresh-upstream.sqlite')) as con:usage=con.execute('SELECT COUNT(*) FROM llm_usage').fetchone()[0]
report={'fixed_commit':FIXED,'captured_at':datetime.now(timezone.utc).isoformat(),'outcome':outcome,'error':error,'actual_model':config.litellm_model,'router_present':pipeline.analyzer._router is not None,'fallback_models':config.litellm_fallback_models,'report_integrity_retry':config.report_integrity_retry,'source':origin,'live_source_error':fresh_error,'target_session':target,'database_path':str(db._engine.url.database),'prefill_rows':len(frame),'database_reads':reads,'technical_checks':trend,'logical_dispatch_attempts_intercepted':len(logical),'SDK_wire_POSTs_intercepted':len(wire),'paid_POSTs_transmitted':0,'notifications_transmitted':0,'llm_usage_rows':usage,'versions':versions,'request_sha256':hashlib.sha256(canonical).hexdigest(),'messages_utf8_bytes':byte_size,'messages_characters':chars,'cl100k_input_estimate_not_supplier_usage':estimated,'token_estimate_error':token_error,'conservative_byte_based_input_allowance_not_formal_guarantee':byte_size+1024,'output_limit':packet.get('max_tokens'),'wire_endpoint':wire[0]['url'] if wire else None,'credentials_used_for_native_capture':'placeholder_only; real key used in separate official free GETs','live_HTTP_requests':len(limits.http),'guard_attempts':guard.attempts,'guard_blocked':guard.blocked,'guard_allowed_network_posts':guard.allowed,'fundamentals_empty':True,'news_empty':True,'run_id':os.getenv('GITHUB_RUN_ID')}
for name,value in [('CAPTURE_SUMMARY.json',report),('ORIGINAL_LOGICAL_REQUESTS.json',logical),('ORIGINAL_SDK_WIRE_REQUESTS.json',wire),('ORIGINAL_REQUEST_PACKET.json',packet),('ORIGINAL_ENHANCED_CONTEXT.json',context),('HTTP_TRACE.json',limits.http),('NVDA_PREFILL_ROWS.json',frame.to_dict(orient='records'))]:
    (C/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
assert outcome=='native_SDK_POST_captured_not_transmitted' and len(wire)==1 and guard.allowed==0
