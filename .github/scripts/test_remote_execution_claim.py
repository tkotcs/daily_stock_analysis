"""Targeted reservation tests; all model transport is simulated."""
import hashlib,json,os,pathlib,sqlite3,subprocess,sys,tempfile,time,unittest
from contextlib import closing
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from remote_execution_claim import GitHubAPI,RemoteExecutionClaim
from deepseek_post_guard import GuardStop,OnePostGuard,ENDPOINT

COMMIT='a'*40
BATCH='b'*64
MEMBERS=[{'symbol':c,'request_sha256':hashlib.sha256(c.encode()).hexdigest()} for c in ('NVDA','MU','QQQ')]

class DatabaseAPI:
    """Atomic INSERT unique index models GitHub's create-ref operation across processes."""
    def __init__(self,path):self.path=path;self.fail=None
    def __call__(self,method,path,value=None):
        if path=='rulesets':return [{'id':1,'name':'dsa-mvp-execution-claims'}]
        if path=='rulesets/1':
            if self.fail=='protection_missing':return {}
            return {'enforcement':'active','target':'tag','current_user_can_bypass':'never','bypass_actors':[], 'conditions':{'ref_name':{'exclude':[],'include':['refs/tags/dsa-mvp-consumed-v1/**','refs/tags/dsa-mvp-claim-test-v1/**']}},'rules':[{'type':'update'},{'type':'deletion'}]}
        with closing(sqlite3.connect(self.path,timeout=10)) as db, db:
            if method=='POST' and path=='tags':
                sha=hashlib.sha1(json.dumps(value,sort_keys=True).encode()).hexdigest();tag={**value,'sha':sha,'object':{'sha':value['object'],'type':'commit'}}
                db.execute('INSERT OR IGNORE INTO objects VALUES(?,?)',(sha,json.dumps(tag)));return tag
            if method=='POST' and path=='refs':
                try:db.execute('INSERT INTO refs VALUES(?,?)',(value['ref'],value['sha']))
                except sqlite3.IntegrityError:raise GuardStop('remote_claim_HTTP_422_no_retry') from None
                db.commit()
                if self.fail=='write_unknown':raise GuardStop('remote_claim_result_unknown_no_retry')
                return {'ref':value['ref'],'object':{'sha':value['sha'],'type':'tag'}}
            if method=='GET' and path.startswith('ref/'):
                if self.fail=='read_unknown':raise GuardStop('remote_claim_result_unknown_no_retry')
                row=db.execute('SELECT sha FROM refs WHERE name=?',('refs/'+path[4:],)).fetchone()
                if not row:raise GuardStop('remote_claim_HTTP_404_no_retry')
                return {'ref':'refs/'+path[4:],'object':{'sha':row[0],'type':'tag'}}
            if method=='GET' and path.startswith('tags/'):
                row=db.execute('SELECT value FROM objects WHERE sha=?',(path[5:],)).fetchone();return json.loads(row[0])
        raise AssertionError('unexpected API operation')

