"""Freeze three already-captured native requests; never collect or call a model."""
import argparse,datetime as dt,hashlib,json,pathlib,sys
from decimal import Decimal

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from authorized_once import canonical_sha,free_get,verify_prices,PRICING

BUSINESS='a1daaa302b3a72fb5694c9872ceecf2c4dc0b6e4'
SYMBOLS=('NVDA','MU','QQQ')


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True,type=pathlib.Path);p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);sys.path.insert(0,str(a.source.resolve()))
    from src.core.trading_calendar import get_effective_trading_date,_XCALS_AVAILABLE
    import exchange_calendars as xc,pandas as pd
    now=dt.datetime.now(dt.timezone.utc);target=get_effective_trading_date('us',current_time=now).isoformat();assert _XCALS_AVAILABLE
    pricing=free_get(PRICING);rates=verify_prices(pricing);(a.out/'OFFICIAL_PRICING.html').write_bytes(pricing)
    members=[]
    for code in SYMBOLS:
        src=a.data/code;status=json.loads((src/'STATUS.json').read_text('utf-8'))
        assert status['status']=='success_simulated_model' and status['data_mode']=='fresh_Yahoo_this_run' and status['session']==target
        body=json.loads((src/'FINAL_REQUEST.json').read_text('utf-8'))
        assert body['model']=='deepseek-flash' and body['max_tokens']==16384 and body['thinking']=={'type':'disabled'} and body['stream'] is True and body['stream_options']=={'include_usage':True}
        dest=a.out/code;dest.mkdir();raw=canonical(body);(dest/'FINAL_REQUEST.json').write_bytes(raw)
        context=(src/'NATIVE_CONTEXT.json').read_bytes();(dest/'NATIVE_CONTEXT.json').write_bytes(context)
        asof=json.loads((src/'FINANCIAL_AUDIT.json').read_text('utf-8'))['fetched_at']
        next_session=xc.get_calendar('XNYS').next_session(pd.Timestamp(target))
        expiry=min(dt.datetime.fromisoformat(asof)+dt.timedelta(hours=24),xc.get_calendar('XNYS').session_close(next_session).to_pydatetime())
        estimate=(Decimal(len(raw)+1024)*Decimal('.30')+Decimal(16384)*Decimal('1.20'))/1000000
        members.append({'symbol':code,'request_sha256':canonical_sha(body),'body_bytes':len(raw),'context_sha256':hashlib.sha256(context).hexdigest(),'target_session':target,'analysis_asof':asof,'material_expires_at':expiry.isoformat(),'output_limit':16384,'peak_byte_allowance_estimate_not_formal_bound_USD':str(estimate),'reservation_USD':'0.03','reservation_check':estimate<=Decimal('.03')})
    lock={'profile':'mvp_three_v1','business_commit':BUSINESS,'source_free_run':json.loads((a.data/'RESULTS.json').read_text('utf-8')).get('run_id'),'created_at':now.isoformat(),'canonicalization':'UTF8 json.dumps ensure_ascii=False sort_keys=True separators=(comma,colon); no BOM/newline','members':members,'max_total_POSTs':3,'max_POSTs_per_symbol':1,'automatic_retry':False,'fallback':False,'allow_peak_test':True,'pricing_sha256':hashlib.sha256(pricing).hexdigest(),'rates_USD_per_million':rates,'total_reservation_USD':'0.09','reservation_is_not_supplier_hard_cap':True,'authorize_paid_POST':False}
    (a.out/'REQUEST_SET_LOCK.json').write_bytes(canonical(lock))
    (a.out/'REQUEST_SET_SHA256.txt').write_text(hashlib.sha256(canonical(lock)).hexdigest()+'\n',encoding='utf-8')
    print('Three native request candidates frozen. No paid authorization or model POST.')


if __name__=='__main__':main()
