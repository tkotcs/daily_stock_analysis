"""Native email adapter tests; synthetic credentials and a local SMTP stub only."""
from pathlib import Path

import pytest

import daily_briefing as daily
from daily_briefing_mail import deliver
from test_daily_briefing import SOURCE, github_env


def report(tmp_path):
    folder = tmp_path / 'generated'
    folder.mkdir()
    path = folder / 'DAILY_REPORT.md'
    path.write_text('# SYNTHETIC daily report\n\none consolidated email', 'utf-8')
    daily.save(folder / 'STATUS.json', dict(status='generated_daily_preview_requires_review'))
    daily.save(folder / 'AUTHORIZATION_USED.json',
               dict(focus_symbol='AAPL', target_session='2026-10-19'))
    return path


def test_preview_does_not_claim_or_contact_SMTP(tmp_path, monkeypatch):
    import remote_execution_claim
    monkeypatch.setattr(remote_execution_claim, 'RemoteExecutionClaim',
                        lambda *a, **k: pytest.fail('no claim in mail preview'))
    result = deliver(report(tmp_path), SOURCE, tmp_path / 'preview', '')
    assert result['mail_attempts'] == 0 and result['status'] == 'mail_preview_only'


@pytest.mark.parametrize('missing', ['review', 'Secret', 'wrong_branch', 'recipient_list'])
def test_mail_is_blocked_before_claim_or_SMTP_when_not_reviewed_or_configured(tmp_path, monkeypatch, missing):
    path = report(tmp_path)
    github_env(monkeypatch)
    for key, value in dict(EMAIL_SENDER='synthetic-sender@gmail.com', EMAIL_PASSWORD='SYNTHETIC-password',
                           EMAIL_RECEIVERS='synthetic-receiver@example.test').items():
        monkeypatch.setenv(key, value)
    if missing == 'Secret':
        monkeypatch.delenv('EMAIL_PASSWORD')
    if missing == 'wrong_branch':
        monkeypatch.setenv('GITHUB_REF', 'refs/heads/review/example')
    if missing == 'recipient_list':
        monkeypatch.setenv('EMAIL_RECEIVERS', ', ,')
    import remote_execution_claim
    monkeypatch.setattr(remote_execution_claim, 'RemoteExecutionClaim',
                        lambda *a, **k: pytest.fail('must stop before claim'))
    ref = '' if missing == 'review' else daily.sha(path.read_bytes())
    result = deliver(path, SOURCE, tmp_path / 'mail', ref, send=True)
    assert result['mail_attempts'] == 0 and result['status'] == 'blocked_before_mail'


@pytest.mark.parametrize('ambiguous_send', [False, True])
def test_one_reviewed_email_reuses_native_sender_and_does_not_export_credentials(tmp_path, monkeypatch, ambiguous_send):
    path = report(tmp_path)
    github_env(monkeypatch)
    for key, value in dict(EMAIL_SENDER='synthetic-sender@gmail.com', EMAIL_PASSWORD='SYNTHETIC-password',
                           EMAIL_RECEIVERS='synthetic-receiver@example.test').items():
        monkeypatch.setenv(key, value)
    import remote_execution_claim as remote
    events = []
    class Claim:
        def __init__(self, *a, **k):
            pass
        def reserve(self, members):
            events.append('reserve')
            return {'SYNTHETIC': members}
        def before_send(self, *a):
            events.append('before_send')
    monkeypatch.setattr(remote, 'GitHubAPI', lambda *a: None)
    monkeypatch.setattr(remote, 'RemoteExecutionClaim', Claim)
    daily.source_check(SOURCE)
    import src.notification_sender.email_sender as native_email
    class SMTP:
        def __init__(self, *a, **k):
            assert k['timeout'] == 45
        def starttls(self):
            pass
        def login(self, *a):
            pass
        def send_message(self, message):
            assert message['To'] == 'synthetic-receiver@example.test'
            events.append('send_message')
            if ambiguous_send:
                raise TimeoutError('SYNTHETIC SMTP result unknown')
        def quit(self):
            pass
    monkeypatch.setattr(native_email.smtplib, 'SMTP', SMTP)
    out = tmp_path / 'delivered'
    result = deliver(path, SOURCE, out, daily.sha(path.read_bytes()), send=True)
    assert events == ['reserve', 'before_send', 'send_message']
    assert result['mail_attempts'] == 1
    assert result['status'] == ('mail_failed_or_unknown_no_retry' if ambiguous_send else 'delivered')
    assert not any(b'SYNTHETIC-password' in p.read_bytes() or b'synthetic-receiver@example.test' in p.read_bytes()
                   for p in out.iterdir() if p.is_file())
