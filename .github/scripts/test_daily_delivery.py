"""Failure delivery stays deterministic and shares the permanent daily mail claim."""
import json
from pathlib import Path

import pytest
import yaml

import daily_delivery as delivery
import daily_briefing as daily
from test_daily_automatic import automatic_env
from test_daily_briefing import SESSION, SOURCE


def setup(tmp_path, monkeypatch, reason=None):
    automatic_env(tmp_path, monkeypatch)
    monkeypatch.setattr(delivery, 'source_check', lambda *a: None)
    monkeypatch.setattr(delivery, 'trading_day_gate', lambda *a: dict(
        run=True, completed_session=SESSION))
    daily.save(tmp_path/'calendar.json', dict(run=True, completed_session=SESSION))
    daily.save(tmp_path/'SESSION_STATUS.json', dict(run=True, session=SESSION))
    if reason:
        child = tmp_path/'daily-real'
        child.mkdir()
        daily.save(child/'STATUS.json', dict(status='failed_no_retry', reason=reason))


@pytest.mark.parametrize('reason', [None, 'upstream_overloaded_no_retry',
                                    'automatic_confirmed_quality_blocker_no_mail_no_retry'])
@pytest.mark.parametrize('mail_failure', [None, 'claimed', 'timeout'])
def test_data_model_or_quality_failure_sends_notice_once(tmp_path, monkeypatch, reason, mail_failure):
    setup(tmp_path, monkeypatch, reason)
    import remote_execution_claim as remote
    import daily_briefing_mail as mail
    monkeypatch.setattr(mail, 'source_check', lambda *a: None)
    monkeypatch.setattr(remote, 'GitHubAPI', lambda *a: None)
    events = []
    class Claim:
        def __init__(self, api, session_key, *a, **k):
            assert session_key == daily.sha(('DSA:daily-mail:v1:'+SESSION).encode())
        def reserve(self, *a):
            events.append('reserve')
            if mail_failure == 'claimed':
                raise ValueError('already_reserved_no_retry')
            return {}
        def before_send(self, *a): events.append('before_send')
    monkeypatch.setattr(remote, 'RemoteExecutionClaim', Claim)
    daily.source_check(SOURCE)
    import src.notification_sender.email_sender as sender
    def send(self, text, **kwargs):
        events.append('SMTP')
        assert '不是完整研报' in text
        assert kwargs['subject'] == '美股日报运行通知｜'+SESSION
        if mail_failure == 'timeout':
            raise TimeoutError('SYNTHETIC_AMBIGUOUS_SMTP')
        return True
    monkeypatch.setattr(sender.EmailSender, 'send_to_email', send)
    result = delivery.deliver_daily(tmp_path, SOURCE, tmp_path/'mail-result')
    assert result['status'] == ('blocked_before_mail' if mail_failure == 'claimed' else
                                'mail_failed_or_unknown_no_retry' if mail_failure else 'delivered')
    assert result['mail_attempts'] == (0 if mail_failure == 'claimed' else 1)
    assert result['delivery_kind'] == 'service_notice'
    expected = ['reserve'] if mail_failure == 'claimed' else ['reserve', 'before_send', 'SMTP']
    assert events == expected
    with pytest.raises(ValueError, match='mail_state_exists_no_retry'):
        delivery.deliver_daily(tmp_path, SOURCE, tmp_path/'mail-result')
    assert events == expected


@pytest.mark.parametrize('change', ['session', 'holiday', 'prior_run', 'already_claimed'])
def test_notice_rejects_invalid_session_before_sending(tmp_path, monkeypatch, change):
    setup(tmp_path, monkeypatch)
    if change == 'session':
        daily.save(tmp_path/'calendar.json', dict(run=True, completed_session='2000-01-01'))
    elif change == 'holiday':
        monkeypatch.setattr(delivery, 'trading_day_gate', lambda *a: dict(
            run=False, completed_session=SESSION))
    elif change == 'prior_run':
        daily.save(tmp_path/'SESSION_STATUS.json', dict(run=True, session='2000-01-01'))
    else:
        daily.save(tmp_path/'SESSION_STATUS.json', dict(run=False, session=SESSION))
    with pytest.raises(ValueError, match='current_unclaimed_trading_session_required'):
        delivery.deliver_daily(tmp_path, SOURCE, tmp_path/'mail-result')
    assert not (tmp_path/'mail-result').exists()


