import ast
import __future__
import copy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nvda_research_materials import attach_reviewed_materials, format_dividend_announcements


ASOF = datetime(2026, 10, 19, 1, tzinfo=timezone.utc)


def announcement(**changes):
    return dict(dict(source='SYNTHETIC issuer', source_url='https://example.test/dividend',
                     announcement_date='2026-09-15', fetched_at='2026-10-19T00:00:00+00:00',
                     ex_dividend_date='2026-11-19', record_date='2026-11-19',
                     payable_date='2026-12-10', cash_dividend_per_share=0.98, currency='USD'), **changes)


def artifacts():
    from src.services.analysis_context_builder import PipelineAnalysisArtifacts
    fundamental = dict(status='partial', earnings=dict(status='partial', data=dict(
        financial_report=dict(revenue=123, report_date='2026-06-30', currency='USD'),
        dividend=dict(events=[dict(ex_dividend_date='2026-08-20', cash_dividend_per_share=0.91)],
                      ttm_cash_dividend_per_share=3.64, ttm_event_count=4, ttm_dividend_yield_pct=0.688))))
    context = dict(code='SYNTHETIC', stock_name='SYNTHETIC', date='2026-10-16',
                   today=dict(close=100, ma5=100, ma10=100, ma20=100, ma60=100),
                   fundamental_context=fundamental)
    return PipelineAnalysisArtifacts(code='SYNTHETIC', stock_name='SYNTHETIC', market='us', phase=None,
                                     base_context={}, enhanced_context=context, realtime_quote=None,
                                     trend_result=None, chip_data=None, fundamental_context=fundamental,
                                     news_context=None, news_result_count=None, metadata={})


def test_future_dividends_isolated_and_invalid_items_audited(tmp_path):
    original = artifacts()
    before = copy.deepcopy(original)
    invalid = [
        announcement(ex_dividend_date='2026-10-19'),
        announcement(ex_dividend_date='2026-10-18'),
        announcement(fetched_at='2026-10-19T02:00:00+00:00'),
        announcement(fetched_at='2026-10-19T00:00:00'),
        announcement(announcement_date='2026-10-20'),
        announcement(source_url='https://user:password@example.test/dividend'),
        announcement(source_url='http://example.test/dividend'),
        announcement(cash_dividend_per_share=float('nan')),
        announcement(cash_dividend_per_share=True),
        announcement(currency=None),
        announcement(record_date='2026-11-18'),
        announcement(payable_date='2026-11-18'),
        announcement(announcement_date='2026-09-15T00:00:00Z'),
    ]
    packet = {'SYNTHETIC': dict(dividend_announcements=[announcement(), *invalid])}
    prepared = attach_reviewed_materials(original, packet, ASOF, tmp_path)
    assert original == before
    audit = prepared.enhanced_context['dividend_announcement_audit']
    assert len(audit['accepted']) == 1 and len(audit['rejected']) == len(invalid)
    assert audit['date_comparison_calendar'] == 'UTC'
    data = prepared.fundamental_context['earnings']['data']
    assert data['financial_report'] == before.fundamental_context['earnings']['data']['financial_report']
    assert {key: value for key, value in data['dividend'].items() if key != 'announced_future'} == before.fundamental_context['earnings']['data']['dividend']
    assert prepared.news_context is None and prepared.news_result_count is None
    assert 'official_research' not in prepared.enhanced_context
    assert packet['SYNTHETIC']['dividend_announcements'][0] == announcement()
    with pytest.raises(ValueError, match='timezone'):
        attach_reviewed_materials(original, packet, ASOF.replace(tzinfo=None), tmp_path)


