"""Related upstream regressions in a no-key, external-network-denied process."""
from pathlib import Path
import ipaddress, os, socket, smtplib, sys
source, cache, output = map(lambda p: Path(p).resolve(), sys.argv[1:4])
os.chdir(source); sys.path[:0] = [str(source), str(source/'.github/scripts')]
for key in list(os.environ):
    if any(x in key for x in ('API_KEY', 'PASSWORD', 'ACCESS_TOKEN', 'WEBHOOK')): os.environ.pop(key, None)
os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', DSA_FIXED_SOURCE=str(source),
                  CUSTOM_TIKTOKEN_CACHE_DIR=str(cache))
original = socket.socket.connect
def deny(*args, **kwargs): raise AssertionError('offline_external_network_or_mail_forbidden')
def connect(sock, address):
    if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
        return original(sock, address)
    return deny()
socket.socket.connect = connect; socket.create_connection = deny
smtplib.SMTP = deny; smtplib.SMTP_SSL = deny
import pytest
modules = ['tests/test_phase2i_quote_facts.py', 'tests/test_yfinance_class_shares.py',
 'tests/test_yfinance_fundamental_adapter.py', 'tests/test_analyzer_prompt_language.py',
 'tests/test_analyzer_news_prompt.py', 'tests/test_tw_report_consumption.py',
 'tests/test_pipeline_realtime_indicators.py', 'tests/test_notification_empty_news_disclosure.py',
 'tests/test_notification_report_fixtures.py', 'tests/test_pipeline_index_targets.py',
 '.github/scripts/test_nvda_frozen_once.py', '.github/scripts/test_deepseek_post_guard.py',
 '.github/scripts/test_authorized_once.py', '.github/scripts/test_nvda_native_render.py',
 '.github/scripts/test_quote_currency.py', '.github/scripts/test_nvda_research_materials.py', '.github/scripts/test_phase2j_free_guard.py', '.github/scripts/test_phase2k_binding.py', '.github/scripts/test_phase2l_inputs.py']
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider', '--junitxml='+str(output/'TESTS.xml')] + modules))
