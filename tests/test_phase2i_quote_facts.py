"""Small prompt/metadata regression; no model client or network required."""
import copy
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from src.analyzer import GeminiAnalyzer
from src.core.pipeline import StockAnalysisPipeline
from src.stock_analyzer import StockTrendAnalyzer
from data_provider.yfinance_fundamental_adapter import _convert_to_yf_symbol
from src.services.empty_news import empty_news_disclosure


def context(opening=9, close=9, previous=11, ma=10, prior_ma=10):
    return {'code': 'NVDA', 'today': {'date': '2026-10-14', 'open': opening, 'close': close,
                      **{f'ma{p}': ma for p in (5, 10, 20, 60)}},
            'yesterday': {'date': '2026-10-13', 'close': previous,
                          **{f'ma{p}': prior_ma for p in (5, 10, 20, 60)}}}


@pytest.mark.parametrize('opening,expected', [(12, '高开'), (9, '低开'), (11, '平开')])
def test_opening_uses_previous_close(opening, expected):
    assert expected in GeminiAnalyzer._format_computed_quote_facts(context(opening=opening))


@pytest.mark.parametrize('period', [5, 10, 20, 60])
@pytest.mark.parametrize('close,previous,expected', [(9, 11, '本日收盘新下穿'), (11, 9, '本日收盘新上穿'), (9, 9, '本日无新收盘穿越'), (10, 10, '本日无新收盘穿越'), (9, 10, '本日收盘新下穿'), (11, 10, '本日收盘新上穿')])
def test_crossings(period, close, previous, expected):
    text = GeminiAnalyzer._format_computed_quote_facts(context(close=close, previous=previous))
    line = next(x for x in text.splitlines() if f'MA{period}=' in x)
    assert expected in line


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), 0, -1, True])
def test_invalid_ma_stays_unknown(value):
    c = context(ma=value)
    assert 'MA60: 暂无可靠数据' in GeminiAnalyzer._format_computed_quote_facts(c)


@pytest.mark.parametrize('case', ['missing_prior_ma', 'partial', 'same_date', 'missing_session', 'estimated'])
def test_unverified_event_is_never_claimed(case):
    c = context()
    if case == 'missing_prior_ma':
        c['yesterday'].pop('ma60')
    elif case == 'partial':
        c['today']['is_partial_bar'] = True
    elif case == 'estimated':
        c['today']['is_estimated'] = True
    elif case == 'same_date':
        c['yesterday']['date'] = c['today']['date']
    else:
        c['yesterday']['date'] = '2026-10-09'
    line = next(x for x in GeminiAnalyzer._format_computed_quote_facts(c).splitlines() if 'MA60=' in x)
    assert '穿越事件无法核实' in line


def test_inputs_not_mutated():
    c = context(); before = copy.deepcopy(c)
    GeminiAnalyzer._format_computed_quote_facts(c)
    assert c == before


@pytest.mark.parametrize('previous', [None, 0, float('nan')])
def test_gap_missing_prior_close(previous):
    assert '高低开无法核实' in GeminiAnalyzer._format_computed_quote_facts(context(previous=previous))


def test_gap_missing_session_not_treated_as_previous_day():
    c = context(); c['yesterday']['date'] = '2026-10-09'
    assert '高低开无法核实' in GeminiAnalyzer._format_computed_quote_facts(c)


@pytest.mark.parametrize('rows,expected', [(59, False), (60, True), (61, True)])
def test_native_context_ma60_true_window(rows, expected):
    df = pd.DataFrame({'date': pd.date_range('2026-01-01', periods=rows), 'close': range(1, rows + 1)})
    pipeline = SimpleNamespace(db=SimpleNamespace(_analyze_ma_status=lambda _: 'unused'))
    c = StockAnalysisPipeline._build_analysis_context_from_daily_df(pipeline, 'NVDA', df)
    assert ('ma60' in c['today']) is expected
    if expected:
        assert c['today']['ma60'] == pytest.approx(df.close.tail(60).mean())
    assert ('ma60' in c['yesterday']) is (rows >= 61)


@pytest.mark.parametrize('rows', [40, 60])
def test_enhanced_ma60_does_not_expose_legacy_ma20_substitute(rows):
    closes = pd.Series(range(10, rows + 10), dtype=float)
    df = pd.DataFrame({'date': pd.bdate_range('2026-01-01', periods=rows), 'close': closes,
                       'open': closes, 'high': closes + 1, 'low': closes - 1, 'volume': 1000})
    trend = StockTrendAnalyzer().analyze(df, 'NVDA')
    pipeline = SimpleNamespace(config=SimpleNamespace(report_language='zh'), search_service=None)
    c = StockAnalysisPipeline._enhance_context(pipeline, {'code': 'NVDA', 'today': {}}, None, None, trend, fundamental_context={})
    assert ('ma60' in c['today']) is (rows >= 60)
    if rows >= 60:
        assert c['today']['ma60'] == pytest.approx(closes.tail(60).mean())


@pytest.mark.parametrize('symbol,expected', [('BRK.B', 'BRK-B'), ('BRK.A', 'BRK-A'), ('NVDA', 'NVDA'), ('QQQ', 'QQQ'), ('SKHY', 'SKHY'), ('hk00700', '0700.HK'), ('600519.SS', '600519.SS')])
def test_fundamental_alias(symbol, expected):
    assert _convert_to_yf_symbol(symbol) == expected


@pytest.mark.parametrize('has_news', [True, False])
def test_frozen_controller_rss_not_search(has_news):
    scripts = pathlib.Path(__file__).resolve().parents[1] / '.github/scripts'
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location('phase2i_frozen', scripts / 'nvda_frozen_once.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    r = SimpleNamespace(search_performed=True, news_result_count=3, news_evidence_present=False, data_sources='', raw_response='unchanged')
    mod.apply_supplied_news_metadata(r, [], {'selected_news': [{'title': 'fixture'}] if has_news else []})
    assert r.raw_response == 'unchanged'
    assert r.search_performed is False
    assert r.news_result_count is None
    assert r.news_evidence_present is has_news
    assert (empty_news_disclosure(r) is None) is has_news
    assert '综合新闻搜索未执行' in r.data_sources
