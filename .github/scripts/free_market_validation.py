"""One-run observability and deny guards around the unmodified upstream CLI.

No model client, research framework, fallback data, or persistent budget state.
"""
import argparse,contextlib,hashlib,json,math,os,pathlib,re,runpy,sqlite3,sys,time,threading
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit,parse_qs,unquote
ROOT=pathlib.Path(__file__).resolve().parents[2]
WATCHLIST='NVDA MSFT AAPL GOOGL AMZN META TSLA SPCX SKHY MU SNDK QQQ SOXX AMD AVGO TSM ASML ORCL PLTR CRWD JPM V BRK.B LLY UNH WMT COST XOM CAT SPY IWM DIA TLT GLD XLE'.split()
NAMES={'NVDA':'nvidia','MSFT':'microsoft','AAPL':'apple','GOOGL':'alphabet','AMZN':'amazon','META':'meta platforms','TSLA':'tesla','SPCX':'spacex|space exploration technologies','SKHY':'hynix','MU':'micron','SNDK':'sandisk','QQQ':'invesco.*qqq','SOXX':'semiconductor','AMD':'advanced micro|amd','AVGO':'broadcom','TSM':'taiwan semiconductor','ASML':'asml','ORCL':'oracle','PLTR':'palantir','CRWD':'crowdstrike','JPM':'jpmorgan|jp morgan','V':'visa','BRK.B':'berkshire','LLY':'lilly','UNH':'unitedhealth','WMT':'walmart','COST':'costco','XOM':'exxon','CAT':'caterpillar','SPY':'s&p 500|spdr','IWM':'russell','DIA':'dow jones','TLT':'treasury','GLD':'gold','XLE':'energy'}
ETFS={'QQQ','SOXX','SPY','IWM','DIA','TLT','GLD','XLE'}
class SafetyStop(BaseException):pass
class Limits:
 def __init__(self,out):self.out=out;self.lock=threading.Lock();self.http=[];self.denied=[];self.yahoo_rate_limited=False;self.calls={'llm':0,'notification':0,'market_review':0,'smtp':0,'paid_host':0}
 def forbid(self,kind):
  def denied(*a,**kw):
   with self.lock:self.calls[kind]+=1
   raise SafetyStop('forbidden_'+kind)
  return denied
 def check(self,url):
  u=urlsplit(str(url));host=(u.hostname or '').lower()
  allowed=host in ('query1.finance.yahoo.com','query2.finance.yahoo.com','finance.yahoo.com','fc.yahoo.com','guce.yahoo.com','consent.yahoo.com') or host.endswith(('.eastmoney.com','.gtimg.cn','.sina.com.cn','.sinajs.cn')) or host in ('raw.githubusercontent.com',)
  if not allowed:
   self.calls['paid_host']+=1;self.denied.append({'host':host,'path':u.path});raise SafetyStop('unapproved_outbound_host')
  if self.yahoo_rate_limited and host.endswith('yahoo.com'):raise SafetyStop('yahoo_429_stop_no_more_requests')
  safe={'host':host,'path':u.path,'at':datetime.now(timezone.utc).isoformat(),'method':None}
  # Never record crumbs, cookies, headers, keys, or arbitrary query parameters.
  q=parse_qs(u.query);safe['query']={k:v for k,v in q.items() if k in ('period1','period2','range','interval','symbols')}
  return safe
 def record(self,row,response):
  row['http_status']=response.status_code
  row['retry_after']=response.headers.get('Retry-After')
  with self.lock:
   row['request_index']=len(self.http)+1;self.http.append(row)
   if response.status_code==429 and row['host'].endswith('yahoo.com'):self.yahoo_rate_limited=True
   if '/finance/chart/' in row['path']:
    name='http-'+str(row['request_index'])+'.json'
    try:
     payload=response.json();(self.out/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');row['response_file']=name
    except Exception:row['response_not_json']=True
  return response
 def install(self):
  import requests,curl_cffi.requests as cr,httpx,smtplib
  for cls,method in ((requests.Session,'request'),(cr.Session,'request'),(httpx.Client,'request')):
   original=getattr(cls,method)
   def wrapper(instance,*args,_original=original,**kw):
    verb=args[0] if args else kw.get('method');url=args[1] if len(args)>1 else kw.get('url');row=self.check(url);row['method']=str(verb)
    try:return self.record(row,_original(instance,*args,**kw))
    except Exception as e:
     row['error_category']=type(e).__name__
     with self.lock:self.http.append(row)
     raise
   setattr(cls,method,wrapper)
  smtplib.SMTP=self.forbid('smtp');smtplib.SMTP_SSL=self.forbid('smtp')
  import litellm
  litellm.completion=self.forbid('llm');litellm.acompletion=self.forbid('llm')
  litellm.Router.completion=self.forbid('llm');litellm.Router.acompletion=self.forbid('llm')
  from src.analyzer import GeminiAnalyzer
  GeminiAnalyzer.analyze=self.forbid('llm');GeminiAnalyzer.generate_text=self.forbid('llm')
  from src.notification import NotificationService
  NotificationService.send=self.forbid('notification')
  from src.notification_sender.email_sender import EmailSender
  EmailSender.send_to_email=self.forbid('notification')
  EmailSender._send_email_with_inline_image=self.forbid('notification')
  import src.core.market_review as mr
  mr.run_market_review=self.forbid('market_review')

def verify_evidence(rows,meta,target):
 errors=[]
 if not rows:return ['no_new_daily_rows']
 if not any(str(x['date'])==target for x in rows):errors.append('latest_completed_session_missing')
 for x in rows:
  nums=[x.get(k) for k in ('open','high','low','close','volume')]
  if any(type(v) not in (int,float) or not math.isfinite(v) for v in nums):errors.append('invalid_ohlcv');break
  o,h,l,c,v=nums
  if min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:errors.append('ohlcv_order_or_sign');break
 if not meta:errors.append('provider_identity_metadata_missing')
 return sorted(set(errors))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--universe',choices=('nvda','watchlist35'),required=True);parser.add_argument('--out',required=True);a=parser.parse_args()
 out=pathlib.Path(a.out).resolve();out.mkdir(exist_ok=False);start=time.monotonic();now=datetime.now(timezone.utc)
 # No environment snapshot is serialized. Deny actual credential-bearing variables.
 credential_names=[k for k,v in os.environ.items() if v and (k.endswith(('_API_KEY','_API_KEYS','_PASSWORD','_ACCESS_TOKEN','_APP_SECRET')) or k in ('MODELFLARE_KEY','AIHUBMIX_KEY','TUSHARE_TOKEN','TAVILY_API_KEYS','BOCHA_API_KEYS','FEISHU_WEBHOOK_URL','TELEGRAM_BOT_TOKEN'))]
 if credential_names:raise SafetyStop('credential_configuration_present:'+','.join(sorted(credential_names)))
 if (ROOT/'.env').exists():raise SafetyStop('unexpected_env_file')
 db=out/'fresh-upstream.sqlite';assert not db.exists()
 os.environ.update(DATABASE_PATH=str(db),LOG_DIR=str(out/'logs'),REPORTS_DIR=str(out/'reports'),SCHEDULE_ENABLED='false',MARKET_REVIEW_ENABLED='false',DAILY_MARKET_CONTEXT_ENABLED='false',AGENT_MODE='false',AGENT_SKILLS='',SINGLE_STOCK_NOTIFY='false',AUTO_BACKTEST_ENABLED='false',SEARXNG_PUBLIC_INSTANCES_ENABLED='false',MAX_WORKERS='1',ENABLE_CHIP_DISTRIBUTION='false',REPORT_LANGUAGE='zh',LITELLM_LOCAL_MODEL_COST_MAP='True')
 sys.path.insert(0,str(ROOT))
 from src.core.trading_calendar import get_effective_trading_date,_XCALS_AVAILABLE
 if not _XCALS_AVAILABLE:raise SafetyStop('calendar_dependency_missing')
 target=get_effective_trading_date('us',current_time=now).isoformat();symbols=['NVDA'] if a.universe=='nvda' else WATCHLIST
 limits=Limits(out);limits.install();exit_code=None;failure=None
 sys.argv=[str(ROOT/'main.py'),'--dry-run','--no-notify','--no-market-review','--stocks',','.join(symbols)]
 try:
  runpy.run_path(str(ROOT/'main.py'),run_name='__main__');exit_code=0
 except SystemExit as e:exit_code=e.code
 except BaseException as e:failure=type(e).__name__+':'+str(e)
 metadata={};chart_results=[]
 for item in limits.http:
  if item.get('response_file'):
   data=json.loads((out/item['response_file']).read_text(encoding='utf-8'))
   for result in data.get('chart',{}).get('result') or []:
    chart_results.append(result)
    m=result.get('meta',{});symbol=m.get('symbol','');metadata[symbol]=m
 records=[];usage_rows=None
 if db.exists():
  with contextlib.closing(sqlite3.connect(db)) as conn:
   conn.row_factory=sqlite3.Row
   if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_daily'").fetchone():records=[dict(x) for x in conn.execute('SELECT * FROM stock_daily ORDER BY code,date')]
   if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_usage'").fetchone():usage_rows=conn.execute('SELECT COUNT(*) FROM llm_usage').fetchone()[0]
 statuses=[]
 for code in symbols:
  r=[x for x in records if x['code']==code];aliases={code,'BRK-B'} if code=='BRK.B' else {code};m=next((metadata[x] for x in aliases if x in metadata),{})
  errors=verify_evidence(r,m,target);name=m.get('longName') or m.get('shortName')
  if not name or not re.search(NAMES[code],name,re.I):errors.append('security_name_not_confirmed')
  if m.get('symbol') not in aliases:errors.append('returned_symbol_mismatch_or_missing')
  if m.get('exchangeTimezoneName')!='America/New_York' or m.get('currency')!='USD':errors.append('US_market_or_currency_unconfirmed')
  expected_type='ETF' if code in ETFS else 'EQUITY'
  if m.get('instrumentType')!=expected_type:errors.append('security_type_unconfirmed_or_mismatch')
  last=next((x for x in r if str(x['date'])==target),None)
  source_match=False
  if last:
   for chart in chart_results:
    if chart.get('meta',{}).get('symbol') not in aliases:continue
    quote=(chart.get('indicators',{}).get('quote') or [{}])[0];adjusted=(chart.get('indicators',{}).get('adjclose') or [{}])[0].get('adjclose',[])
    for index,stamp in enumerate(chart.get('timestamp',[])):
     if datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date().isoformat()!=target:continue
     try:
      close=quote['close'][index];factor=adjusted[index]/close if len(adjusted)>index and adjusted[index] is not None else 1
      source_match=all(math.isclose(last[k],quote[k][index]*(1 if k=='volume' else factor),rel_tol=1e-6,abs_tol=1e-5) for k in ('open','high','low','close','volume'))
     except (KeyError,IndexError,TypeError,ZeroDivisionError):pass
  if not source_match:errors.append('target_ohlcv_not_verified_against_this_run_chart')
  statuses.append({'symbol':code,'valid':not errors,'errors':sorted(set(errors)),'provider_name':name,'metadata':m,'rows':len(r),'latest_db_date':max((str(x['date']) for x in r),default=None),'target_completed_session':target,'target_ohlcv':last,'providers':sorted({x.get('data_source') for x in r if x.get('data_source')}),'fetched_this_run':True,'cache_restored':False,'source_ohlcv_match':source_match,'adjustment':'upstream yfinance auto_adjust=True; raw OHLC scaled by observed adjclose/close only for evidence verification'})
 safety=all(v==0 for v in limits.calls.values()) and usage_rows in (None,0);valid=sum(x['valid'] for x in statuses)
 summary={'started_at':now.isoformat(),'ended_at':datetime.now(timezone.utc).isoformat(),'seconds':round(time.monotonic()-start,3),'target_session':target,'universe':a.universe,'symbols':symbols,'valid':valid,'total':len(symbols),'safety_passed':safety,'attempt_counters':limits.calls,'http_requests':len(limits.http),'http_status_counts':{str(k):sum(x.get('http_status')==k for x in limits.http) for k in sorted({x['http_status'] for x in limits.http if 'http_status' in x})},'rate_limited':limits.yahoo_rate_limited,'cli_exit_code':exit_code,'failure':failure,'credential_variables_present':False,'fresh_database':True,'run_id':os.getenv('GITHUB_RUN_ID'),'run_attempt':os.getenv('GITHUB_RUN_ATTEMPT'),'commit':os.getenv('GITHUB_SHA'),'runner_os':os.getenv('RUNNER_OS'),'paid_model_calls':0,'emails_sent':0,'passed':safety and valid==len(symbols) and exit_code==0 and failure is None}
 summary['llm_usage_rows']=usage_rows
 for name,value in [('summary.json',summary),('statuses.json',statuses),('http-trace.json',limits.http),('denied-outbound.json',limits.denied),('daily-rows.json',records)]:
  (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False));return 0 if summary['passed'] else 1
if __name__=='__main__':sys.exit(main())
