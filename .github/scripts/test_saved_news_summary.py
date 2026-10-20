import copy
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from saved_news import attach_saved_news_context
from test_saved_news import artifacts, item, ASOF


def test_saved_operator_summary_is_separate_from_publisher_full_text():
    text = 'SYNTHETIC 人工摘要；不是新闻全文。媒体称发生事件，事件日期尚待原始来源核对。'
    entry = item(content_kind='summary', summary_origin='operator_paraphrase',
                 text=text, content_sha256=hashlib.sha256(text.encode()).hexdigest())
    original = artifacts(existing='SYNTHETIC_FINANCIAL_CONTEXT_NOT_RECENT_NEWS')
    before = copy.deepcopy(original)
    prepared = attach_saved_news_context(original, {'SYNTHETIC': [entry]}, ASOF)
    assert len(prepared.enhanced_context['saved_news_audit']['accepted']) == 1
    assert '人工摘要' in prepared.news_context and '不是新闻全文' in prepared.news_context
    assert '已保存正文' not in prepared.news_context
    assert original == before and prepared.fundamental_context == original.fundamental_context


def test_summary_requires_origin_text_valid_hash_and_window():
    good = item(content_kind='summary', summary_origin='operator_paraphrase', text='SYNTHETIC summary')
    bad = [
        dict(good, summary_origin='publisher_full_text'),
        {k:v for k,v in good.items() if k != 'summary_origin'},
        dict(good, text=''),
        dict(good, content_sha256='bad'),
        dict(good, published_at='2026-10-12T18:00:00+00:00'),
    ]
    audit = attach_saved_news_context(artifacts(), {'SYNTHETIC': bad}, ASOF).enhanced_context['saved_news_audit']
    assert not audit['accepted'] and len(audit['rejected']) == len(bad)
