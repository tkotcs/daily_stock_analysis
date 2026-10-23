import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml

from manual_responses_once import completed_response, cost, load_bundle

ROOT = Path(__file__).resolve().parents[2]
BATCH = '3e23087e93c3ad203e1d2ef7ced882261b9c45872fc34d8a37740a4b79ee5223'


@pytest.fixture(autouse=True)
def frozen_test_clock(monkeypatch):
    """Historical contract fixtures use their own date; production keeps real time."""
    import manual_responses_once as sender
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(sender, 'datetime', Clock)


def test_expired_material_still_refused_with_test_clock():
    from manual_responses_once import check_time
    with pytest.raises(ValueError, match='material_expired_or_invalid_no_refresh'):
        check_time(dict(analysis_asof='2026-10-19T10:00:00+00:00',
                        material_expires_at='2026-10-20T10:00:00+00:00'))


def test_real_frozen_request_profile_and_actual_financial_input():
    lock, request, context, profile = load_bundle(ROOT / '.github/frozen/sol-aapl-20261020', BATCH)
    assert lock['max_total_POSTs'] == 1 and lock['reservation_CNY'] == '0.05'
    text = json.dumps(request, ensure_ascii=False)
    assert 'derived_from_ytd_difference' in text and '116996' in text and '82627' in text
    assert '| 归母净利润 |' not in text
    assert 'financial_evidence' in context and profile['api_key_env'] == 'SEEKERX'


def test_truncated_stream_and_duplicate_completion_refused():
    response = dict(status='completed', output=[dict(type='message', content=[dict(type='output_text', text='{}')])])
    event = 'data: ' + json.dumps(dict(type='response.completed', response=response)) + '\n\n'
    assert completed_response(event.encode())[1] == '{}'
    for raw in (b'data: {"type":"response.output_text.delta","delta":"{}"}\n\n',
                b'data: {"type":"response.incomplete"}\n\n', (event + event).encode()):
        with pytest.raises(ValueError):
            completed_response(raw)


def test_upstream_overload_is_explicit_without_copying_provider_message():
    from manual_responses_once import ResponseStreamFailure
    event = dict(type='response.failed', response=dict(
        status='failed', error=dict(code='server_error', type='service_unavailable_error',
                                   message='SYNTHETIC_PRIVATE_PROVIDER_MESSAGE')))
    raw = ('data: ' + json.dumps(event) + '\n\n').encode()
    with pytest.raises(ResponseStreamFailure) as failed:
        completed_response(raw)
    assert str(failed.value) == 'upstream_overloaded_no_retry'
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(failed.value.details)
    assert failed.value.details['automatic_retry'] is False
    assert failed.value.details['output_accepted'] is False


def test_HTTP200_overloaded_stream_preserves_one_attempt_no_output(tmp_path, monkeypatch):
    import httpx
    import manual_responses_once as sender
    calls = []
    key = 'SYNTHETIC_CREDENTIAL'
    raw = ('data: ' + json.dumps(dict(type='response.failed', response=dict(
        error=dict(type='service_unavailable_error', code='server_error',
                   message=key)))) + '\n\n').encode()
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_bytes(self): yield raw
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['transport']._pool._retries == 0
            assert kwargs['follow_redirects'] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, *args, **kwargs):
            calls.append(args)
            return Response()
    monkeypatch.setattr(httpx, 'Client', Client)
    saved = {}
    result = dict(actual_model_POST_attempts=0)
    with pytest.raises(ValueError, match='upstream_overloaded_no_retry'):
        sender.perform_post_once({}, {}, 'https://example.test/responses', key,
                                 tmp_path, result, saved.__setitem__, 'SYNTHETIC_HASH')
    assert len(calls) == 1 and result['actual_model_POST_attempts'] == 1
    assert saved['POST_ATTEMPT.json']['state'] == 'reserved_before_transport_may_be_charged'
    assert saved['PROVIDER_FAILURE.json']['provider_error_type'] == 'service_unavailable_error'
    assert result['HTTP_status'] == 200
    assert not (tmp_path/'MODEL_RAW_TEXT.txt').exists()
    assert key.encode() not in (tmp_path/'RAW_RESPONSE_BODY.bin').read_bytes()


def test_actual_usage_cached_subset_and_reasoning_not_double_charged():
    profile = json.loads((ROOT / '.github/research/gpt-6.1-sol-review-profile.json').read_text('utf-8'))
    usage = dict(input_tokens=1000000, output_tokens=1000000,
                 input_tokens_details=dict(cached_tokens=500000),
                 output_tokens_details=dict(reasoning_tokens=900000))
    assert cost(usage, profile)['estimated_CNY'] == '0.887145'
    assert cost(None, profile)['estimated_CNY'] is None
    usage['input_tokens_details']['cached_tokens'] = 1000001
    assert cost(usage, profile)['status'] == 'unknown_usage'


