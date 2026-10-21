import json

import pytest

import daily_saved_response as saved
from daily_briefing import canonical, sha
from test_daily_automatic import automatic_env
from daily_execution_policy import execution_authority


def test_saved_delivery_cannot_authorize_a_model_call(tmp_path,monkeypatch):
    automatic_env(tmp_path,monkeypatch)
    monkeypatch.setenv('GITHUB_EVENT_NAME','workflow_dispatch')
    (tmp_path/'event.json').write_text(json.dumps(dict(inputs=dict(operation='deliver_saved_daily'))))
    with pytest.raises(ValueError):
        execution_authority(automatic=True)
    assert execution_authority(automatic=True,saved_response=True)['max_model_POSTs']==1


@pytest.mark.parametrize('change',['raw','lock','status','authorization','SMTP','model'])
def test_recovery_refuses_changed_or_uneligible_evidence(tmp_path,monkeypatch,change):
    bundle=tmp_path/'daily-ready';bundle.mkdir()
    generated=tmp_path/'daily-real';generated.mkdir()
    values={
        bundle/'DAILY_LOCK.json':{},
        generated/'STATUS.json':dict(HTTP_status=200,actual_model_POST_attempts=1,
            reason='automatic_confirmed_quality_blocker_no_mail_no_retry',run_id='123'),
        generated/'AUTHORIZATION_USED.json':dict(run_id='123',batch_sha256=sha(canonical({}))),
    }
    for path,value in values.items():
        path.write_bytes(canonical(value))
    raw=generated/'RAW_RESPONSE_BODY.bin';raw.write_bytes(b'SYNTHETIC original')
    manifest=dict(source_run_id='123',batch_sha256=sha((bundle/'DAILY_LOCK.json').read_bytes()),
        raw_response_sha256=sha(raw.read_bytes()),
        source_status_sha256=sha((generated/'STATUS.json').read_bytes()),
        source_authorization_sha256=sha((generated/'AUTHORIZATION_USED.json').read_bytes()))
    pin=tmp_path/'manifest.json';pin.write_bytes(canonical(manifest))
    monkeypatch.setattr(saved,'MANIFEST',pin)
    if change=='SMTP':
        folder=tmp_path/'mail-result';folder.mkdir();(folder/'MAIL_ATTEMPT.json').write_text('{}')
    elif change=='model':
        monkeypatch.setattr(saved,'load_live_bundle',lambda *a:({},dict(model='expected'),{},{},{},{}))
        monkeypatch.setattr(saved,'completed_response',lambda *a:(dict(model='wrong'),'SYNTHETIC'))
    else:
        path={'raw':raw,'lock':bundle/'DAILY_LOCK.json','status':generated/'STATUS.json',
              'authorization':generated/'AUTHORIZATION_USED.json'}[change]
        path.write_bytes(b'changed')
    with pytest.raises(ValueError):
        saved.verified_inputs(tmp_path)
