"""Free-only checks of the accepted business pin and request metadata."""
import datetime
import tempfile
from pathlib import Path

import pytest
from authorized_once import FIXED, LiveSession, with_usage_options
from deepseek_post_guard import GuardStop


def test_business_pin_is_the_accepted_phase2j_commit():
    assert FIXED == 'f93a7609e569e3b6c6372e652a3d36a27225d783'


def test_old_business_authorization_rejected_without_account_or_model_request():
    called = []
    def forbidden_get(*args):
        called.append(True)
        raise AssertionError('must_not_read_account')
    auth = {'authorize_paid_post': True, 'authorization_reference': 'MOCK_ONLY',
            'secret_upload_approval_reference': 'MOCK_ONLY', 'run_id': 'offline',
            'fixed_commit': '578fc55364bf32b7299e84eea7a630eb7e93e973',
            'reservation_usd': '.03',
            'expires_at': (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=1)).isoformat()}
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(GuardStop):
            LiveSession(Path(d), auth, 'offline-sentinel-not-real', 'offline', get=forbidden_get)
    assert not called


def test_usage_metadata_does_not_rewrite_research_or_thinking():
    original = {'stream': True, 'messages': [{'role': 'user', 'content': '离线材料'}], 'max_tokens': 8192}
    result = with_usage_options(original)
    assert result['stream_options'] == {'include_usage': True}
    assert result['messages'] == original['messages'] and result['max_tokens'] == 8192
    assert 'thinking' not in result and 'reasoning_effort' not in result
    assert 'stream_options' not in original
