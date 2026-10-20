"""Scheduled authorization and delivery tests; synthetic values, no real network."""
import ast
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import daily_briefing as daily
from daily_briefing_mail import deliver
from daily_execution_policy import execution_authority,require_mail_configuration
from test_daily_briefing import SOURCE,SESSION,NOW,PROFILE,fixture_capture,github_env,bundle

ROOT=Path(__file__).resolve().parents[2]
POLICY=json.loads((ROOT/'.github/research/daily-automatic-policy.json').read_bytes())
TEMPLATE=ROOT/'.github/research/daily-production-workflow.yml'


def automatic_env(tmp_path,monkeypatch):
    github_env(monkeypatch)
    event=tmp_path/'event.json'
    daily.save(event,dict(schedule=POLICY['cron_UTC']))
    for key,value in dict(
        GITHUB_REF='refs/heads/main',
        GITHUB_WORKFLOW_REF='owner/repo/.github/workflows/06-daily-consolidated.yml@refs/heads/main',
        GITHUB_EVENT_NAME='schedule',GITHUB_EVENT_PATH=str(event),
        EMAIL_SENDER='synthetic-sender@gmail.com',EMAIL_PASSWORD='SYNTHETIC-password',
        EMAIL_RECEIVERS='synthetic-receiver@example.test').items():
        monkeypatch.setenv(key,value)


@pytest.mark.parametrize('change',[
    'branch','workflow','actor','attempt','event','cron','manual_free','missing_event',
])
def test_automatic_authority_rejects_other_contexts(tmp_path,monkeypatch,change):
    automatic_env(tmp_path,monkeypatch)
    if change=='branch':monkeypatch.setenv('GITHUB_REF','refs/heads/review/example')
    if change=='workflow':monkeypatch.setenv('GITHUB_WORKFLOW_REF','owner/repo/other.yml@refs/heads/main')
    if change=='actor':monkeypatch.setenv('GITHUB_ACTOR','someone_else')
    if change=='attempt':monkeypatch.setenv('GITHUB_RUN_ATTEMPT','2')
    if change=='event':monkeypatch.setenv('GITHUB_EVENT_NAME','pull_request')
    if change=='cron':daily.save(tmp_path/'event.json',dict(schedule='0 * * * *'))
    if change=='manual_free':
        monkeypatch.setenv('GITHUB_EVENT_NAME','workflow_dispatch')
        daily.save(tmp_path/'event.json',dict(inputs=dict(operation='prepare')))
    if change=='missing_event':monkeypatch.setenv('GITHUB_EVENT_PATH',str(tmp_path/'absent.json'))
    with pytest.raises(ValueError):execution_authority(automatic=True)


def test_schedule_and_explicit_manual_production_share_one_user_policy(tmp_path,monkeypatch):
    automatic_env(tmp_path,monkeypatch)
    scheduled=execution_authority(automatic=True)
    monkeypatch.setenv('GITHUB_EVENT_NAME','workflow_dispatch')
    daily.save(tmp_path/'event.json',dict(inputs=dict(operation='run_paid_daily')))
    assert execution_authority(automatic=True)==scheduled
    assert scheduled['human_review_required'] is False
    assert scheduled['reservation_CNY']=='0.05' and scheduled['max_model_POSTs']==1


def test_automatic_bundle_is_explicit_and_does_not_claim_human_review(tmp_path,monkeypatch):
    automatic_env(tmp_path,monkeypatch)
    _,target,_=bundle(tmp_path,automatic=True)
    assert daily.read(target/'DAILY_LOCK.json')['execution_policy_id']==POLICY['id']
    assert daily.read(target/'PREPARATION_STATUS.json')['status']=='ready_for_automatic_generation'


@pytest.mark.parametrize('bad',['EMAIL_SENDER','EMAIL_PASSWORD','EMAIL_RECEIVERS','invalid_receivers'])
def test_missing_or_invalid_mail_setup_blocks_before_bundle_claim_and_POST(tmp_path,monkeypatch,bad):
    automatic_env(tmp_path,monkeypatch)
    if bad=='invalid_receivers':monkeypatch.setenv('EMAIL_RECEIVERS',', ,')
    else:monkeypatch.delenv(bad)
    monkeypatch.setattr(daily,'load_live_bundle',lambda *a:pytest.fail('must stop before live loading'))
    result=daily.generate(tmp_path/'absent','b'*64,SOURCE,tmp_path/'blocked','SYNTHETIC policy',automatic=True)
    assert result['status']=='blocked_before_POST' and result['actual_model_POST_attempts']==0


def automatic_report(tmp_path,monkeypatch):
    automatic_env(tmp_path,monkeypatch)
    folder=tmp_path/'generated';folder.mkdir()
    path=folder/'DAILY_REPORT.md';path.write_text('# SYNTHETIC automatic report','utf-8')
    lock=dict(execution_policy_id=POLICY['id'],analysis_asof=NOW.isoformat(),
              material_expires_at=(NOW+timedelta(hours=1)).isoformat())
    daily.save(folder/'DAILY_LOCK.json',lock)
    daily.save(folder/'STATUS.json',dict(status='generated_daily_automatic_validated',
        program_validation_passed=True,report_sha256=daily.sha(path.read_bytes())))
    daily.save(folder/'AUTHORIZATION_USED.json',dict(focus_symbol='AAPL',target_session=SESSION,
        run_id=os.environ['GITHUB_RUN_ID'],execution_authority=execution_authority(automatic=True),
        batch_sha256=daily.sha((folder/'DAILY_LOCK.json').read_bytes())))
    import manual_responses_once
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(manual_responses_once,'datetime',Clock)
    return path


