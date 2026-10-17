"""Prepare paired requests from existing evidence; no collection or live send."""
import argparse,ast,copy,datetime as dt,hashlib,json,math,pathlib,subprocess,sys
from datetime import date
from typing import Dict,Any
from decimal import Decimal

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def computed_function(source):
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='GeminiAnalyzer')
    node=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_format_computed_quote_facts'))
    node.decorator_list=[];env={'Dict':Dict,'Any':Any,'math':math,'date':date}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'<native-computed-facts>','exec'),env)
    return env[node.name]
def prepare(source,bundle,out):
    old=json.loads((bundle/'REQUEST_SET_LOCK.json').read_text('utf-8'))
    oldsrc=subprocess.check_output(['git','show',old['business_commit']+':src/analyzer.py'],cwd=source).decode('utf-8')
    previous=computed_function(oldsrc);current=computed_function((source/'src/analyzer.py').read_text('utf-8'))
    out.mkdir(parents=True,exist_ok=False);members=[]
    for member in old['members']:
        code=member['symbol'];raw=(bundle/code/'NATIVE_CONTEXT.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==member['context_sha256']
        context=json.loads(raw);base=json.loads((bundle/code/'FINAL_REQUEST.json').read_text('utf-8'))
        assert sha(base)==member['request_sha256']
        before,after=previous(context),current(context)
        assert sum(m.get('content','').count(before) for m in base['messages'])==1
        for m in base['messages']:m['content']=m.get('content','').replace(before,after)
        messages_sha=sha(base['messages'])
        for mode,limit in [('nonthinking',16384),('thinking',32768)]:
            body=copy.deepcopy(base);body['thinking']={'type':'enabled' if mode=='thinking' else 'disabled'};body['max_tokens']=limit
            if mode=='thinking':body['reasoning_effort']='high'
            else:body.pop('reasoning_effort',None)
            dest=out/code/mode;dest.mkdir(parents=True)
            payload=canonical(body);(dest/'FINAL_REQUEST.json').write_bytes(payload);(dest/'NATIVE_CONTEXT.json').write_bytes(raw)
            # Character/byte allowance is deliberately labeled approximate, not vendor token usage.
            byte_allowance=len(payload)+1024
            peak=(Decimal(byte_allowance)*Decimal('.30')+Decimal(limit)*Decimal('1.20'))/1000000
            members.append(dict(request_id=code+'_'+mode,symbol=code,mode=mode,request_sha256=sha(body),context_sha256=member['context_sha256'],messages_sha256=messages_sha,
                relative_request=f'{code}/{mode}/FINAL_REQUEST.json',analysis_asof=member['analysis_asof'],material_expires_at=member['material_expires_at'],target_session=member['target_session'],max_tokens=limit,
                reservation_USD='0.06' if mode=='thinking' else '0.03',peak_byte_allowance_estimate_not_hard_bound_USD=str(peak),offpeak_same_allowance_USD=str(peak/2)))
    lock=dict(profile='paired_mode_comparison_proposal_v1',authorize_paid_POST=False,live_workflow_bound=False,model='deepseek-flash',business_commit='577624ad8459871630c690e5760ae504ac6f2b9f',
        historical_source_batch_sha256=hashlib.sha256((bundle/'REQUEST_SET_LOCK.json').read_bytes()).hexdigest(),max_total_POSTs=6,max_POSTs_per_request=1,max_POSTs_per_symbol=2,total_reservation_USD='0.27',automatic_retry=False,fallback=False,
        created_at=dt.datetime.now(dt.timezone.utc).isoformat(),material_expiry_not_extended=True,comparison_limitations=['unequal output caps to accommodate reasoning; report this confound','one observation per mode per symbol; descriptive only'],members=members)
    (out/'COMPARISON_LOCK.json').write_bytes(canonical(lock));(out/'BATCH_SHA256.txt').write_text(sha(lock)+'\n','utf-8')
    return lock
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--bundle',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
    sys.path.insert(0,str(a.source.resolve()))
    lock=prepare(a.source.resolve(),a.bundle.resolve(),a.out.resolve());print(sha(lock))
