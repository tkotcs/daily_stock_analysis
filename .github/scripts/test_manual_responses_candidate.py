import copy
import json
from pathlib import Path

import pytest

from manual_responses_candidate import hosted_endpoint, build_request, budget_estimate


def profile():
    return json.loads((Path(__file__).resolve().parents[1] /
                       'research/gpt-6.1-sol-review-profile.json').read_text('utf-8'))


def test_responses_preserves_messages_and_removes_DeepSeek_parameters():
    packet = dict(model='deepseek-flash', thinking={'type': 'disabled'}, max_tokens=16384,
                  temperature=0.7, stream_options={'include_usage': True},
                  messages=[dict(role='system', content='SYNTHETIC system'),
                            dict(role='user', content='SYNTHETIC 财务口径')])
    before = copy.deepcopy(packet)
    request = build_request(packet, profile())
    assert request['model'] == 'gpt-6.1-sol' and request['input'] == packet['messages']
    assert request['reasoning'] == {'effort': 'high'} and request['max_output_tokens'] == 32768
    assert not {'thinking', 'max_tokens', 'temperature', 'stream_options', 'messages'} & set(request)
    assert request['stream'] and request['store'] is False and packet == before


@pytest.mark.parametrize('url', [
    'http://localhost:15721', 'https://localhost:15721', 'https://127.0.0.1/v1',
    'https://[::1]/v1', 'https://192.168.1.1/v1', 'https://user:secret@example.test/v1',
])
def test_hosted_candidate_refuses_local_or_credential_bearing_addresses(url):
    with pytest.raises(ValueError):
        hosted_endpoint(url)


def test_public_base_keeps_supplied_path_without_guessing_host():
    assert hosted_endpoint('https://example.test/custom/v1/') == 'https://example.test/custom/v1/responses'


def test_user_multiplier_matches_reviewed_rates_and_reasoning_not_double_counted():
    p = profile()
    request = build_request(dict(messages=[dict(role='user', content='SYNTHETIC')]), p)
    result = budget_estimate(request, p)
    rates = result['discounted_rates_USD_per_1M']
    assert rates['input'] == '0.071400' and rates['cached_input'] == '0.003570'
    assert rates['output'] == '0.357000'
    assert result['reasoning_tokens_in_output_not_charged_twice']
    assert result['is_bill'] is False and result['is_provider_enforced_cap'] is False
    p['reservation_USD'] = '0.0001'
    with pytest.raises(ValueError, match='reservation_exceeded'):
        budget_estimate(request, p)
