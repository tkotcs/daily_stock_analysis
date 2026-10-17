"""Small, source-backed quality checks; no paid or network requests."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from src.analyzer import GeminiAnalyzer
from src.config import Config
from src.core.pipeline import StockAnalysisPipeline
from src.notification import NotificationService
from src.stock_analyzer import TrendAnalysisResult
from src.trade_plan import format_risk_plan

ROOT = Path(__file__).parents[1]
FIX = ROOT/'tests/fixtures/quality_live_20261017'
PACK = json.loads((ROOT/'.github/research/official-three-20261017.json').read_text('utf-8'))
spec = importlib.util.spec_from_file_location('quality_materials', ROOT/'.github/scripts/nvda_research_materials.py')
materials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materials)


def ctx(symbol='MU'):
    return json.loads((FIX/(symbol+'_CONTEXT.json')).read_text('utf-8'))


@pytest.mark.parametrize('rsi,state', [(0,'超卖'),(29.99,'超卖'),(30,'未达到超卖'),(31.3,'未达到超卖'),(70,'未达到超卖'),(70.01,'超买')])
def test_rsi_uses_native_thresholds_including_boundaries(rsi,state):
    c = ctx(); c['trend_analysis']['rsi_12'] = rsi
    text = GeminiAnalyzer._format_computed_quote_facts(c)
    line = next(s for s in text.splitlines() if s.startswith('RSI(12)='))
    assert state in line and 'RSI<30 / RSI>70' in line


@pytest.mark.parametrize('rsi', [None, True, float('nan'), -1, 101])
def test_unknown_rsi_does_not_gain_a_status(rsi):
    c = ctx(); c['trend_analysis']['rsi_12'] = rsi
    assert 'RSI(12)=' not in GeminiAnalyzer._format_computed_quote_facts(c)


def test_numeric_order_excludes_missing_and_nonsense():
    c = ctx()
    text = GeminiAnalyzer._format_computed_quote_facts(c)
    line = next(s for s in text.splitlines() if s.startswith('均线按数值升序'))
    assert line.index('MA5=') < line.index('MA60=') < line.index('MA10=') < line.index('MA20=')
    assert '无' not in line and 'None' not in line
    c['today']['ma60'] = None
    assert 'MA60=' not in next(s for s in GeminiAnalyzer._format_computed_quote_facts(c).splitlines() if s.startswith('均线按数值升序'))


def test_native_builder_can_supply_previous_ma60_without_ma20_substitution():
    df = pd.DataFrame({'date':pd.bdate_range('2026-07-17',periods=64),'close':list(range(100,164))})
    pipeline = SimpleNamespace(db=SimpleNamespace(_analyze_ma_status=lambda row: 'not tested here'))
    context = StockAnalysisPipeline._build_analysis_context_from_daily_df(pipeline,'QQQ',df)
    assert context['today']['ma60'] == pytest.approx(df.close.iloc[-60:].mean())
    assert context['yesterday']['ma60'] == pytest.approx(df.close.iloc[-61:-1].mean())


def test_pipeline_passes_actual_rsi_to_native_prompt():
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.config = SimpleNamespace(report_language='zh')
    pipeline.search_service = SimpleNamespace(news_window_days=3)
    result = TrendAnalysisResult(code='MU',data_points=64,rsi_12=31.3)
    enhanced = pipeline._enhance_context(ctx(),None,None,result,fundamental_context={})
    assert enhanced['trend_analysis']['rsi_12'] == 31.3


@pytest.mark.parametrize('symbol', ['NVDA','MU'])
def test_official_quarter_replaces_whole_block_with_provenance(symbol,tmp_path):
    before = ctx(symbol); original = copy.deepcopy(before)
    updated, text = materials.attach_reviewed_release(before,PACK,dt.datetime(2026,10,17,8,30,tzinfo=dt.timezone.utc),tmp_path)
    fin = updated['fundamental_context']['earnings']['data']['financial_report']
    assert fin['report_date'] == PACK[symbol]['period_end']
    assert fin['operating_cash_flow'] == PACK[symbol]['values']['operating_cash_flow']
    assert fin['source'] == PACK[symbol]['source_url'] and 'GAAP' in text
    assert before == original and updated['official_research']['publication_time_exact'] is None
    assert '已附公司公告证据' in GeminiAnalyzer._format_computed_quote_facts(updated)
    with patch.object(GeminiAnalyzer,'_init_litellm',return_value=None):a=GeminiAnalyzer(config=Config(stock_list=[]))
    prompt = a._format_prompt(updated,symbol,news_context=text,analysis_context_pack_summary=None)
    assert PACK[symbol]['period_end'] in prompt and PACK[symbol]['source_url'] in prompt


def test_future_official_data_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='not_available_at_cutoff'):
        materials.attach_reviewed_release(ctx(),PACK,dt.datetime(2026,9,29,tzinfo=dt.timezone.utc),tmp_path)


def test_etf_never_receives_enterprise_financial_fields(tmp_path):
    c = ctx('QQQ'); d, text = materials.attach_reviewed_release(c,PACK,dt.datetime.now(dt.timezone.utc),tmp_path)
    assert d is c and text is None


def test_quarter_cash_flow_does_not_use_annual_or_half_year():
    assert PACK['NVDA']['values']['operating_cash_flow'] == 24077e6
    assert PACK['MU']['values']['operating_cash_flow'] == 43973e6
    assert PACK['MU']['period_end'] == '2026-09-03'
    assert '全年经营现金流896.75亿美元不是本季' in PACK['MU']['text']


def test_real_qqq_trade_prose_comes_from_same_structured_rows():
    model = json.loads((FIX/'QQQ_MODEL.json').read_text('utf-8')); original = copy.deepcopy(model)
    summary = format_risk_plan(model['dashboard']['battle_plan']['risk_plan'])
    assert 'S1：假设入场731.27，止损707.23，目标742.52' in summary
    assert '收益风险比0.468' in summary and model == original
    assert '情景S1参考731.27' in model['dashboard']['battle_plan']['sniper_points']['take_profit']
    with patch.object(GeminiAnalyzer,'_init_litellm',return_value=None):a=GeminiAnalyzer(config=Config(stock_list=[]))
    result = a._parse_response(json.dumps(model,ensure_ascii=False),'QQQ','QQQ')
    report = NotificationService().generate_single_stock_report(result)
    assert '程序依据risk_plan生成的情景摘要（非模型原文）' in report
    assert '目标742.52' in report and '情景S1参考731.27' not in report


def test_watch_does_not_invent_entry_for_summary():
    summary = format_risk_plan({'mode':'watch','max_position_pct':0,'existing_position_cap_pct':None,'scenarios':[]})
    assert '观望' in summary and '假设入场' not in summary and 'S1' not in summary
