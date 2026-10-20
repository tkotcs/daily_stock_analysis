"""Explicit session references at the final request preparation boundary."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manual_responses_candidate import build_request

ROOT = Path(__file__).resolve().parents[2]


def saved():
    bundle = ROOT / '.github/frozen/sol-aapl-20261020'
    return (json.loads((bundle / name).read_text('utf-8')) for name in
            ('REQUEST.json', 'CONTEXT.json', 'PROFILE.json'))


def test_real_AAPL_request_binds_both_session_dates_and_OHLC():
    request, context, profile = saved()
    chat = dict(messages=request['input'])
    before = copy.deepcopy((chat, context))
    updated = build_request(chat, profile, context=context)
    text = '\n'.join(message['content'] for message in updated['input'])
    assert 'Session date references / 日线日期对照' in text
    assert '| 2026-10-19 |' in text and '| 2026-10-16 |' in text
    assert '| 340.12 | 342.94 |' in text
    assert '| 340.46 | 343.46 |' in text
    assert 'Use the absolute session date' in text
    assert '请写绝对交易日日期' in text
    assert (chat, context) == before
    assert 'derived_from_ytd_difference' in text and '116996' in text and '82627' in text
    assert '净利润（供应商字段，归母归属未独立核验）' in text


def test_session_table_is_shared_and_idempotent():
    from manual_responses_candidate import qualify_session_references
    request, context, profile = saved()
    chat = dict(messages=request['input'])
    prepared = qualify_session_references(context, chat)
    assert qualify_session_references(context, prepared) == prepared
    converted = build_request(prepared, profile, context=context)
    assert '\n'.join(m['content'] for m in converted['input']).count('Session date references / 日线日期对照') == 1


@pytest.mark.parametrize('change', ['same_date', 'reversed', 'target_mismatch', 'NaN_low'])
def test_inconsistent_dates_and_invalid_price_are_rejected(change):
    from manual_responses_candidate import qualify_session_references
    request, context, _ = saved()
    if change == 'same_date':
        context['yesterday']['date'] = context['today']['date']
    elif change == 'reversed':
        context['yesterday']['date'] = '2026-10-20'
    elif change == 'target_mismatch':
        context['date'] = '2026-10-16'
    else:
        context['today']['low'] = float('nan')
    with pytest.raises(ValueError):
        qualify_session_references(context, dict(messages=request['input']))


def test_stale_date_table_is_not_silently_reused():
    from manual_responses_candidate import qualify_session_references
    request, context, _ = saved()
    packet = qualify_session_references(context, dict(messages=request['input']))
    context['today']['low'] = 340.13
    with pytest.raises(ValueError, match='stale_or_ambiguous'):
        qualify_session_references(context, packet)


def test_actual_model_sidecar_renders_dates_and_preserves_both_findings(tmp_path):
    from manual_reports import save_quality_review
    _, context, _ = saved()
    model = dict(pattern_analysis='前日低点340.12美元接近MA10',
                 dashboard=dict(data_perspective=dict(price_position=dict(
                     support_interpretation='340.12美元前日低点与MA10构成观察区域'))))
    before = copy.deepcopy(model)
    review = save_quality_review(tmp_path, 'AAPL', model, context)
    text = (tmp_path / 'QUALITY_REVIEW.md').read_text('utf-8')
    assert '| 2026-10-19 | 346.00 | 340.12 |' in text
    assert '| 2026-10-16 | 347.82 | 340.46 |' in text
    assert len(review['findings']) == 2 and model == before
    assert not review['published'] and not review['quality_accepted']
