"""Complete offline test entry; literal loopback allowed only for Windows asyncio IPC."""
import ipaddress,json,os,pathlib,socket,sys,unittest
root=pathlib.Path(__file__).resolve().parents[2]
for k in list(os.environ):
    if any(x in k for x in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')):os.environ.pop(k,None)
os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True',DSA_FIXED_SOURCE=str(root))
sys.path.insert(0,str(root))
original=socket.socket.connect
def connect(sock,address):
    if isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback:return original(sock,address)
    raise AssertionError('external_network_forbidden')
def deny(*a,**kw):raise AssertionError('external_network_forbidden')
socket.socket.connect=connect;socket.create_connection=deny
suite=unittest.defaultTestLoader.loadTestsFromNames(['test_nvda_frozen_once','test_deepseek_post_guard','test_authorized_once','test_nvda_native_render','test_quote_currency','test_nvda_research_materials'])
r=unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({'tests':r.testsRun,'errors':len(r.errors),'failures':len(r.failures),'skipped':len(r.skipped),'external_network_forbidden':True,'real_model_posts':0}))
sys.exit(0 if r.wasSuccessful() else 1)