def test_missing_empty_rejected_and_utc_calendar_are_not_no_events(tmp_path):
    original = artifacts()
    for label, packet in (
        ('missing', {}),
        ('empty', {'SYNTHETIC': dict(dividend_announcements=[])}),
        ('rejected', {'SYNTHETIC': dict(dividend_announcements=[announcement(currency='bad')])}),
    ):
        directory = tmp_path / label
        directory.mkdir()
        prepared = attach_reviewed_materials(original, packet, ASOF, directory)
        text = format_dividend_announcements(prepared.enhanced_context)
        assert ('未提供未来公告材料' if label == 'missing' else '不代表不存在未来公告') in text
        assert prepared.fundamental_context == original.fundamental_context
        if label == 'rejected':
            assert 'dividend_currency_required' in text
    prepared = attach_reviewed_materials(original, {'SYNTHETIC': dict(dividend_announcements=[
        announcement(announcement_date='2026-10-18', fetched_at='2026-10-19T08:30:00+08:00')
    ])}, ASOF, tmp_path)
    audit = prepared.enhanced_context['dividend_announcement_audit']
    assert len(audit['accepted']) == 1
    assert audit['accepted'][0]['fetched_at'].endswith('+08:00')
    assert 'UTC日历' in format_dividend_announcements(prepared.enhanced_context)


def test_legacy_financial_release_and_independent_dividend_can_coexist(tmp_path):
    original = artifacts()
    release = dict(available_after='2026-08-01T00:00:00+00:00', fetched_at='2026-10-18T00:00:00+00:00',
                   period_end='2026-06-30', published_date='2026-08-01', currency='USD',
                   source_url='https://example.test/financial', text='SYNTHETIC_FINANCIAL_TEXT',
                   values=dict(revenue=456, net_profit_parent=123, operating_cash_flow=200))
    legacy = attach_reviewed_materials(original, {'SYNTHETIC': release}, ASOF, tmp_path)
    legacy_data = legacy.fundamental_context['earnings']['data']
    assert legacy_data['financial_report']['revenue'] == 456
    assert legacy_data['dividend'] == original.fundamental_context['earnings']['data']['dividend']
    assert legacy.news_context == 'SYNTHETIC_FINANCIAL_TEXT'
    directory = tmp_path / 'combined'
    directory.mkdir()
    combined = attach_reviewed_materials(original, {'SYNTHETIC': dict(release, dividend_announcements=[announcement()])}, ASOF, directory)
    assert combined.fundamental_context['earnings']['data']['financial_report'] == legacy_data['financial_report']
    assert combined.news_context == legacy.news_context
    assert 'dividend_announcements' not in combined.enhanced_context['official_research']
    assert len(combined.enhanced_context['dividend_announcement_audit']['accepted']) == 1


@pytest.mark.parametrize('parent_status', ['not_supported', 'failed', 'partial'])
def test_dividend_evidence_does_not_upgrade_failed_financial_status(tmp_path, parent_status):
    original = artifacts()
    original.fundamental_context['status'] = parent_status
    earnings = original.fundamental_context['earnings']
    earnings.update(status='failed', errors=['SYNTHETIC financial unavailable'], source_chain=['SYNTHETIC failed source'])
    earnings['data'].pop('financial_report')
    before = copy.deepcopy(original)
    prepared = attach_reviewed_materials(original, {'SYNTHETIC': dict(dividend_announcements=[announcement()])}, ASOF, tmp_path)
    assert original == before
    assert prepared.fundamental_context['status'] == parent_status
    result = prepared.fundamental_context['earnings']
    assert result['status'] == 'failed'
    assert result['errors'] == earnings['errors'] and result['source_chain'] == earnings['source_chain']
    assert 'financial_report' not in result['data']
    assert result['data']['dividend']['ttm_cash_dividend_per_share'] == 3.64
    assert len(prepared.enhanced_context['dividend_announcement_audit']['accepted']) == 1
    assert '2026-11-19' in format_dividend_announcements(prepared.enhanced_context)


