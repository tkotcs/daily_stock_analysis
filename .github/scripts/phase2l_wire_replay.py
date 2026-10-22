"""Actual newly captured packet through the pinned native SDK, fake transport only."""
import os,sys,pathlib,json,hashlib,tempfile,socket,ipaddress
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import argparse
parser=argparse.ArgumentParser()
for arg in ('source','bundle','out','cache'):parser.add_argument('--'+arg,required=True,type=pathlib.Path)
args=parser.parse_args()
C=pathlib.Path(__file__).resolve().parent;G=args.source.resolve();B=args.bundle.resolve();O=args.out.resolve();O.mkdir(parents=True,exist_ok=False)
for k in list(os.environ):
    if any(x in k for x in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')):os.environ.pop(k,None)
os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True',DEEPSEEK_API_BASE='https://api.deepseek.com',CUSTOM_TIKTOKEN_CACHE_DIR=str(args.cache.resolve()))
sys.path[:0]=[str(C),str(G)]
original_connect=socket.socket.connect
def deny(sock,address):
    if isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback:return original_connect(sock,address)
    raise AssertionError('real_network_forbidden')
socket.socket.connect=deny
import httpx
from nvda_frozen_once import load_packet,dispatch_frozen
from authorized_once import LiveSession,canonical_sha,FIXED
from deepseek_post_guard import OnePostGuard,GuardStop
from test_authorized_once import PRICE,SSE,KEY
from src.config import Config
from src.analyzer import GeminiAnalyzer
summary=json.loads((B/'CAPTURE_SUMMARY.json').read_text(encoding='utf-8'));packet=load_packet(B,summary['request_sha256'])
try:load_packet(B,'0'*64);raise AssertionError('tampered identity accepted')
except GuardStop:pass
with tempfile.TemporaryDirectory() as t:
    auth={'authorize_paid_post':True,'authorization_reference':'OFFLINE_FAKE_NOT_AUTHORIZED','secret_upload_approval_reference':'OFFLINE_FAKE','run_id':'offline-wire-only','fixed_commit':FIXED,'request_sha256':canonical_sha(packet),'pricing_sha256':hashlib.sha256(PRICE).hexdigest(),'reservation_usd':'.03','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}
    def get(url,key=None):
        if url.endswith('/models'):return b'{"data":[{"id":"deepseek-flash"}]}'
        if url.endswith('/balance'):return b'{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"29.87"}]}'
        return PRICE
    session=LiveSession(pathlib.Path(t),auth,KEY,'offline-wire-only',get);sent=[]
    def fake(transport,request):
        sent.append(json.loads(request.content));return httpx.Response(200,stream=httpx.ByteStream(SSE),headers={'content-type':'text/event-stream'},request=request)
    with patch.object(httpx.HTTPTransport,'handle_request',fake):
        config=Config(litellm_model='deepseek/deepseek-flash',deepseek_api_keys=[KEY],litellm_fallback_models=[],report_integrity_retry=0)
        analyzer=GeminiAnalyzer(config=config)
        guard=OnePostGuard(preflight=False,before_send=session.approve,on_response=session.on_response,on_error=session.on_error);guard.install()
        try:
            text,usage=dispatch_frozen(analyzer,packet,config)
            assert text=='fixture' and sent==[packet] and canonical_sha(sent[0])==summary['request_sha256']
            result={'status':'passed_fake_transport_only','material_sha256':canonical_sha(packet),'business_commit':FIXED,'actual_sdk_payload_unchanged':True,'fake_delegate_calls':len(sent),'real_paid_POSTs':0,'wrong_sha_rejected':True,'supplier_usage_is_not_real':True,'no_authorization_created':True}
        finally:guard.restore()
(O/'FROZEN_NEW_PACKET_OFFLINE_TEST.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
