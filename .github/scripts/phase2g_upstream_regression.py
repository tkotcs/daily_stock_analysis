"""Relevant upstream offline regression under an external-network denial."""
import os,pathlib,socket,sys,ipaddress
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
root=pathlib.Path(__file__).resolve().parents[2]
os.chdir(root);sys.path.insert(0,str(root))
for k in list(os.environ):
    if any(x in k for x in ('API_KEY','PASSWORD','ACCESS_TOKEN','WEBHOOK')):os.environ.pop(k,None)
def deny(*a,**k):raise AssertionError('external_network_forbidden')
original_connect=socket.socket.connect
def connect(sock,address):
    if isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback:return original_connect(sock,address)
    raise AssertionError('external_network_forbidden')
socket.socket.connect=connect;socket.create_connection=deny
import pytest
sys.exit(pytest.main(['-q','tests/test_yfinance_class_shares.py','tests/test_yfinance_fundamental_adapter.py','tests/test_analyzer_prompt_language.py','tests/test_analyzer_news_prompt.py','tests/test_tw_report_consumption.py']))