@pytest.mark.parametrize('failure_kind', ['HTTP', 'wrong_model', 'missing_model'])
def test_real_sender_failure_consumes_one_attempt_and_redacts(tmp_path, monkeypatch, failure_kind):
    import sys
    import subprocess
    import httpx
    import manual_responses_once as sender
    import remote_execution_claim as remote
    key = 'SYNTHETIC_TEST_CREDENTIAL'
    send_batch = 'f1f3e8dbc009e1eb0798bb397147c511cf5f8904f6ef64d7acb365bd26e908c4'
    for name, value in dict(SEEKERX=key, GITHUB_RUN_ATTEMPT='1',
                            GITHUB_REF='refs/heads/deploy/phase2h-request-preparation',
                            GITHUB_ACTOR='owner', GITHUB_REPOSITORY_OWNER='owner',
                            GITHUB_RUN_ID='1234567', GITHUB_SHA='a' * 40,
                            GITHUB_REPOSITORY='owner/repo', GITHUB_TOKEN='SYNTHETIC_GITHUB_KEY',
                            APPROVAL_REF='synthetic approval ' + send_batch,
                            RESEARCH_API_BASE='https://api.sequenceq.com/v1').items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: '577624ad8459871630c690e5760ae504ac6f2b9f\n')
    monkeypatch.setitem(sys.modules, 'src.core.trading_calendar', SimpleNamespace(
        get_effective_trading_date=lambda *a, **k: SimpleNamespace(isoformat=lambda: '2026-10-19')))
    monkeypatch.setattr(remote, 'GitHubAPI', lambda *a: None)
    events = []
    class Claim:
        def __init__(self, *args, **kwargs):
            pass
        def reserve(self, members):
            events.append('reserve')
            return {'fixture': 'test-only'}
        def before_send(self, *args):
            events.append('before_send')
    monkeypatch.setattr(remote, 'RemoteExecutionClaim', Claim)
    class Response:
        status_code = 401 if failure_kind == 'HTTP' else 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_bytes(self):
            if failure_kind == 'HTTP':
                yield ('synthetic error ' + key).encode()
            else:
                response = dict(status='completed', output=[dict(type='message', content=[
                    dict(type='output_text', text=json.dumps(dict(synthetic=key)))])],
                    usage=dict(input_tokens=10, output_tokens=5,
                               input_tokens_details=dict(cached_tokens=0)))
                if failure_kind == 'wrong_model':
                    response['model'] = 'unrequested-SYNTHETIC-model'
                yield ('data: ' + json.dumps(dict(type='response.completed', response=response)) + '\n\n').encode()
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
            assert kwargs['transport']._pool._retries == 0
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def stream(self, method, url, **kwargs):
            events.append('POST')
            assert method == 'POST' and url == 'https://api.sequenceq.com/v1/responses'
            return Response()
    monkeypatch.setattr(httpx, 'Client', Client)
    out = tmp_path / 'out'
    monkeypatch.setattr(sys, 'argv', ['sender', '--bundle', str(ROOT / '.github/frozen/sol-aapl-news-20261020'),
                                    '--source', str(tmp_path), '--out', str(out), '--batch-sha', send_batch])
    with pytest.raises(SystemExit) as stopped:
        sender.main()
    assert stopped.value.code == 1
    assert events == ['reserve', 'before_send', 'POST']
    status = json.loads((out / 'STATUS.json').read_text('utf-8'))
    assert status['actual_model_POST_attempts'] == 1 and status['status'] == 'failed_no_retry'
    assert (out / 'POST_ATTEMPT.json').exists()
    if failure_kind != 'HTTP':
        assert status['reason'] == 'response_model_mismatch_no_retry'
        assert status['usage']['input_tokens'] == 10
        assert status['cost_estimate']['estimated_CNY'] is not None
        assert (out / 'RESPONSE_RESULT.json').exists()
        assert (out / 'MODEL_RAW_TEXT.txt').exists()
        assert not (out / 'REPORT.md').exists()
    assert not any(key.encode() in p.read_bytes() for p in out.iterdir())


@pytest.mark.parametrize('live,branch,owner,expected', [
    (True, 'deploy/phase2h-request-preparation', True, ['sol_aapl_paid']),
    (False, 'deploy/phase2h-request-preparation', True, []),
    (True, 'review/phase2t-hosted-preflight', True, []),
    (True, 'deploy/phase2h-request-preparation', False, []),
])
def test_exact_paid_selector_excludes_all_legacy_paid_jobs(live, branch, owner, expected):
    workflow = yaml.load((ROOT / '.github/workflows/04-nvda-free-preflight.yml').read_text('utf-8'), Loader=yaml.BaseLoader)
    inputs = SimpleNamespace(execute_live=live, mvp_three=True, comparison_modes=False,
                             mvp_universe='single_mode_watchlist', request_sha256=BATCH)
    github = SimpleNamespace(actor='owner' if owner else 'other', repository_owner='owner', ref='refs/heads/' + branch)
    selected = []
    for name, job in workflow['jobs'].items():
        expression = job['if'].removeprefix('${{').removesuffix('}}').strip().replace('&&', 'and').replace('||', 'or').replace('!inputs.', 'not inputs.')
        if eval(expression, {'__builtins__': {}}, dict(inputs=inputs, github=github)):
            selected.append(name)
    assert selected == expected
    assert workflow['jobs']['sol_aapl_paid']['environment'] == 'nvda-one-call-approval'
    assert 'secrets.SEEKERX' in str(workflow['jobs']['sol_aapl_paid'])