def initialize(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE refs(name TEXT PRIMARY KEY,sha TEXT NOT NULL)');db.execute('CREATE TABLE objects(sha TEXT PRIMARY KEY,value TEXT)')

def worker(database,out,run,batch,commit,start=None,github=False):
    calls=[];result={'run':run,'model_POSTs':0,'real_model_POSTs':0}
    try:
        if start:
            deadline=time.monotonic()+20
            while not pathlib.Path(start).exists():
                if time.monotonic()>deadline:raise GuardStop('test_barrier_timeout')
                time.sleep(.01)
        api=GitHubAPI(os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_TOKEN']) if github else DatabaseAPI(database)
        claim=RemoteExecutionClaim(api,batch,run,commit,namespace='dsa-mvp-claim-test-v1' if github else 'dsa-mvp-consumed-v1')
        members=[{**m,'request_sha256':hashlib.sha256((batch+m['symbol']).encode()).hexdigest()} for m in MEMBERS] if github else MEMBERS
        claim.reserve(members)
        for m in members:
            claim.before_send(m['symbol'],m['request_sha256']);calls.append(m['symbol'])
        result.update(status='won',model_POSTs=len(calls),fake_calls=calls,records=claim.records)
    except GuardStop as error:result.update(status='blocked',reason=str(error),model_POSTs=len(calls))
    pathlib.Path(out).write_text(json.dumps(result,indent=2),'utf-8')

class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name);self.db=self.root/'state.sqlite';initialize(self.db);self.api=DatabaseAPI(self.db)
    def claim(self,run='1',batch=BATCH):return RemoteExecutionClaim(self.api,batch,run,COMMIT)
    def test_success_and_repeat_request_rejected(self):
        c=self.claim();c.reserve(MEMBERS)
        for m in MEMBERS:c.before_send(m['symbol'],m['request_sha256'])
        with self.assertRaises(GuardStop):c.before_send('NVDA',MEMBERS[0]['request_sha256'])
        self.assertEqual(len(c.sent),3)
    def test_same_batch_other_runner_rejected(self):
        self.claim().reserve(MEMBERS)
        with self.assertRaises(GuardStop):self.claim('2').reserve(MEMBERS)
    def test_same_request_different_batch_rejected(self):
        self.claim().reserve(MEMBERS)
        with self.assertRaises(GuardStop):self.claim('2','c'*64).reserve(MEMBERS)
    def test_reservation_response_lost_stays_burned(self):
        self.api.fail='write_unknown'
        with self.assertRaises(GuardStop):self.claim().reserve(MEMBERS)
        self.api.fail=None
        with self.assertRaises(GuardStop):self.claim('2').reserve(MEMBERS)
    def test_read_unknown_blocks_before_send(self):
        c=self.claim();c.reserve(MEMBERS);self.api.fail='read_unknown'
        with self.assertRaises(GuardStop):c.before_send('NVDA',MEMBERS[0]['request_sha256'])
        self.assertFalse(c.sent)
    def test_changed_remote_owner_blocks(self):
        c=self.claim();c.reserve(MEMBERS)
        with closing(sqlite3.connect(self.db)) as db, db:db.execute('UPDATE refs SET sha=? WHERE name=?',('d'*40,'refs/'+c.records[BATCH]['ref']))
        with self.assertRaises(GuardStop):c.before_send('NVDA',MEMBERS[0]['request_sha256'])
    def test_mismatched_symbol_and_unreserved_block(self):
        c=self.claim()
        with self.assertRaises(GuardStop):c.before_send('NVDA',MEMBERS[0]['request_sha256'])
        c.reserve(MEMBERS)
        with self.assertRaises(GuardStop):c.before_send('MU',MEMBERS[0]['request_sha256'])
    def test_partial_claim_cannot_send(self):
        c=self.claim();self.api.fail='write_unknown'
        with self.assertRaises(GuardStop):c.reserve(MEMBERS)
        with self.assertRaises(GuardStop):c.before_send('NVDA',MEMBERS[0]['request_sha256'])
    def test_two_isolated_processes_race_and_fresh_replay(self):
        barrier=self.root/'start';outs=[self.root/'one.json',self.root/'two.json'];processes=[]
        for i,out in enumerate(outs):
            processes.append(subprocess.Popen([sys.executable,'-I',__file__,'--worker',str(self.db),str(out),str(i+1),BATCH,COMMIT,str(barrier)]))
        barrier.touch()
        for p in processes:self.assertEqual(p.wait(timeout=40),0)
        results=[json.loads(p.read_text()) for p in outs]
        self.assertEqual(sorted(r['model_POSTs'] for r in results),[0,3]);self.assertEqual(sum(r['real_model_POSTs'] for r in results),0)
        out=self.root/'third.json';subprocess.run([sys.executable,'-I',__file__,'--worker',str(self.db),str(out),'3',BATCH,COMMIT],check=True,timeout=30)
        self.assertEqual(json.loads(out.read_text())['model_POSTs'],0)
    def test_timeout_cannot_send_second_POST_or_new_runner(self):
        import httpx
        from unittest.mock import patch
        c=self.claim();c.reserve(MEMBERS);calls=[]
        def fake(transport,request):calls.append(1);raise httpx.ReadTimeout('simulated no response')
        with patch.object(httpx.HTTPTransport,'handle_request',fake):
            guard=OnePostGuard(preflight=False,before_send=lambda body:c.before_send('NVDA',MEMBERS[0]['request_sha256']));guard.install()
            try:
                with httpx.Client() as client:
                    with self.assertRaises(httpx.ReadTimeout):client.post(ENDPOINT,json={})
                    with self.assertRaises(GuardStop):client.post(ENDPOINT,json={})
            finally:guard.restore()
        self.assertEqual(len(calls),1)
        with self.assertRaises(GuardStop):self.claim('2').reserve(MEMBERS)
    def test_transport_denies_other_host_and_method(self):
        api=GitHubAPI('owner/repository','placeholder')
        for method,path in [('DELETE','refs/tags/x'),('PATCH','refs/tags/x'),('GET','https://elsewhere'),('POST','../x')]:
            with self.assertRaises(GuardStop):api(method,path)
    def test_missing_protection_blocks(self):
        self.api.fail='protection_missing'
        with self.assertRaises(GuardStop):self.claim().reserve(MEMBERS)
    def test_protection_disabled_after_reserve_blocks(self):
        c=self.claim();c.reserve(MEMBERS);self.api.fail='protection_missing'
        with self.assertRaises(GuardStop):c.before_send('NVDA',MEMBERS[0]['request_sha256'])
    def test_hidden_admin_list_requires_explicit_current_token_denial(self):
        base=self.api
        def hidden(method,path,value=None):
            result=base(method,path,value)
            if path=='rulesets/1':result.pop('bypass_actors')
            return result
        c=RemoteExecutionClaim(hidden,BATCH,'1',COMMIT);c.reserve(MEMBERS)
        c.before_send('NVDA',MEMBERS[0]['request_sha256'])
    def test_missing_or_bypassable_token_decision_blocks(self):
        base=self.api
        for decision in (None,'always','pull_request'):
            def unsafe(method,path,value=None):
                result=base(method,path,value)
                if path=='rulesets/1':result['current_user_can_bypass']=decision
                return result
            with self.assertRaises(GuardStop):RemoteExecutionClaim(unsafe,BATCH,'1',COMMIT).reserve(MEMBERS)
    def test_remote_API_timeout_is_not_retried_and_no_secret_in_error(self):
        from unittest.mock import Mock
        api=GitHubAPI('owner/repository','do-not-log-token')
        api.opener.open=Mock(side_effect=TimeoutError('do-not-log-token'))
        with self.assertRaises(GuardStop) as raised:api('POST','refs',{'ref':'refs/tags/x','sha':COMMIT})
        self.assertEqual(api.opener.open.call_count,1)
        self.assertNotIn('do-not-log-token',str(raised.exception))
    def test_production_integration_order(self):
        source=(pathlib.Path(__file__).parent/'mvp_three_live.py').read_text('utf-8')
        self.assertLess(source.index('claim.reserve('),source.index('dispatch_frozen(analyzer'))
        self.assertLess(source.index('session.approve(body)'),source.index('claim.before_send(code'))
        self.assertIn('authorization_expired_during_remote_check',source)

def github_smoke(out):
    """Two fresh interpreters race actual GitHub refs, with NO model client/key."""
    out=pathlib.Path(out);out.mkdir(exist_ok=False)
    batch=hashlib.sha256(('free-claim-test:'+os.environ['GITHUB_RUN_ID']).encode()).hexdigest()
    # Separate request namespace AND hashes from any paid material.
    barrier=out/'start';processes=[]
    for i in (1,2):
        processes.append(subprocess.Popen([sys.executable,'-I',__file__,'--github-worker',str(out/(str(i)+'.json')),os.environ['GITHUB_RUN_ID']+str(i),batch,os.environ['GITHUB_SHA'],str(barrier)]))
    barrier.touch()
    for p in processes:
        if p.wait(timeout=180)!=0:raise SystemExit('claim smoke process failed')
    results=[json.loads((out/(str(i)+'.json')).read_text()) for i in (1,2)]
    assert sorted(r['model_POSTs'] for r in results)==[0,3],results
    import urllib.request,urllib.error
    from remote_execution_claim import NoRedirect
    url='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/git/refs/tags/dsa-mvp-claim-test-v1/batch/'+batch
    negative=[]
    for method,data in [('PATCH',json.dumps({'sha':os.environ['GITHUB_SHA'],'force':True}).encode()),('DELETE',None)]:
        req=urllib.request.Request(url,method=method,data=data,headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'DSA-MVP-claim-negative-test'})
        try:
            with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as response:status=response.status
        except urllib.error.HTTPError as error:status=error.code
        assert status in (403,422),'test marker update/delete protection not enforced'
        negative.append({'method':method,'HTTP':status,'namespace':'FREE_TEST_ONLY'})
    (out/'IMMUTABILITY_CHECK.json').write_text(json.dumps(negative,indent=2),'utf-8')
    worker(None,out/'fresh-replay.json',os.environ['GITHUB_RUN_ID']+'3',batch,os.environ['GITHUB_SHA'],github=True)
    assert json.loads((out/'fresh-replay.json').read_text())['model_POSTs']==0
    (out/'RESULT.json').write_text(json.dumps({'real_model_POSTs':0,'paid_keys_injected':False,'isolated_processes':3,'race':'one owner only','fresh_runner_replay':'blocked','test_namespace_only':True,'batch_test_sha':batch},indent=2),'utf-8')

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':worker(*sys.argv[2:])
    elif len(sys.argv)>1 and sys.argv[1]=='--github-worker':worker(None,*sys.argv[2:],github=True)
    elif len(sys.argv)>1 and sys.argv[1]=='--github-smoke':github_smoke(sys.argv[2])
    else:unittest.main(verbosity=2)