@pytest.mark.parametrize('with_news', [False, True])
def test_controller_wiring_with_native_pack_body_formatter_and_report(tmp_path, monkeypatch, with_news):
    import src
    from src.analyzer import GeminiAnalyzer
    from src.services.analysis_context_builder import AnalysisContextBuilder
    from src.analysis_context_pack_prompt import format_analysis_context_pack_prompt_section
    from src.analysis_context_pack_overview import render_analysis_context_pack_overview
    from manual_reports import save_full_report
    import mvp_three

    analyzer = object.__new__(GeminiAnalyzer)
    monkeypatch.setattr(analyzer, '_get_skill_prompt_sections', lambda: ('', '', True))
    pipeline = SimpleNamespace(analyzer=analyzer)
    pipeline_path = Path(src.__file__).parent / 'core' / 'pipeline.py'
    native_class = next(node for node in ast.parse(pipeline_path.read_text('utf-8')).body if isinstance(node, ast.ClassDef) and node.name == 'StockAnalysisPipeline')
    native_method = next(node for node in native_class.body if isinstance(node, ast.FunctionDef) and node.name == '_build_analysis_context_pack_outputs')
    native_namespace = dict(AnalysisContextBuilder=AnalysisContextBuilder,
                            format_analysis_context_pack_prompt_section=format_analysis_context_pack_prompt_section,
                            render_analysis_context_pack_overview=render_analysis_context_pack_overview,
                            logger=logging.getLogger(__name__))
    exec(compile(ast.Module(body=[native_method], type_ignores=[]), str(pipeline_path), 'exec', flags=__future__.annotations.compiler_flag), native_namespace)
    pipeline._build_analysis_context_pack_outputs = native_namespace['_build_analysis_context_pack_outputs'].__get__(pipeline)
    packet_path = tmp_path / 'research.json'
    packet_path.write_text(json.dumps({'SYNTHETIC': dict(dividend_announcements=[announcement()])}), encoding='utf-8')
    news_path = None
    if with_news:
        news_path = tmp_path / 'news.json'
        news_path.write_text(json.dumps({'SYNTHETIC': [dict(source='SYNTHETIC news', url='https://example.test/news',
            title='SYNTHETIC_NEWS_SEPARATE', published_at='2026-10-18T00:00:00+00:00',
            fetched_at='2026-10-19T00:00:00+00:00', content_kind='metadata_only')]}), encoding='utf-8')
    run_function = next(node for node in ast.parse(Path(mvp_three.__file__).read_text('utf-8')).body if isinstance(node, ast.FunctionDef) and node.name == 'run_symbol')
    start = next(index for index, node in enumerate(run_function.body) if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'prepared_materials' for target in node.targets))
    namespace = dict(analyzer=analyzer, pipeline=pipeline, research_data=packet_path, news_data=news_path,
                     now=ASOF, out=tmp_path, json=json, save=mvp_three.save)
    exec(compile(ast.Module(body=run_function.body[start:start+2], type_ignores=[]), str(mvp_three.__file__), 'exec'), namespace)
    original = artifacts()
    summary, overview = pipeline._build_analysis_context_pack_outputs(original, report_language='zh', code='SYNTHETIC', query_id='synthetic-dividend')
    prepared = namespace['prepared_materials']['artifacts']
    assert summary and overview
    pack = AnalysisContextBuilder.build(prepared)
    assert pack.subject.code == 'SYNTHETIC'
    if with_news:
        assert 'SYNTHETIC_NEWS_SEPARATE' in prepared.news_context
        assert len(prepared.enhanced_context['saved_news_audit']['accepted']) == 1
    for language in ('zh', 'en'):
        prompt = analyzer._format_prompt(prepared.enhanced_context, 'SYNTHETIC', news_context=prepared.news_context, report_language=language, analysis_context_pack_summary=summary)
        assert '2026-11-19' in prompt and '2026-12-10' in prompt and '0.98' in prompt
        assert ('近12个月每股现金分红 | 3.64' if language == 'zh' else 'TTM Cash Dividend per Share | 3.64') in prompt
        assert ('仅计划支付日' if language == 'zh' else 'planned payment') in prompt
        if with_news:
            assert 'SYNTHETIC_NEWS_SEPARATE' in prompt
    model = dict(analysis_summary='SYNTHETIC model unchanged')
    before = copy.deepcopy(model)
    save_full_report(tmp_path, 'SYNTHETIC', model, prepared.enhanced_context, {}, True)
    facts = json.loads((tmp_path / 'PROGRAM_FACTS.json').read_text('utf-8'))
    assert facts['dividend_announcement_evidence']['accepted'][0]['ex_dividend_date'] == '2026-11-19'
    assert model == before
    assert not (tmp_path / 'FINAL_REQUEST.json').exists()
    assert not (tmp_path / 'REQUEST_IDENTITY.json').exists()
