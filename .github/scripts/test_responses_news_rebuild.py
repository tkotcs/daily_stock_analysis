import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manual_responses_candidate import rebuild_with_saved_news, build_request, qualify_us_market_rules

ROOT = Path(__file__).resolve().parents[2]
ASOF = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)


def inputs():
    base = ROOT / '.github/frozen/sol-aapl-20261020'
    request, context, profile = [json.loads((base / name).read_text('utf-8')) for name in
                                 ('REQUEST.json', 'CONTEXT.json', 'PROFILE.json')]
    report = context['fundamental_context']['earnings']['data']['financial_report']
    audit = dict(fields={key: dict(classification='quarterly_Yahoo_not_officially_verified',
                actual_series_period='2026-06-30', value=report.get(key),
                source_url='https://example.test/SYNTHETIC-vendor-financial')
                for key in ('revenue', 'net_profit_parent', 'operating_cash_flow')})
    entry = dict(source='SYNTHETIC single media source', url='https://example.test/article',
                 title='SYNTHETIC_RECENT_ARTICLE', published_at='2026-10-19T16:05:07+00:00',
                 fetched_at='2026-10-20T09:00:00+00:00', content_kind='summary',
                 summary_origin='operator_paraphrase',
                 text='SYNTHETIC operator summary; media claim only, event effective time not proven.')
    return dict(messages=request['input']), context, profile, audit, {'AAPL': [entry]}


def test_native_news_rebuild_replaces_missing_news_and_preserves_financial_and_system():
    chat, context, profile, audit, packet = inputs()
    before = copy.deepcopy((chat, context, audit, packet))
    updated, new_chat = rebuild_with_saved_news(
        chat, context, packet, ASOF, Path(os.environ['DSA_FIXED_SOURCE']), audit)
    result = build_request(new_chat, profile, context=updated)
    text = '\n'.join(m['content'] for m in result['input'])
    assert 'SYNTHETIC_RECENT_ARTICLE' in text and '人工摘要' in text
    assert '不是新闻全文' in text and '不代表综合新闻覆盖' in text
    assert '本次未提供可用新闻证据' not in text
    assert 'derived_from_ytd_difference' in text and '116996' in text and '82627' in text
    assert '| 2026-10-19 |' in text and '| 2026-10-16 |' in text
    assert '| 归母净利润 |' not in text
    assert updated['today'] == context['today']
    assert updated['fundamental_context'] == context['fundamental_context']
    assert updated['financial_evidence'] == context['financial_evidence']
    assert updated['saved_news_audit']['search_performed'] is False
    assert len(updated['saved_news_audit']['accepted']) == 1
    assert [m for m in result['input'] if m['role'] != 'user'] == [
        m for m in qualify_us_market_rules(chat)['messages'] if m['role'] != 'user']
    assert (chat, context, audit, packet) == before


def test_rebuild_refuses_empty_or_invalid_news_before_a_new_request():
    chat, context, _, audit, packet = inputs()
    source = Path(os.environ['DSA_FIXED_SOURCE'])
    for rejected in ({'AAPL': []}, {'AAPL': [dict(packet['AAPL'][0], published_at='2026-09-01T00:00:00Z')]}):
        with pytest.raises(ValueError, match='at_least_one_accepted'):
            rebuild_with_saved_news(chat, context, rejected, ASOF, source, audit)
