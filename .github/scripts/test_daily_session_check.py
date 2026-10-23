import pytest

from daily_session_check import check_session
from deepseek_post_guard import GuardStop


def test_only_absent_claim_allows_capture():
    calls = []
    def api(method, path):
        calls.append((method, path))
        raise GuardStop('remote_claim_HTTP_404_no_retry')
    assert check_session('2026-10-20', api)['run'] is True
    assert len(calls) == 2 and all(call[0] == 'GET' for call in calls)


def test_notice_mail_claim_alone_prevents_later_paid_generation():
    calls = []
    def api(method, path):
        calls.append(path)
        if len(calls) == 1:
            raise GuardStop('remote_claim_HTTP_404_no_retry')
        return {'ref': 'refs/' + path.removeprefix('ref/')}
    assert check_session('2026-10-20', api)['run'] is False
    assert len(calls) == 2


def test_existing_claim_skips_even_if_delivery_is_unknown():
    def api(method, path):
        assert method == 'GET'
        return {'ref': 'refs/' + path.removeprefix('ref/')}
    state = check_session('2026-10-20', api)
    assert state['run'] is False
    assert state['status'] == 'session_reserved_may_be_consumed_no_retry'


@pytest.mark.parametrize('reason', [
    'remote_claim_HTTP_403_no_retry', 'remote_claim_HTTP_500_no_retry',
    'remote_claim_result_unknown_no_retry',
])
def test_unknown_check_never_allows_paid_run(reason):
    def api(*args):
        raise GuardStop(reason)
    with pytest.raises(GuardStop):
        check_session('2026-10-20', api)


def test_malformed_claim_never_allows_paid_run():
    with pytest.raises(ValueError):
        check_session('2026-10-20', lambda *args: {'ref': 'other'})
