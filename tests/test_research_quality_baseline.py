"""Small, fixed real-response baseline, not a general natural-language validator.

No network/model invocation. Original errors must remain visible after replay.
"""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.analyzer import GeminiAnalyzer
from src.config import Config
from src.notification import NotificationService
from src.trade_plan import calculate_risk_plan, format_risk_plan

FIXTURES = Path(__file__).parent / 'fixtures/mvp_real_three'


def load(symbol, suffix):
    return json.loads((FIXTURES / f'{symbol}_{suffix}.json').read_text('utf-8'))


def analyzer():
    with patch.object(GeminiAnalyzer, '_init_litellm', return_value=None):
        return GeminiAnalyzer(config=Config(stock_list=[]))


def test_nvda_original_ma_error_is_not_silently_repaired():
    context = load('NVDA', 'CONTEXT')
    old = load('NVDA', 'PARSED_MODEL_JSON')
    text = old['dashboard']['data_perspective']['trend_status']['ma_alignment']
    assert 'MA20高于MA10' in text  # known false claim in the real original
    assert context['today']['ma10'] > context['today']['ma20']
    assert 'MA10=230.27 > MA20=228.58' in analyzer()._format_computed_quote_facts(context)


def test_qqq_original_volume_benchmark_error_is_preserved():
    old = load('QQQ', 'PARSED_MODEL_JSON')
    context = load('QQQ', 'CONTEXT')
    prior_multiple = context['today']['volume'] / context['yesterday']['volume']
    assert old['dashboard']['data_perspective']['volume_analysis']['volume_ratio'] == .95
    assert round(prior_multiple, 2) == .95
    assert context['today']['volume_ratio'] == 1.4


def test_qqq_original_universal_stop_does_not_cover_second_entry():
    old = load('QQQ', 'PARSED_MODEL_JSON')['dashboard']['battle_plan']
    assert '720.36' in old['position_strategy']['risk_control']
    rows, cap, errors = calculate_risk_plan(old['risk_plan'])
    assert not errors and cap == 20
    assert rows[1]['stop'] == 705 and rows[1]['entry'] == 720.36
    assert rows[1]['stop'] != rows[0]['stop']
    assert rows[0]['loss_pct'] == pytest.approx((739.57 - 720.36) / 739.57 * 100)
    assert rows[1]['reward_risk'] == pytest.approx((743.06 - 720.36) / (720.36 - 705))


def test_mu_real_watch_requires_no_fabricated_entry():
    plan = load('MU', 'PARSED_MODEL_JSON')['dashboard']['battle_plan']['risk_plan']
    before = copy.deepcopy(plan)
    assert calculate_risk_plan(plan) == ([], 0, [])
    assert '不虚构入场' in format_risk_plan(plan)
    assert plan == before


@pytest.mark.parametrize('symbol', ['NVDA', 'MU', 'QQQ'])
def test_real_close_mislabel_still_requires_editorial_review(symbol):
    old = load(symbol, 'PARSED_MODEL_JSON')
    limitations = old['dashboard']['phase_decision']['data_limitations']
    assert any('盘中' in line and '估算' in line for line in limitations)
    assert '已完成日线收盘价' in analyzer()._format_computed_quote_facts(load(symbol, 'CONTEXT'))


@pytest.mark.parametrize('symbol', ['MU', 'QQQ'])
def test_existing_position_cannot_be_inferred_from_new_exposure_cap(symbol):
    battle = load(symbol, 'PARSED_MODEL_JSON')['dashboard']['battle_plan']
    assert '3成' in battle['position_strategy']['suggested_position']
    assert battle['risk_plan'].get('existing_position_cap_pct') is None
    assert '现有持仓上限未提供' in format_risk_plan(battle['risk_plan'])


@pytest.mark.parametrize('symbol', ['NVDA', 'MU', 'QQQ'])
@pytest.mark.parametrize('language', ['zh', 'en'])
def test_prompt_has_concise_quality_contract(symbol, language):
    prompt = analyzer()._format_prompt(load(symbol, 'CONTEXT'), symbol, report_language=language)
    for term in ('existing_position_cap_pct', '"mode":"watch"', 'volume_ratio'):
        assert term in prompt
    if language == 'zh':
        for term in ('两两比较', '单日快照不能证明均线斜率', '既有仓位上限保持null',
                     '不同入场情景不能共用', '前日成交量倍数另行标注', '推翻判断的新信息'):
            assert term in prompt
        assert '分别说明名义价格损失' not in prompt
    else:
        assert 'pairwise MA comparisons' in prompt
        assert 'not a universal stop' in prompt
        assert 'keep the existing-position cap null' in prompt
        assert 'give nominal price loss' not in prompt


@pytest.mark.parametrize('symbol', ['NVDA', 'MU', 'QQQ'])
def test_native_replay_preserves_model_paragraphs(symbol):
    raw = (FIXTURES / f'{symbol}_MODEL_RAW_TEXT.txt').read_text('utf-8')
    a = analyzer()
    result = a._parse_response(raw, symbol, symbol)
    result.raw_response = raw
    result.report_language = 'zh'
    result.market_snapshot = a._build_market_snapshot(load(symbol, 'CONTEXT'))
    report = NotificationService().generate_single_stock_report(result)
    for field in ('ma_analysis', 'fundamental_analysis', 'volume_analysis'):
        assert load(symbol, 'PARSED_MODEL_JSON')[field] in report
    assert result.raw_response == raw


def test_etf_missing_company_finance_does_not_verify_tracking_error():
    old = load('QQQ', 'PARSED_MODEL_JSON')
    assert '低跟踪误差' in old['company_highlights']
    assert '本次未提供相关数据' in old['fundamental_analysis']
    prompt = analyzer()._format_prompt(load('QQQ', 'CONTEXT'), 'QQQ')
    assert '不得断言未给出的跟踪误差' in prompt
