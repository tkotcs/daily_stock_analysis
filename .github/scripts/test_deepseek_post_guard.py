"""Offline fake transports only; exercises native DSA retries and shared sync/async gate."""
import asyncio,json,os,pathlib,sys,unittest
from unittest.mock import patch
import httpx
sys.path.insert(0,str(pathlib.Path(os.getenv('DSA_FIXED_SOURCE',str(pathlib.Path(__file__).resolve().parents[2]))).resolve()))
from deepseek_post_guard import OnePostGuard,GuardStop,PreflightIntercept,ENDPOINT

def request():return httpx.Request('POST',ENDPOINT,json={'model':'deepseek-flash','messages':[]})
def response(req):return httpx.Response(200,json={'offline':True},request=req)

class Tests(unittest.TestCase):
    def setUp(self):self.sent=0
    def fake(self,transport,req):self.sent+=1;return response(req)
    def test_preflight_zero_sent(self):
        with patch.object(httpx.HTTPTransport,'handle_request',self.fake):
            g=OnePostGuard();g.install()
            try:
                with self.assertRaises(PreflightIntercept):httpx.HTTPTransport(retries=0).handle_request(request())
                self.assertEqual(self.sent,0)
            finally:g.restore()
    def test_second_sync_blocked(self):
        with patch.object(httpx.HTTPTransport,'handle_request',self.fake):
            g=OnePostGuard(preflight=False);g.install()
            try:
                t=httpx.HTTPTransport(retries=0);t.handle_request(request())
                with self.assertRaises(GuardStop):t.handle_request(request())
                self.assertEqual(self.sent,1)
            finally:g.restore()
    def test_sync_async_shared_quota(self):
        async def fake_async(t,r):self.sent+=1;return response(r)
        with patch.object(httpx.HTTPTransport,'handle_request',self.fake),patch.object(httpx.AsyncHTTPTransport,'handle_async_request',fake_async):
            g=OnePostGuard(preflight=False);g.install()
            try:
                httpx.HTTPTransport(retries=0).handle_request(request())
                async def run():
                    with self.assertRaises(GuardStop):await httpx.AsyncHTTPTransport(retries=0).handle_async_request(request())
                asyncio.run(run());self.assertEqual(self.sent,1)
            finally:g.restore()
    def test_async_first_preflight(self):
        g=OnePostGuard();g.install()
        try:
            async def run():
                with self.assertRaises(PreflightIntercept):await httpx.AsyncHTTPTransport(retries=0).handle_async_request(request())
            asyncio.run(run());self.assertEqual(g.allowed,0)
        finally:g.restore()
    def test_wrong_endpoint(self):
        g=OnePostGuard()
        for url in (ENDPOINT+'?x=1',ENDPOINT+'/',ENDPOINT.replace('https:','http:'),'https://api.deepseek.com/beta/chat/completions','https://api.openai.com/v1/chat/completions'):
            with self.assertRaises(GuardStop):g.check(httpx.Request('POST',url,json={}),httpx.HTTPTransport(retries=0))
    def test_retry_nonzero_reject(self):
        with self.assertRaises(GuardStop):OnePostGuard().check(request(),httpx.HTTPTransport(retries=2))
    def test_redirect_disabled(self):
        g=OnePostGuard();g.install()
        try:
            with httpx.Client(follow_redirects=True) as c:
                self.assertFalse(c.follow_redirects)
                with self.assertRaises(GuardStop):c.send(request(),follow_redirects=True)
            async def run():
                async with httpx.AsyncClient(follow_redirects=True) as c:self.assertFalse(c.follow_redirects)
            asyncio.run(run())
        finally:g.restore()
    def test_custom_transports_replaced_with_zero_retry_standard(self):
        g=OnePostGuard();g.install()
        try:
            with httpx.Client(transport=httpx.MockTransport(response)) as c:
                self.assertIs(type(c._transport),httpx.HTTPTransport)
                self.assertEqual(c._transport._pool._retries,0)
            async def run():
                async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as c:
                    self.assertIs(type(c._transport),httpx.AsyncHTTPTransport)
                    self.assertEqual(c._transport._pool._retries,0)
            asyncio.run(run())
        finally:g.restore()
    def test_native_parameter_recovery_blocked(self):
        from src.llm.errors import call_litellm_with_param_recovery
        def failure(t,r):self.sent+=1;raise RuntimeError("Unsupported parameter: 'temperature'")
        with patch.object(httpx.HTTPTransport,'handle_request',failure):
            g=OnePostGuard(preflight=False);g.install()
            try:
                t=httpx.HTTPTransport(retries=0)
                with self.assertRaises(GuardStop):call_litellm_with_param_recovery(lambda kw:t.handle_request(request()),model='deepseek/deepseek-flash',call_kwargs={'temperature':.7})
                self.assertEqual(self.sent,1);self.assertEqual(g.blocked,1)
            finally:g.restore()
    def test_native_stream_failure_blocked(self):
        from src.config import Config
        from src.analyzer import GeminiAnalyzer
        a=GeminiAnalyzer(config=Config(litellm_model='deepseek/deepseek-flash',deepseek_api_keys=['offline-placeholder-only'],litellm_fallback_models=[],report_integrity_retry=0))
        def failure(t,r):self.sent+=1;raise RuntimeError('offline stream failure')
        with patch.object(httpx.HTTPTransport,'handle_request',failure):
            g=OnePostGuard(preflight=False);g.install()
            try:
                t=httpx.HTTPTransport(retries=0)
                a._dispatch_litellm_completion=lambda *x,**kw:t.handle_request(request())
                with self.assertRaises(GuardStop):a._call_litellm('offline',{'max_tokens':8192},stream=True)
                self.assertEqual(self.sent,1);self.assertEqual(g.blocked,1)
            finally:g.restore()

if __name__=='__main__':unittest.main()
