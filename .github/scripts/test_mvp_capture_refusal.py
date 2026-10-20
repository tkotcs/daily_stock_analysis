"""Exercise terminal free-data failures without contacting any endpoint."""
import json
import subprocess
import sys
from types import SimpleNamespace

import curl_cffi.requests as curl
import pytest

import mvp_three as capture
from phase2j_free_guard import FreeSafetyStop


@pytest.mark.parametrize('status', [403, 429])
def test_terminal_response_persists_before_escaping_and_blocks_more_calls(tmp_path, monkeypatch, status):
    calls=[]
    def underlying(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=status)
    monkeypatch.setattr(curl.Session, 'request', underlying)
    trace=capture.install_capture_transport(tmp_path)
    with pytest.raises(FreeSafetyStop, match=f'Yahoo_HTTP_{status}_stop_no_retry'):
        curl.Session().get('https://query1.finance.yahoo.com/v1/test/getcrumb?secret=never-record')
    with pytest.raises(FreeSafetyStop):
        curl.Session().get('https://query2.finance.yahoo.com/v8/finance/chart/NVDA')
    assert len(calls)==1
    assert calls[0]['timeout']==15 and calls[0]['allow_redirects'] is False
    saved=(tmp_path/'HTTP_TRACE.json').read_text()
    assert 'never-record' not in saved and json.loads(saved)==trace
    assert trace[0]['status']==status


def test_serial_download_keeps_native_yfinance_exception_on_caller(tmp_path, monkeypatch):
    """Use the installed yfinance download loop; a threaded terminal error would hang."""
    import yfinance as yf
    import yfinance.multi as multi
    monkeypatch.setattr(multi, '_download_one',
                        lambda *a, **k: (_ for _ in ()).throw(FreeSafetyStop('terminal_refusal')))
    monkeypatch.setattr(yf, 'download', yf.download)
    capture.install_serial_download(yf)
    with pytest.raises(FreeSafetyStop, match='terminal_refusal'):
        yf.download('NVDA', threads=True, progress=False)


@pytest.mark.parametrize('status', [403, 429])
def test_parent_stops_remaining_symbols_and_keeps_specific_failure(tmp_path, monkeypatch, status):
    calls=[]
    source=tmp_path/'source';source.mkdir()
    out=tmp_path/'capture'
    def run(command, **kwargs):
        calls.append(command)
        child=out/'NVDA';child.mkdir()
        (child/'STATUS.json').write_text(json.dumps(dict(
            symbol='NVDA', status='failed',
            error=f'FreeSafetyStop:Yahoo_HTTP_{status}_stop_no_retry', real_POSTs=0)))
        (child/'HTTP_TRACE.json').write_text(json.dumps([dict(status=status)]))
        return subprocess.CompletedProcess(command, 0, b'', b'')
    monkeypatch.setattr(capture.subprocess, 'run', run)
    monkeypatch.setattr(capture.subprocess, 'check_output', lambda *a, **k:'business\n')
    monkeypatch.setattr(sys, 'argv', ['mvp_three.py','--source',str(source),'--out',str(out),
                                     '--only','NVDA,MSFT,AAPL'])
    capture.main()
    result=json.loads((out/'RESULTS.json').read_text())
    assert len(calls)==1
    assert result['real_POSTs']==0 and result['mail_sent']==0
    assert result['symbols'][0]['error']==f'FreeSafetyStop:Yahoo_HTTP_{status}_stop_no_retry'
    assert all(row['error']==f'Yahoo_{status}_batch_circuit_open_no_more_requests'
               for row in result['symbols'][1:])


def test_successful_chart_keeps_existing_evidence_format(tmp_path, monkeypatch):
    payload={'chart':{'result':[{'meta':{'symbol':'NVDA'}}]}}
    monkeypatch.setattr(curl.Session, 'request', lambda *a, **k:
                        SimpleNamespace(status_code=200,json=lambda:payload))
    trace=capture.install_capture_transport(tmp_path)
    curl.Session().get('https://query1.finance.yahoo.com/v8/finance/chart/NVDA')
    assert json.loads((tmp_path/trace[0]['response_file']).read_text())==payload
