"""Only three explicit free GETs; never create a model client or serialize a key."""
import argparse,os,pathlib,json,hashlib
from datetime import datetime,timezone
from authorized_once import free_get,BASE,PRICING,verify_prices
p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
out=pathlib.Path(a.out);out.mkdir(exist_ok=False)
key=os.getenv('DEEPSEEK_API_KEY','').strip()
if not key and os.name=='nt':
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as reg:key=winreg.QueryValueEx(reg,'DEEPSEEK_API_KEY')[0].strip()
    except OSError:pass
result={'at':datetime.now(timezone.utc).isoformat(),'key_present':bool(key),'paid_POSTs':0,'GETs_attempted':0}
try:
    if not key:raise RuntimeError('missing_key')
    result['GETs_attempted']+=1;models=json.loads(free_get(BASE+'/models',key));result['flash_available']=any(m.get('id')=='deepseek-flash' for m in models.get('data',[]))
    result['GETs_attempted']+=1;balance=json.loads(free_get(BASE+'/user/balance',key));result['account_available']=balance.get('is_available')
    result['balances']=[{k:v.get(k) for k in ('currency','total_balance')} for v in balance.get('balance_infos',[])]
    result['GETs_attempted']+=1;pricing=free_get(PRICING);result['rates']=verify_prices(pricing);result['pricing_sha256']=hashlib.sha256(pricing).hexdigest();(out/'OFFICIAL_PRICING.html').write_bytes(pricing)
    result['status']='read_only_checks_complete'
except BaseException as exc:result['status']='blocked';result['error_category']=type(exc).__name__;result['http_status']=getattr(exc,'code',None)
(out/'ACCOUNT_READONLY.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
