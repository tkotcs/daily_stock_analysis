"""Targeted regressions from Run 39014776142; no model or network calls."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from src.analyzer import GeminiAnalyzer
from src.config import Config
from src.trade_plan import calculate_risk_plan

F = Path(__file__).parent / 'fixtures/quality_live_20261017'


def load(symbol, suffix):
    return json.loads((F / f'{symbol}_{suffix}.json').read_text('utf-8'))


@pytest.mark.parametrize('name', ['SYSTEM_PROMPT', 'LEGACY_DEFAULT_SYSTEM_PROMPT',
                                 'SYSTEM_PROMPT_EN', 'LEGACY_DEFAULT_SYSTEM_PROMPT_EN'])
def test_examples_do_not_force_duplicate_trade_numbers(name):
    text = getattr(GeminiAnalyzer, name)
    for key in ('ideal_buy', 'secondary_buy', 'stop_loss', 'take_profit', 'suggested_position'):
        assert f'"{key}"' in text
    assert 'risk_plan' in text and 'XX' not in text
    assert '无新增交易' in text if not name.endswith('_EN') else 'no new trade' in text


@pytest.mark.parametrize('close,expected', [(709.8, '收盘上方观察线'), (730, '收盘下方观察线'), (720.67, '收盘同价观察线')])
def test_ma60_reference_role_uses_computed_position(close, expected):
    context = load('QQQ', 'CONTEXT')
    context['today'].update(close=close, ma60=720.67)
    before = copy.deepcopy(context)
    text = GeminiAnalyzer._format_computed_quote_facts(context)
    assert expected in text and context == before
    assert '无法核实不等于本日无穿越' in text


def test_english_ma60_role_and_unknown_event_are_separate():
    text = GeminiAnalyzer._format_computed_quote_facts(load('QQQ', 'CONTEXT'), english=True)
    assert 'above-close reference; resistance unconfirmed' in text
    assert 'crossing unverified' in text
    assert 'unverified does not mean no crossing' in text


def test_ma60_missing_is_not_assigned_support():
    context = load('QQQ', 'CONTEXT')
    context['today'].pop('ma60')
    text = GeminiAnalyzer._format_computed_quote_facts(context)
    assert 'MA60: 暂无可靠数据' in text
    assert 'MA60: 收盘上方观察线' not in text


def test_live_raw_qqq_target_conflict_remains_detectable():
    battle = load('QQQ', 'MODEL')['dashboard']['battle_plan']
    assert '情景S1参考731.27' in battle['sniper_points']['take_profit']
    assert battle['risk_plan']['scenarios'][0]['target'] == 742.52
    rows, _, errors = calculate_risk_plan(battle['risk_plan'])
    assert not errors
    assert rows[0]['reward_risk'] == pytest.approx(11.25 / 24.04)


def test_live_mu_blanket_ma_statement_is_not_corrected_in_fixture():
    model = load('MU', 'MODEL')
    context = load('MU', 'CONTEXT')
    assert '短期均线全面位于中长期均线下方' in model['ma_analysis']
    assert context['today']['ma10'] > context['today']['ma60']


def test_non_numeric_watch_stop_passes_existing_integrity_check():
    model = load('NVDA', 'MODEL')
    model['dashboard']['battle_plan']['sniper_points']['stop_loss'] = '不适用（无新增交易）'
    with patch.object(GeminiAnalyzer, '_init_litellm', return_value=None):
        a = GeminiAnalyzer(config=Config(stock_list=[]))
    result = a._parse_response(json.dumps(model, ensure_ascii=False), 'NVDA', 'NVDA')
    valid, missing = a._check_content_integrity(result, require_phase_decision=True)
    assert valid and not missing


@pytest.mark.parametrize('symbol', ['NVDA', 'MU', 'QQQ'])
def test_original_live_json_still_parses_without_mutation(symbol):
    model = load(symbol, 'MODEL')
    before = copy.deepcopy(model)
    with patch.object(GeminiAnalyzer, '_init_litellm', return_value=None):
        a = GeminiAnalyzer(config=Config(stock_list=[]))
    result = a._parse_response(json.dumps(model, ensure_ascii=False), symbol, symbol)
    assert result.success and model == before