@pytest.mark.parametrize('change',['report','status','run','authority','lock','expired'])
def test_automatic_mail_requires_this_runs_validated_unchanged_unexpired_report(tmp_path,monkeypatch,change):
    path=automatic_report(tmp_path,monkeypatch)
    if change=='report':path.write_text('SYNTHETIC changed after validation','utf-8')
    name='DAILY_LOCK.json' if change in ('lock','expired') else 'STATUS.json' if change=='status' else 'AUTHORIZATION_USED.json'
    changed=daily.read(path.parent/name)
    if change=='status':changed['program_validation_passed']=False
    if change=='run':changed['run_id']='different_run'
    if change=='authority':changed['execution_authority']={'mode':'manual'}
    if change=='lock':changed['execution_policy_id']='other'
    if change=='expired':changed['material_expires_at']=(NOW-timedelta(seconds=1)).isoformat()
    if change!='report':
        daily.save(path.parent/name,changed)
        if change=='expired':
            auth=daily.read(path.parent/'AUTHORIZATION_USED.json')
            auth['batch_sha256']=daily.sha((path.parent/name).read_bytes())
            daily.save(path.parent/'AUTHORIZATION_USED.json',auth)
    import remote_execution_claim as remote
    monkeypatch.setattr(remote,'RemoteExecutionClaim',lambda *a,**k:pytest.fail('no claim or SMTP'))
    result=deliver(path,SOURCE,tmp_path/'blocked',daily.sha(path.read_bytes()),send=True,automatic=True)
    assert result['status']=='blocked_before_mail' and result['mail_attempts']==0


@pytest.mark.parametrize('ambiguous',[False,True])
def test_automatic_native_SMTP_is_one_attempt_and_never_repaired(tmp_path,monkeypatch,ambiguous):
    path=automatic_report(tmp_path,monkeypatch)
    import remote_execution_claim as remote
    events=[]
    class Claim:
        def __init__(self,*a,**k):pass
        def reserve(self,members):events.append('reserve');return {'fixture':True}
        def before_send(self,*a):events.append('before_send')
    monkeypatch.setattr(remote,'GitHubAPI',lambda *a:None)
    monkeypatch.setattr(remote,'RemoteExecutionClaim',Claim)
    daily.source_check(SOURCE)
    import src.notification_sender.email_sender as native
    class SMTP:
        def __init__(self,*a,**k):assert k['timeout']==45
        def starttls(self):pass
        def login(self,*a):pass
        def quit(self):pass
        def send_message(self,message):
            events.append('SMTP')
            if ambiguous:raise TimeoutError('SYNTHETIC unknown delivery')
    monkeypatch.setattr(native.smtplib,'SMTP',SMTP)
    out=tmp_path/'mail'
    result=deliver(path,SOURCE,out,daily.sha(path.read_bytes()),send=True,automatic=True)
    assert events==['reserve','before_send','SMTP']
    assert result['mail_attempts']==1
    assert result['status']==('mail_failed_or_unknown_no_retry' if ambiguous else 'delivered')
    assert result['execution_authority']['human_review_required'] is False
    assert not any(b'SYNTHETIC-password' in p.read_bytes() or b'synthetic-receiver@example.test' in p.read_bytes()
                   for p in out.iterdir() if p.is_file())


@pytest.mark.parametrize('timestamp,run,session',[
    ('2026-10-21T09:00:00+08:00',True,'2026-10-20'),
    ('2026-10-24T09:00:00+08:00',True,'2026-10-23'),
    ('2026-10-25T09:00:00+08:00',False,'2026-10-23'),
    ('2026-10-26T09:00:00+08:00',False,'2026-10-23'),
    ('2026-12-26T09:00:00+08:00',False,'2026-12-24'),
    ('2026-11-03T09:00:00+08:00',True,'2026-11-02'),
])
def test_beijing_nine_resolves_actual_completed_US_session(timestamp,run,session):
    daily.source_check(SOURCE)
    now=datetime.fromisoformat(timestamp)
    assert now.astimezone(timezone.utc).hour==1
    gate=daily.trading_day_gate(now)
    assert gate['run'] is run and gate['completed_session']==session


def test_production_template_pins_controller_and_fails_before_paid_steps():
    spec=yaml.load(TEMPLATE.read_text('utf-8'),Loader=yaml.BaseLoader)
    assert spec['on']['schedule']==[{'cron':POLICY['cron_UTC']}]
    assert spec['on']['workflow_dispatch']['inputs']['operation']['default']=='check_config'
    job=spec['jobs']['daily']
    assert 'environment' not in job and 'refs/heads/main' in job['if']
    steps=job['steps']
    assert steps[0]['with']['ref']=='__CONTROLLER_COMMIT__'
    preflight=next(i for i,s in enumerate(steps) if s.get('name','').startswith('Check required delivery'))
    generate=next(i for i,s in enumerate(steps) if s.get('name','').startswith('One authorized'))
    email=next(i for i,s in enumerate(steps) if s.get('name','').startswith('Send this run'))
    assert preflight<generate<email
    assert '--automatic' in steps[generate]['run'] and '--automatic' in steps[email]['run']
    assert 'always()' not in steps[email]['if']
    assert not any('continue-on-error' in step for step in steps)
    free=next(s for s in steps if s.get('name','').startswith('Native watchlist capture'))
    assert 'secrets.' not in json.dumps(free)
    assert 'GITHUB_REF' not in job['env']
    for step in steps:
        script=step.get('run','')
        if "python - <<'PY'\n" in script:
            code=script.split("python - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
            ast.parse(code)
