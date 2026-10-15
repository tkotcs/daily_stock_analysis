"""One read-only Yahoo adapter probe plus an official public RSS check; no LLM."""
import argparse,json,os,pathlib,sys,time,urllib.parse,urllib.request,datetime,math

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    out=pathlib.Path(a.out).resolve();out.mkdir(exist_ok=False)
    for k in list(os.environ):
        if any(s in k for s in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')):os.environ.pop(k,None)
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
    import pandas as pd,yfinance as yf,curl_cffi.requests as curl
    from data_provider.yfinance_fundamental_adapter import YfinanceFundamentalAdapter,_pick_row,_latest_value,_INCOME_REVENUE_KEYS,_INCOME_NET_PROFIT_KEYS,_CASHFLOW_OP_KEYS
    start=time.monotonic();trace=[];raw={};restricted=[]
    original_request=curl.Session.request
    def request(session,method,url,*args,**kw):
        host=urllib.parse.urlparse(url).hostname or ''
        if method.upper()!='GET' or not (host=='yahoo.com' or host.endswith('.yahoo.com')):raise RuntimeError('non_yahoo_GET_forbidden')
        if restricted:raise RuntimeError('Yahoo_access_restriction_circuit_open')
        kw['timeout']=min(float(kw.get('timeout') or 15),15)
        kw['allow_redirects']=False
        at=time.monotonic();rec={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'GET','host':host,'path':urllib.parse.urlparse(url).path}
        try:
            r=original_request(session,method,url,*args,**kw);rec['status']=r.status_code
            if r.status_code in (403,429):
                rec['stop_reason']='access_restriction_no_bypass';restricted.append(r.status_code)
            return r
        except Exception as exc:rec['error']=type(exc).__name__;raise
        finally:rec['seconds']=round(time.monotonic()-at,3);trace.append(rec)
    curl.Session.request=request
    factory=yf.Ticker
    class Recorder:
        def __init__(self,code):self.inner=factory(code)
        def get_info(self):
            value=self.inner.get_info();raw['info']=value;return value
        def __getattr__(self,name):
            value=getattr(self.inner,name)
            if name in ('quarterly_income_stmt','quarterly_cashflow','dividends'):
                raw[name]=value
                if hasattr(value,'to_csv'):value.to_csv(out/(name+'.csv'))
            return value
    yf.Ticker=Recorder
    try:bundle=YfinanceFundamentalAdapter().get_fundamental_bundle('NVDA')
    except Exception as exc:bundle={'status':'failed','errors':[type(exc).__name__]}
    finally:yf.Ticker=factory;curl.Session.request=original_request
    def save(name,data):
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str,allow_nan=False),encoding='utf-8')
    info=raw.get('info') or {};save('YAHOO_INFO.json',info);save('ADAPTER_BUNDLE.json',bundle)
    report=(bundle.get('earnings') or {}).get('financial_report') or {}
    fields={}
    for name,table,keys,fallback in [('revenue','quarterly_income_stmt',_INCOME_REVENUE_KEYS,'totalRevenue'),('net_profit_parent','quarterly_income_stmt',_INCOME_NET_PROFIT_KEYS,None),('operating_cash_flow','quarterly_cashflow',_CASHFLOW_OP_KEYS,'operatingCashflow')]:
        df=raw.get(table);row=_pick_row(df,keys) if df is not None and not df.empty else None
        direct=_latest_value(row);key=next((k for k in keys if df is not None and k in df.index),None)
        valid=row.dropna() if row is not None else None
        date=str(valid.index[0]) if valid is not None and not valid.empty else None
        source=f'yfinance.{table}[{key}]' if direct is not None else f'yfinance.info.{fallback}' if fallback else 'derived: revenue * info.profitMargins'
        value=report.get(name)
        fields[name]={'value':value,'adapter_report_date':report.get('report_date'),'actual_series_period_end':date if direct is not None else None,'period_type':'quarterly' if direct is not None else 'TTM_or_unknown_fallback','source':source,'source_url':'https://finance.yahoo.com/quote/NVDA/financials/' if table=='quarterly_income_stmt' else 'https://finance.yahoo.com/quote/NVDA/cash-flow/','direct_statement_value':direct,'estimated':name=='net_profit_parent' and direct is None and value is not None,'missing':value is None,'publication_timestamp':None,'historical_availability_proven':False,'currency':report.get('currency')}
        if direct is not None and value is not None:fields[name]['matches_original_adapter']=math.isclose(float(direct),float(value),rel_tol=1e-10)
    fields['currency']={'financial_currency':info.get('financialCurrency'),'quote_currency':info.get('currency'),'adapter_financial_currency':report.get('currency'),'source':'yfinance.info','identity':{'symbol':info.get('symbol'),'name':info.get('longName'),'exchange':info.get('exchange')}}
    save('FIELD_PROVENANCE.json',fields);save('YAHOO_HTTP_TRACE.json',trace)
    # Read a publisher-provided RSS feed. No feed is injected into DSA's search config.
    import xml.etree.ElementTree as ET,email.utils
    url='https://nvidianews.nvidia.com/releases.xml';news={'url':url,'source':'NVIDIA official newsroom','automatic_dsa_integration':False,'redistribution_license_verified':False}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'DSA-Personal-Research-Free-Validation/1.0'})
        with urllib.request.urlopen(req,timeout=20) as r:
            data=r.read(3000000);news['http_status']=r.status;news['final_url']=r.url
        (out/'NVIDIA_RSS.xml').write_bytes(data)
        rss=ET.fromstring(data);items=[]
        for item in rss.findall('.//item')[:10]:
            pub=item.findtext('pubDate');timestamp=email.utils.parsedate_to_datetime(pub).isoformat() if pub else None
            items.append({'title':item.findtext('title'),'url':item.findtext('link'),'published_at':timestamp,'publisher_time_raw':pub})
        news['items']=items;news['valid_items']=sum(bool(x['url'] and x['published_at']) for x in items)
    except Exception as exc:news['error']=type(exc).__name__;news['http_status']=getattr(exc,'code',None)
    save('NEWS_PROBE.json',news)
    from src.search_service import SearchService
    service=SearchService(searxng_public_instances_enabled=False)
    save('SUMMARY.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'seconds':round(time.monotonic()-start,3),'adapter_status':bundle.get('status'),'financial_fields_present':sum(fields[n]['value'] is not None for n in ('revenue','net_profit_parent','operating_cash_flow')),'yahoo_requests':len(trace),'news_valid_items':news.get('valid_items',0),'dsa_search_configured':service.is_available,'paid_model_posts':0,'mail_sent':0,'latest_data_not_historical_replay':True})
    print('Free probe complete; see field provenance and HTTP trace. No LLM or notification initialized.')

if __name__=='__main__':main()
