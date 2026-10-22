"""Frozen payload replay tests; fake transport only."""
import hashlib,json,os,pathlib,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import httpx
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
sys.path.insert(0,str(pathlib.Path(os.getenv('DSA_FIXED_SOURCE',str(pathlib.Path(__file__).resolve().parents[2]))).resolve()))
from nvda_frozen_once import load_packet,dispatch_frozen
from authorized_once import LiveSession,canonical_sha,FIXED,BASE
from deepseek_post_guard import OnePostGuard,GuardStop
from test_authorized_once import BODY,PRICE,SSE,KEY
class Tests(unittest.TestCase):
    def test_load_exact_and_reject_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'ORIGINAL_REQUEST_PACKET.json').write_text(json.dumps(BODY),encoding='utf-8')
            self.assertEqual(load_packet(root,canonical_sha(BODY)),BODY)
            with self.assertRaises(GuardStop):load_packet(root,'0'*64)
    def test_native_sdk_frozen_wire_identity_no_prompt_builder(self):
        from src.config import Config
        from src.analyzer import GeminiAnalyzer
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            auth={'authorize_paid_post':True,'authorization_reference':'OFFLINE','secret_upload_approval_reference':'OFFLINE','run_id':'fixture','fixed_commit':FIXED,'request_sha256':canonical_sha(BODY),'pricing_sha256':hashlib.sha256(PRICE).hexdigest(),'reservation_usd':'.03','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}
            def get(url,key=None):
                if url.endswith('/models'):return b'{"data":[{"id":"deepseek-flash"}]}'
                if url.endswith('/balance'):return b'{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"29.91"}]}'
                return PRICE
            session=LiveSession(root,auth,KEY,'fixture',get);sent=[]
            def fake(t,r):sent.append(json.loads(r.content));return httpx.Response(200,stream=httpx.ByteStream(SSE),headers={'content-type':'text/event-stream'},request=r)
            with patch.dict(os.environ,{'DEEPSEEK_API_BASE':BASE}),patch.object(httpx.HTTPTransport,'handle_request',fake):
                config=Config(litellm_model='deepseek/deepseek-flash',deepseek_api_keys=[KEY],litellm_fallback_models=[],report_integrity_retry=0);a=GeminiAnalyzer(config=config)
                a.analyze=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('prompt rebuild forbidden'))
                g=OnePostGuard(preflight=False,before_send=session.approve,on_response=session.on_response,on_error=session.on_error);g.install()
                try:
                    text,_=dispatch_frozen(a,BODY,config);self.assertEqual(text,'fixture');self.assertEqual(sent,[BODY]);self.assertEqual(canonical_sha(sent[0]),auth['request_sha256'])
                finally:g.restore()
if __name__=='__main__':unittest.main()
