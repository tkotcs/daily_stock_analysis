import copy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sys
import socket
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, os.environ['DSA_FIXED_SOURCE'])
from saved_news import attach_saved_news_context, apply_saved_news_metadata
from free_market_validation import WATCHLIST
from src.services.analysis_context_builder import PipelineAnalysisArtifacts, _build_news_block


ASOF = datetime(2026, 10, 16, 20, tzinfo=timezone.utc)


def artifacts(symbol='SYNTHETIC', existing=None):
    financial = dict(earnings=dict(data=dict(financial_report=dict(revenue=123, report_date='2026-06-30', currency='USD'))))
    context = dict(code=symbol, stock_name=symbol, date='2026-10-16', today={}, fundamental_context=financial)
    return PipelineAnalysisArtifacts(code=symbol, stock_name=symbol, market='us', phase=None, base_context={}, enhanced_context=context, realtime_quote=None, trend_result=None, chip_data=None, fundamental_context=financial, news_context=existing, news_result_count=None, metadata={})


def item(**changes):
    return dict(dict(source='synthetic saved RSS', url='https://example.test/article', title='SYNTHETIC_NEWS_ONLY', published_at='2026-10-16T18:00:00+00:00', fetched_at='2026-10-16T19:00:00+00:00', content_kind='metadata_only'), **changes)


def test_news_preserves_financials_prior_context_and_inputs():
    original = artifacts(existing='SYNTHETIC_REVIEWED_RELEASE')
    before = copy.deepcopy(original)
    packet = {'SYNTHETIC': [item()]}
    packet_before = copy.deepcopy(packet)
    prepared = attach_saved_news_context(original, packet, ASOF)
    assert original == before and packet == packet_before
    assert prepared.fundamental_context == before.fundamental_context
    assert prepared.enhanced_context['fundamental_context'] == before.enhanced_context['fundamental_context']
    assert 'SYNTHETIC_REVIEWED_RELEASE' in prepared.news_context
    assert '不计作本包近三日新闻' in prepared.news_context
    assert prepared.news_result_count is None


def test_reject_cutoff_timestamp_source_and_content_counterexamples():
    invalid = [item(published_at='2026-10-16T21:00:00+00:00'), item(published_at='2026-10-12T18:00:00+00:00'), item(published_at='2026-10-16T18:00:00'), item(fetched_at='2026-10-17T19:00:00+00:00'), item(fetched_at='2026-10-15T19:00:00+00:00'), item(url='http://example.test/article'), item(content_kind='full_text'), item(text='not_metadata'), item(content_kind='unknown')]
    prepared = attach_saved_news_context(artifacts(), {'SYNTHETIC': invalid}, ASOF)
    assert not prepared.enhanced_context['saved_news_audit']['accepted']
    assert len(prepared.enhanced_context['saved_news_audit']['rejected']) == len(invalid)
    assert prepared.news_context is None
    assert _build_news_block(prepared).status.value == 'missing'
    assert '事件风险未知' in prepared.enhanced_context['news_source_note']
    with pytest.raises(ValueError, match='timezone'):
        attach_saved_news_context(artifacts(), {}, ASOF.replace(tzinfo=None))


def test_metadata_and_saved_full_text_have_distinct_evidence():
    body = 'SYNTHETIC_SAVED_BODY'
    digest = hashlib.sha256(body.encode()).hexdigest()
    packet = {'SYNTHETIC': [item(), item(content_kind='full_text', text=body, content_sha256=digest), item(content_kind='full_text', text=body, content_sha256='bad')]}
    prepared = attach_saved_news_context(artifacts(), packet, ASOF)
    assert '未提供新闻全文' in prepared.news_context and body in prepared.news_context
    assert '综合新闻搜索未执行' in prepared.news_context
    audit = prepared.enhanced_context['saved_news_audit']
    assert len(audit['accepted']) == 2 and len(audit['rejected']) == 1
    assert audit['accepted'][0]['content_sha256'] is None
    assert audit['accepted'][1]['content_sha256'] == digest
    assert audit['search_performed'] is False and prepared.news_result_count is None


def test_35_symbols_reach_native_pack_and_prompt_without_dispatch(monkeypatch, tmp_path):
    monkeypatch.setenv('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
    monkeypatch.setenv('ENV_FILE', str(tmp_path / 'nonexistent.env'))
    def deny_network(*args, **kwargs):
        raise AssertionError('offline_news_test_network_forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny_network)
    monkeypatch.setattr(socket, 'create_connection', deny_network)
    from src.analyzer import GeminiAnalyzer
    from src.services.analysis_context_builder import AnalysisContextBuilder
    from src.analysis_context_pack_prompt import format_analysis_context_pack_prompt_section
    analyzer = object.__new__(GeminiAnalyzer)
    monkeypatch.setattr(analyzer, '_get_skill_prompt_sections', lambda: ('', '', True))
    for symbol in WATCHLIST:
        prepared = attach_saved_news_context(artifacts(symbol), {symbol: [item()]}, ASOF)
        pack = AnalysisContextBuilder.build(prepared)
        summary = format_analysis_context_pack_prompt_section(pack, report_language='zh')
        prompt = analyzer._format_prompt(prepared.enhanced_context, symbol, news_context=prepared.news_context, analysis_context_pack_summary=summary)
        assert 'SYNTHETIC_NEWS_ONLY' in pack.blocks['news'].items['content'].value
        assert pack.blocks['news'].status.value == 'available'
        assert 'SYNTHETIC_NEWS_ONLY' not in summary and 'SYNTHETIC_NEWS_ONLY' in prompt
        assert pack.subject.code == symbol and prepared.news_result_count is None
        assert 'news_result_count' not in _build_news_block(prepared).metadata


def test_future_report_metadata_preserves_model_and_legacy_path(tmp_path):
    from manual_reports import save_full_report
    prepared = attach_saved_news_context(artifacts(), {'SYNTHETIC': [item()]}, ASOF)
    parsed = SimpleNamespace(raw_response='original model bytes', data_sources='original model source label')
    apply_saved_news_metadata(parsed, prepared.enhanced_context)
    assert parsed.raw_response == 'original model bytes'
    assert parsed.search_performed is False and parsed.news_result_count is None
    assert parsed.news_evidence_present is True and '未执行' in parsed.data_sources
    legacy = SimpleNamespace(data_sources='legacy unchanged')
    apply_saved_news_metadata(legacy, {})
    assert vars(legacy) == dict(data_sources='legacy unchanged')
    model = dict(analysis_summary='synthetic original model')
    before = copy.deepcopy(model)
    save_full_report(tmp_path, 'SYNTHETIC', model, prepared.enhanced_context, {}, True)
    import json
    facts = json.loads((tmp_path / 'PROGRAM_FACTS.json').read_text('utf-8'))
    assert facts['saved_news_evidence']['search_performed'] is False
    assert model == before


def test_synthetic_fixture_discloses_supplied_evidence_without_claiming_research():
    from mvp_three import fixture
    prepared = attach_saved_news_context(artifacts(), {'SYNTHETIC': [item()]}, ASOF)
    prepared.enhanced_context['today']['close'] = 100
    result = fixture('SYNTHETIC', prepared.enhanced_context)
    assert result['news_summary'] == prepared.enhanced_context['news_source_note']
    assert '综合新闻搜索未执行' in result['news_summary']
    assert '模拟' in result['analysis_summary']
