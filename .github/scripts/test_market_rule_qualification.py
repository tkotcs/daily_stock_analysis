import copy

from manual_responses_candidate import (
    LEGACY_US_MARKET_RULE, QUALIFIED_US_MARKET_RULE, qualify_us_market_rules,
)


def test_only_known_system_rule_is_corrected_and_original_evidence_is_preserved():
    packet = dict(messages=[
        dict(role='system', content='prefix\n' + LEGACY_US_MARKET_RULE + '\nsuffix'),
        dict(role='user', content='Quoted source text: ' + LEGACY_US_MARKET_RULE),
        dict(role='developer', content='Unrelated instruction'),
    ])
    before = copy.deepcopy(packet)
    result = qualify_us_market_rules(packet)
    assert result['messages'][0]['content'] == 'prefix\n' + QUALIFIED_US_MARKET_RULE + '\nsuffix'
    assert 'T+1' in result['messages'][0]['content'] and 'LULD' in result['messages'][0]['content']
    assert result['messages'][1:] == packet['messages'][1:]
    assert qualify_us_market_rules(result) == result
    assert packet == before
