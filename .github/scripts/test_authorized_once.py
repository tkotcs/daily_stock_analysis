"""All network delegates are fakes; no real credentials or model POSTs."""
import asyncio,hashlib,json,os,pathlib,sys,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import httpx
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
sys.path.insert(0,str(pathlib.Path(os.getenv('DSA_FIXED_SOURCE',str(pathlib.Path(__file__).resolve().parents[2]))).resolve()))
from authorized_once import LiveSession,SafeWriter,canonical_sha,usage_cost,verify_prices,with_usage_options,FIXED,BASE,PRICING
from deepseek_post_guard import OnePostGuard,GuardStop,ENDPOINT

KEY='offline-credential-sentinel'
BODY={'model':'deepseek-flash','max_tokens':8192,'stream':True,'stream_options':{'include_usage':True},'temperature':.7,'messages':[{'role':'user','content':'中文离线材料'}]}
PRICE=b'<table>DeepSeek-V4.1-Flash 1M INPUT TOKENS (CACHE HIT) OFF-PEAK $0.003 $0.022 PEAK $0.006 $0.044 1M INPUT TOKENS (CACHE MISS) OFF-PEAK $0.15 $0.66 PEAK $0.3 $1.32 1M OUTPUT TOKENS OFF-PEAK $0.6 $1.98 PEAK $1.2 $3.96</table>'
SSE=b'data: {"model":"deepseek-flash","choices":[{"delta":{"content":"fixture"},"finish_reason":"stop"}],"usage":{"prompt_tokens":100,"completion_tokens":20}}\n\ndata: [DONE]\n\n'

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.gets=[];self.sent=0
        self.auth={'authorize_paid_post':True,'authorization_reference':'OFFLINE_ONLY','secret_upload_approval_reference':'OFFLINE_ONLY','run_id':'offline-test-1','fixed_commit':FIXED,'request_sha256':canonical_sha(BODY),'pricing_sha256':hashlib.sha256(PRICE).hexdigest(),'reservation_usd':'.03','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}
    def tearDown(self):self.tmp.cleanup()
    def get(self,url,key=None):
        self.gets.append(url)
        if url.endswith('/models'):return b'{"data":[{"id":"deepseek-flash"}]}'
        if url.endswith('/balance'):return b'{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"29.91"}]}'
        return PRICE
    def session(self,**kwargs):return LiveSession(self.root,kwargs.get('auth',self.auth),kwargs.get('key',KEY),kwargs.get('run_id','offline-test-1'),kwargs.get('get',self.get))
    def request(self):return httpx.Request('POST',ENDPOINT,json=BODY)
    def guard(self,s):return OnePostGuard(preflight=False,before_send=s.approve,on_response=s.on_response,on_error=s.on_error)
    def result(self):return json.loads((self.root/'RESPONSE_RESULT.json').read_text(encoding='utf-8'))
    def test_requires_both_approvals(self):
        for field in ['authorize_paid_post','authorization_reference','secret_upload_approval_reference']:
            a={**self.auth,field:False}
            with self.assertRaises(GuardStop):self.session(auth=a)
    def test_run_and_commit_binding(self):
        for a in [{**self.auth,'run_id':'other'},{**self.auth,'fixed_commit':'other'}]:
            with self.assertRaises(GuardStop):self.session(auth=a)
    def test_expiry_and_timezone_required(self):
        for value in ['2020-01-01T00:00:00+00:00','2099-01-01','bad']:
            with self.assertRaises(GuardStop):self.session(auth={**self.auth,'expires_at':value})
    def test_reserve_limits(self):
        for value in ['0','.031','NaN','Infinity','bad']:
            with self.assertRaises(GuardStop):self.session(auth={**self.auth,'reservation_usd':value})
    def test_missing_key(self):
        with self.assertRaises(GuardStop):self.session(key='')
    def test_hash_mismatch_before_free_get(self):
        s=self.session(auth={**self.auth,'request_sha256':'0'*64})
        with self.assertRaises(GuardStop):s.approve(BODY)
        self.assertEqual(self.gets,[])
    def test_unreviewed_parameters(self):
        for patch_body in [{'max_tokens':8193},{'model':'other'},{'stream':False},{'tools':[]}]:
            body={**BODY,**patch_body};s=self.session(auth={**self.auth,'request_sha256':canonical_sha(body)})
            with self.assertRaises(GuardStop):s.approve(body)
    def test_insufficient_reserve(self):
        with self.assertRaises(GuardStop):self.session(auth={**self.auth,'reservation_usd':'.001'}).approve(BODY)
    def test_no_duplicate_local_marker(self):
        s=self.session();s.approve(BODY)
        with self.assertRaises(FileExistsError):self.session().approve(BODY)
    def test_balance_or_model_failure(self):
        for failure in [b'{"data":[]}',b'{"is_available":false}']:
            def get(url,key=None):return failure if ('/models' in url and b'data' in failure) or ('/balance' in url and b'available' in failure) else self.get(url,key)
            with self.assertRaises(GuardStop):self.session(get=get).approve(BODY)
    def test_pricing_change_blocks(self):
        with self.assertRaises(GuardStop):self.session(auth={**self.auth,'pricing_sha256':'bad'}).approve(BODY)
        with self.assertRaises(GuardStop):verify_prices(PRICE.replace(b'$0.3 ',b'$0.4 '))
    def test_sync_raw_capture(self):
        def fake(t,r):self.sent+=1;return httpx.Response(200,content=SSE,request=r)
        s=self.session()
        with patch.object(httpx.HTTPTransport,'handle_request',fake):
            g=self.guard(s);g.install()
            try:
                with httpx.Client() as c:c.send(self.request()).read()
                with self.assertRaises(GuardStop):httpx.Client().send(self.request())
            finally:g.restore()
        x=self.result();self.assertEqual(self.sent,1);self.assertTrue(x['sse_done']);self.assertEqual(x['finish_reason'],'stop');self.assertEqual((self.root/'RAW_RESPONSE_BODY.bin').read_bytes(),SSE)
    def test_async_raw_capture(self):
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):yield SSE
        async def fake(t,r):self.sent+=1;return httpx.Response(200,stream=Stream(),request=r)
        s=self.session()
        with patch.object(httpx.AsyncHTTPTransport,'handle_async_request',fake):
            g=self.guard(s);g.install()
            async def run():
                async with httpx.AsyncClient() as c:await c.send(self.request())
            try:asyncio.run(run())
            finally:g.restore()
        self.assertEqual(self.sent,1);self.assertTrue(self.result()['sse_done'])
    def test_transport_timeout_is_unknown_and_no_retry(self):
        def fake(t,r):self.sent+=1;raise httpx.ReadTimeout(KEY)
        s=self.session()
        with patch.object(httpx.HTTPTransport,'handle_request',fake):
            g=self.guard(s);g.install()
            try:
                for _ in range(2):
                    with self.assertRaises(GuardStop):httpx.Client().send(self.request())
            finally:g.restore()
        self.assertEqual(self.sent,1);self.assertTrue(self.result()['result_unknown']);self.assertEqual(self.result()['error_category'],'ReadTimeout')
    def test_http_error_saved_without_recovery(self):
        def fake(t,r):self.sent+=1;return httpx.Response(429,content=b'limited',request=r)
        s=self.session()
        with patch.object(httpx.HTTPTransport,'handle_request',fake):
            g=self.guard(s);g.install()
            try:
                with self.assertRaises(GuardStop):httpx.Client().send(self.request())
            finally:g.restore()
        self.assertEqual(self.result()['http_status'],429);self.assertEqual((self.root/'RAW_RESPONSE_BODY.bin').read_bytes(),b'limited')
    def test_partial_stream_retained(self):
        class Partial(httpx.SyncByteStream):
            def __iter__(self):yield SSE[:25];raise httpx.ReadTimeout('fixture')
        def fake(t,r):return httpx.Response(200,stream=Partial(),request=r)
        s=self.session()
        with patch.object(httpx.HTTPTransport,'handle_request',fake):
            g=self.guard(s);g.install()
            try:
                with self.assertRaises(GuardStop):httpx.Client().send(self.request())
            finally:g.restore()
        self.assertEqual((self.root/'RAW_RESPONSE_BODY.bin').read_bytes(),SSE[:25]);self.assertTrue(self.result()['result_unknown'])
    def test_missing_usage_not_zero(self):self.assertTrue(usage_cost(None)['status'].startswith('unknown'))
    def test_cache_cost_and_reasoning_not_double_counted(self):
        x=usage_cost({'prompt_tokens':100,'prompt_cache_hit_tokens':60,'prompt_cache_miss_tokens':40,'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':5}})
        self.assertEqual(x['peak_usd'],'0.00003636');self.assertEqual(x['reasoning_tokens'],5)
        self.assertTrue(usage_cost({'prompt_tokens':100,'prompt_cache_hit_tokens':101,'prompt_cache_miss_tokens':0,'completion_tokens':1})['status'].startswith('unknown'))
    def test_log_split_write_redacts(self):
        p=self.root/'log';w=SafeWriter(p,KEY);w.write(KEY[:5]);w.write(KEY[5:]+'\n');w.close();self.assertNotIn(KEY,p.read_text(encoding='utf-8'))
    def test_raw_secret_echo_redacted_and_marked(self):
        s=self.session();s.started=__import__('time').monotonic();s.add(KEY.encode());s.finish()
        self.assertTrue(self.result()['secret_redaction_changed_raw']);self.assertNotIn(KEY.encode(),(self.root/'RAW_RESPONSE_BODY.bin').read_bytes())
    def test_async_http_error_retained(self):
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):yield b'async-limited'
        async def fake(t,r):self.sent+=1;return httpx.Response(429,stream=Stream(),request=r)
        s=self.session()
        with patch.object(httpx.AsyncHTTPTransport,'handle_async_request',fake):
            g=self.guard(s);g.install()
            async def run():
                async with httpx.AsyncClient() as c:
                    with self.assertRaises(GuardStop):await c.send(self.request())
            try:asyncio.run(run())
            finally:g.restore()
        self.assertEqual(self.sent,1);self.assertEqual((self.root/'RAW_RESPONSE_BODY.bin').read_bytes(),b'async-limited')
    def test_native_litellm_stream_uses_same_guard_and_recorder(self):
        from src.config import Config
        from src.analyzer import GeminiAnalyzer
        packet={**BODY,'messages':[{'role':'system','content':'offline system'},{'role':'user','content':'中文离线材料'}]}
        s=self.session(auth={**self.auth,'request_sha256':canonical_sha(packet)})
        def fake(t,r):
            self.sent+=1
            return httpx.Response(200,stream=httpx.ByteStream(SSE),headers={'Content-Type':'text/event-stream'},request=r)
        with patch.dict(os.environ,{'DEEPSEEK_API_BASE':BASE,'LITELLM_LOCAL_MODEL_COST_MAP':'True'}),patch.object(httpx.HTTPTransport,'handle_request',fake):
            a=GeminiAnalyzer(config=Config(litellm_model='deepseek/deepseek-flash',deepseek_api_keys=[KEY],litellm_fallback_models=[],report_integrity_retry=0))
            original=a._dispatch_litellm_completion
            a._dispatch_litellm_completion=lambda model,kwargs,**kw:original(model,with_usage_options(kwargs),**kw)
            g=self.guard(s);g.install()
            try:
                text,model,usage=a._call_litellm('中文离线材料',{'max_tokens':8192,'temperature':.7},system_prompt='offline system',stream=True)
                self.assertEqual(text,'fixture');self.assertEqual(self.sent,1)
            finally:g.restore()
        self.assertEqual(self.result()['http_status'],200)
    def test_concurrent_attempts_only_one_enters_transport(self):
        def fake(t,r):self.sent+=1;return httpx.Response(200,stream=httpx.ByteStream(SSE),request=r)
        s=self.session()
        def attempt(_):
            try:
                httpx.HTTPTransport(retries=0).handle_request(self.request()).read();return 'one'
            except GuardStop:return 'blocked'
        with patch.object(httpx.HTTPTransport,'handle_request',fake):
            g=self.guard(s);g.install()
            try:
                with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(attempt,range(6)))
            finally:g.restore()
        self.assertEqual(results.count('one'),1);self.assertEqual(self.sent,1);self.assertEqual(g.blocked,5)
    def test_example_cannot_authorize(self):
        example=json.loads((pathlib.Path(__file__).parent/'nvda_authorization.example.json').read_text(encoding='utf-8'))
        with self.assertRaises(GuardStop):self.session(auth=example)
    def test_invalid_reasoning_usage_unknown(self):
        self.assertEqual(usage_cost({'prompt_tokens':10,'completion_tokens':2,'completion_tokens_details':{'reasoning_tokens':3}})['status'],'unknown_invalid_reasoning_usage')
    def test_gzip_raw_and_usage_preserved(self):
        import gzip
        raw=gzip.compress(SSE)
        def fake(t,r):return httpx.Response(200,stream=httpx.ByteStream(raw),headers={'content-encoding':'gzip'},request=r)
        s=self.session()
        with patch.object(httpx.HTTPTransport,'handle_request',fake):
            g=self.guard(s);g.install()
            try:httpx.Client().send(self.request())
            finally:g.restore()
        self.assertEqual((self.root/'RAW_RESPONSE_BODY.bin').read_bytes(),raw);self.assertEqual(self.result()['usage']['prompt_tokens'],100)
    def test_expiry_during_get_stops_before_marker(self):
        def get(url,key=None):
            result=self.get(url,key)
            if url==PRICING:self.auth['expires_at']='2020-01-01T00:00:00+00:00'
            return result
        s=self.session(get=get)
        with self.assertRaises(GuardStop):s.approve(BODY)
        self.assertFalse((self.root/'POST_ATTEMPT.json').exists())
    def test_usage_option_preserves_prompt(self):
        x={'stream':True,'messages':BODY['messages'],'max_tokens':8192}
        y=with_usage_options(x);self.assertEqual(y['messages'],x['messages']);self.assertNotIn('stream_options',x)
        self.assertEqual(y['stream_options'],{'include_usage':True})
        with self.assertRaises(GuardStop):with_usage_options({'stream':False})
    def test_missing_or_false_usage_option_blocks(self):
        for v in [None,{}, {'include_usage':False}]:
            body={**BODY,'stream_options':v};s=self.session(auth={**self.auth,'request_sha256':canonical_sha(body)})
            with self.assertRaises(GuardStop):s.approve(body)
    def test_official_terminal_usage_shape(self):
        s=self.session();s.started=__import__('time').monotonic();s.status=200
        chunks=[{'model':'deepseek-flash','choices':[{'delta':{'content':'fixture'},'finish_reason':None}],'usage':None},{'model':'deepseek-flash','choices':[{'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':20,'prompt_cache_hit_tokens':60,'prompt_cache_miss_tokens':40,'completion_tokens_details':{'reasoning_tokens':5}}}]
        s.add((''.join('data: '+json.dumps(x)+'\n\n' for x in chunks)+'data: [DONE]\n\n').encode());s.finish()
        x=self.result();self.assertEqual(x['usage']['prompt_cache_hit_tokens'],60);self.assertEqual(x['finish_reason'],'stop');self.assertEqual(x['cost_estimate']['peak_usd'],'0.00003636')

if __name__=='__main__':unittest.main()