def test_healthy_report_uses_existing_full_report_validation(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    child = tmp_path/'daily-real'
    child.mkdir()
    daily.save(child/'STATUS.json', dict(status='generated_daily_automatic_validated'))
    (child/'DAILY_REPORT.md').write_text('SYNTHETIC_VALIDATED_REPORT')
    import daily_briefing_mail as mail
    def deliver(report, source, out, digest, **kwargs):
        assert report == child/'DAILY_REPORT.md'
        assert digest == daily.sha(report.read_bytes())
        assert kwargs == dict(send=True, automatic=True)
        return dict(status='delivered')
    monkeypatch.setattr(mail, 'deliver', deliver)
    assert delivery.deliver_daily(tmp_path, SOURCE, tmp_path/'mail-result')['status'] == 'delivered'
    assert not (tmp_path/'daily-notice').exists()


def test_notice_never_copies_private_error_or_unvalidated_model_text(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, 'SYNTHETIC_PRIVATE_ERROR')
    (tmp_path/'daily-real/MODEL_RAW_TEXT.txt').write_text('SYNTHETIC_PRIVATE_MODEL')
    text, _ = delivery.notice_content(tmp_path, SOURCE)
    assert 'PRIVATE' not in text and '不包含投资建议' in text


def test_workflow_delivery_runs_after_failed_generation_but_not_cancelled_or_free():
    root = Path(__file__).resolve().parents[2]
    spec = yaml.load((root/'.github/research/daily-production-workflow.yml').read_text('utf-8'),
                     Loader=yaml.BaseLoader)
    step = next(s for s in spec['jobs']['daily']['steps']
                if s.get('name', '').startswith('Send this run'))
    condition = step['if']
    assert '!cancelled()' in condition and "env.AUTOMATIC_RUN == 'true'" in condition
    assert "steps.session.outputs.run == 'true'" in condition
    assert 'daily_delivery.py' in step['run']
    assert 'continue-on-error' not in json.dumps(spec)


def test_notice_slot_requires_explicit_remote_claim_mode():
    from remote_execution_claim import RemoteExecutionClaim
    from deepseek_post_guard import GuardStop
    args = (None, 'a'*64, '123', 'b'*40)
    with pytest.raises(GuardStop, match='remote_claim_watchlist_invalid'):
        RemoteExecutionClaim(*args, symbols=('DAILY_NOTICE',))
    claim = RemoteExecutionClaim(*args, symbols=('DAILY_NOTICE',), mail_notice=True)
    assert claim.symbols == ('DAILY_NOTICE',)
    with pytest.raises(GuardStop, match='remote_claim_notice_slot_invalid'):
        RemoteExecutionClaim(*args, symbols=('NVDA',), mail_notice=True)


def test_real_notice_claim_prevents_full_report_and_next_model_capture(tmp_path):
    from remote_execution_claim import RemoteExecutionClaim
    from test_remote_execution_claim import DatabaseAPI, initialize
    from daily_session_check import check_session
    from deepseek_post_guard import GuardStop
    database = tmp_path/'claims.sqlite'
    initialize(database)
    api = DatabaseAPI(database)
    batch = daily.sha(('DSA:daily-mail:v1:'+SESSION).encode())
    digest = daily.sha(b'SYNTHETIC_NOTICE')
    notice = RemoteExecutionClaim(api, batch, '123', 'b'*40,
                                  symbols=('DAILY_NOTICE',), mail_notice=True)
    notice.reserve([dict(symbol='DAILY_NOTICE', request_sha256=digest)])
    notice.before_send('DAILY_NOTICE', digest)
    with pytest.raises(GuardStop):
        notice.before_send('DAILY_NOTICE', digest)
    full = RemoteExecutionClaim(api, batch, '124', 'b'*40, symbols=('NVDA',))
    with pytest.raises(GuardStop):
        full.reserve([dict(symbol='NVDA', request_sha256=daily.sha(b'SYNTHETIC_FULL'))])
    assert check_session(SESSION, api)['run'] is False
