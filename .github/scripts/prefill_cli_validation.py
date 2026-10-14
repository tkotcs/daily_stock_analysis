"""One-run original API prefill, original CLI, and paid-stage-free trend probe.

Observers delegate to original methods. No replacement prices or indicators.
"""
import argparse, contextlib, json, math, os, pathlib, re, runpy, sqlite3, sys, time
from datetime import datetime, timedelta, timezone
from free_market_validation import ROOT, WATCHLIST, NAMES, ETFS, Limits, SafetyStop
from history_identity_validation import LISTING_DATES, validate_rows, match_source


class TrendProbeComplete(BaseException):
    """Intentional stop after original technical calculation, before research."""


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args()
    out=pathlib.Path(args.out).resolve();out.mkdir(exist_ok=False)
    now=datetime.now(timezone.utc);clock=time.monotonic();db_path=out/'fresh-upstream.sqlite'
    credentials=[k for k,v in os.environ.items() if v and (k.endswith(('_API_KEY','_API_KEYS','_PASSWORD','_ACCESS_TOKEN','_APP_SECRET')) or k in ('TUSHARE_TOKEN','MODELFLARE_KEY','AIHUBMIX_KEY','TELEGRAM_BOT_TOKEN'))]
    if credentials or (ROOT/'.env').exists():raise SafetyStop('credential_or_env_file_present')
    os.environ.update(DATABASE_PATH=str(db_path),LOG_DIR=str(out/'logs'),REPORTS_DIR=str(out/'reports'),SCHEDULE_ENABLED='false',MARKET_REVIEW_ENABLED='false',DAILY_MARKET_CONTEXT_ENABLED='false',AGENT_MODE='false',AGENT_SKILLS='',SINGLE_STOCK_NOTIFY='false',AUTO_BACKTEST_ENABLED='false',SEARXNG_PUBLIC_INSTANCES_ENABLED='false',MAX_WORKERS='1',ENABLE_CHIP_DISTRIBUTION='false',ENABLE_REALTIME_QUOTE='false',ENABLE_FUNDAMENTAL_PIPELINE='false',LITELLM_LOCAL_MODEL_COST_MAP='True')
    sys.path.insert(0,str(ROOT))
    from src.core.trading_calendar import get_effective_trading_date,_XCALS_AVAILABLE
    if not _XCALS_AVAILABLE:raise SafetyStop('calendar_dependency_missing')
    import exchange_calendars as xc
    from data_provider import DataFetcherManager,YfinanceFetcher
    from src.storage import get_db,DatabaseManager
    from src.core.pipeline import StockAnalysisPipeline
    from src.stock_analyzer import StockTrendAnalyzer
    from src.enums import ReportType
    limits=Limits(out);limits.install()
    db=get_db();manager=DataFetcherManager();fetcher=YfinanceFetcher()
    assert pathlib.Path(db._engine.url.database).resolve()==db_path
    target=get_effective_trading_date('us',current_time=now).isoformat()
    end=(datetime.fromisoformat(target)+timedelta(days=1)).date().isoformat()
    start=(datetime.fromisoformat(end)-timedelta(days=180)).date().isoformat()
    calendar=xc.get_calendar('XNYS');statuses=[];charts=[];stopped=False
    for code in WATCHLIST:
        before=len(limits.http);begin=time.monotonic();rows=[];errors=[];failure=None;source=None;saved=0
        alias=fetcher._convert_stock_code(code)
        try:
            if stopped:raise SafetyStop('earlier_safety_stop')
            frame,source=manager.get_daily_data(code,end_date=end,days=90)
            rows=[{'date':str(row['date'])[:10],**{k:float(row[k]) for k in ('open','high','low','close','volume')}} for _,row in frame.iterrows()]
            rows.sort(key=lambda row:row['date'])
        except BaseException as e:
            failure=type(e).__name__+':'+str(e);errors.append('fetch_failure')
            stopped=isinstance(e,SafetyStop) or stopped
        for item in limits.http[before:]:
            if item.get('response_file'):charts.extend(json.loads((out/item['response_file']).read_text()).get('chart',{}).get('result') or [])
        meta=next((c['meta'] for c in reversed(charts) if c.get('meta',{}).get('symbol')==alias),{})
        lower=max(start,LISTING_DATES.get(code,start));expected=[d.date().isoformat() for d in calendar.sessions_in_range(lower,target)]
        errors+=validate_rows(rows,target,expected)
        if any(row['date']<lower or row['date']>target for row in rows):errors.append('outside_completed_listing_window')
        name=meta.get('longName') or meta.get('shortName')
        if not name or not re.search(NAMES[code],name,re.I):errors.append('name_mismatch')
        if meta.get('symbol')!=alias or meta.get('currency')!='USD' or meta.get('exchangeTimezoneName')!='America/New_York':errors.append('identity_mismatch')
        if meta.get('exchangeName') not in ('NMS','NGM','NCM','NYQ','PCX','ASE','BTS'):errors.append('market_unconfirmed')
        if meta.get('instrumentType')!=('ETF' if code in ETFS else 'EQUITY'):errors.append('instrument_type_mismatch')
        matched=match_source(rows,charts,alias)
        if matched!=len(rows) or not rows:errors.append('source_ohlcv_mismatch')
        if not errors:
            saved=db.save_daily_data(frame,code,source)
        statuses.append({'symbol':code,'yahoo_symbol':alias,'provider':source,'metadata':meta,'valid':not errors,'errors':sorted(set(errors)),'failure':failure,'rows':len(rows),'saved_rows':saved,'source_matched_rows':matched,'first_date':min((r['date'] for r in rows),default=None),'last_date':max((r['date'] for r in rows),default=None),'http_requests':len(limits.http)-before,'seconds':round(time.monotonic()-begin,3),'diagnostic_only':False,'cache_restored':False})
        print(json.dumps({k:statuses[-1][k] for k in ('symbol','yahoo_symbol','valid','rows','errors')}),flush=True)
        time.sleep(0.25)
    def snapshot():
        with contextlib.closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory=sqlite3.Row
            return [dict(r) for r in conn.execute('SELECT * FROM stock_daily ORDER BY code,date')]
    before_cli=snapshot();pipelines=[];cli_fetches=[];trend_checks=[];reads=[];mas=[];cli_exit=None;cli_failure=None
    original_init=StockAnalysisPipeline.__init__
    def observe_init(self,*a,**kw):
        original_init(self,*a,**kw);pipelines.append(self)
    StockAnalysisPipeline.__init__=observe_init
    original_fetch=StockAnalysisPipeline.fetch_and_save_stock_data
    phase={'name':'cli'}
    def observe_fetch(self,code,*a,**kw):
        actual_path=str(pathlib.Path(self.db._engine.url.database).resolve())
        outcome=original_fetch(self,code,*a,**kw)
        cli_fetches.append({'phase':phase['name'],'code':code,'database_path':actual_path,'same_prefill_database':actual_path==str(db_path),'success':outcome[0],'error':outcome[1]})
        return outcome
    StockAnalysisPipeline.fetch_and_save_stock_data=observe_fetch
    original_read=DatabaseManager.get_data_range
    def observe_read(self,code,*a,**kw):
        bars=original_read(self,code,*a,**kw)
        if phase['name']=='trend_probe':reads.append({'code':code,'start':str(a[0]),'end':str(a[1]),'rows':len(bars),'database_path':str(pathlib.Path(self._engine.url.database).resolve()),'dates':[str(b.date) for b in bars]})
        return bars
    DatabaseManager.get_data_range=observe_read
    original_mas=StockTrendAnalyzer._calculate_mas
    def observe_mas(self,frame):
        actual=original_mas(self,frame)
        expected=sum(float(c) for c in frame['close'].iloc[-60:])/60
        mas.append({'rows':len(frame),'expected_ma60':expected,'actual_ma60':float(actual['MA60'].iloc[-1]),'actual_ma20':float(actual['MA20'].iloc[-1]),'first_ma60_valid_index':int(actual['MA60'].first_valid_index()),'uses_real_60_window':len(frame)>=60 and actual['MA60'].iloc[:59].isna().all() and math.isclose(float(actual['MA60'].iloc[-1]),expected,rel_tol=1e-12,abs_tol=1e-10)})
        return actual
    StockTrendAnalyzer._calculate_mas=observe_mas
    original_trend=StockTrendAnalyzer.analyze
    def observe_trend(self,frame,code,*a,**kw):
        result=original_trend(self,frame,code,*a,**kw)
        trend_checks.append({'code':code,'rows':len(frame),'current_price':result.current_price,'ma60':result.ma60,'ma20':result.ma20,'ma5':result.ma5,'ma10':result.ma10,'trend':result.trend_status.value,'calculation':mas[-1],'database_read':reads[-1]})
        raise TrendProbeComplete()
    StockTrendAnalyzer.analyze=observe_trend
    if all(status['valid'] for status in statuses):
        sys.argv=[str(ROOT/'main.py'),'--dry-run','--no-notify','--no-market-review','--stocks',','.join(WATCHLIST)]
        try:runpy.run_path(str(ROOT/'main.py'),run_name='__main__');cli_exit=0
        except SystemExit as e:cli_exit=e.code
        except BaseException as e:cli_failure=type(e).__name__+':'+str(e)
        if cli_exit==0 and cli_failure is None and pipelines:
            phase['name']='trend_probe'
            # Original production entry freezes the real effective target date and reads DB.
            for code in WATCHLIST:
                try:pipelines[-1].process_single_stock(code,report_type=ReportType.SIMPLE,skip_analysis=False,current_time=now)
                except TrendProbeComplete:pass
                except BaseException as e:
                    trend_checks.append({'code':code,'failure':type(e).__name__+':'+str(e)})
                    if isinstance(e,SafetyStop):break
    after_cli=snapshot()
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        usage=conn.execute('SELECT COUNT(*) FROM llm_usage').fetchone()[0]
    main_calls=[r for r in cli_fetches if r['phase']=='cli'];technical_calls=[r for r in cli_fetches if r['phase']=='trend_probe']
    technical_pass=len(trend_checks)==35 and all(t.get('calculation',{}).get('uses_real_60_window') and t['database_read']['rows']==t['rows']>=60 and t['database_read']['database_path']==str(db_path) for t in trend_checks)
    cli_pass=cli_exit==0 and cli_failure is None and len(main_calls)==35 and all(r['success'] and r['same_prefill_database'] for r in main_calls)
    safety=all(v==0 for v in limits.calls.values()) and usage==0
    summary={'run_id':os.getenv('GITHUB_RUN_ID'),'commit':os.getenv('GITHUB_SHA'),'started_at':now.isoformat(),'ended_at':datetime.now(timezone.utc).isoformat(),'seconds':round(time.monotonic()-clock,3),'target_session':target,'history_start':start,'history_end_exclusive':end,'days_parameter':90,'database_path':str(db_path),'prefill_valid':sum(s['valid'] for s in statuses),'total':35,'prefill_rows':len(before_cli),'post_cli_rows':len(after_cli),'stock_daily_unchanged_after_cli_and_probe':before_cli==after_cli,'cli_exit_code':cli_exit,'cli_failure':cli_failure,'native_cli_passed':cli_pass,'native_cli_symbols':len(main_calls),'technical_probe_passed':technical_pass,'technical_probe_symbols':len(trend_checks),'technical_probe_stop':'after original StockTrendAnalyzer.analyze, before news/AI; not a full paid analysis','same_database':all(r['same_prefill_database'] for r in cli_fetches),'attempt_counters':limits.calls,'llm_usage_rows':usage,'safety_passed':safety,'http_requests':len(limits.http),'http_status_counts':{str(k):sum(r.get('http_status')==k for r in limits.http) for k in sorted({r['http_status'] for r in limits.http if 'http_status' in r})},'rate_limited':limits.yahoo_rate_limited,'paid_requests':0,'emails_sent':0,'passed':cli_pass and technical_pass and safety and before_cli==after_cli}
    for name,value in [('summary.json',summary),('prefill-statuses.json',statuses),('daily-rows.json',after_cli),('cli-fetches.json',cli_fetches),('ma60-checks.json',trend_checks),('http-trace.json',limits.http),('denied-outbound.json',limits.denied)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False));return 0 if summary['passed'] else 1


if __name__=='__main__':sys.exit(main())
