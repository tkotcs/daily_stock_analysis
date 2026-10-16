"""Targeted replay: raw responses remain read-only; no model requests."""
import copy,json,hashlib
from pathlib import Path
from unittest.mock import patch
import pytest
from src.analyzer import GeminiAnalyzer,_phase_aware_quote_labels
from src.config import Config
from src.notification import NotificationService
from src.trade_plan import calculate_risk_plan,format_risk_plan,is_watch_plan
F=Path(__file__).parent/'fixtures/mvp_real_three'
def ctx(c='NVDA'):return json.loads((F/(c+'_CONTEXT.json')).read_text('utf-8'))
def data(c):return json.loads((F/(c+'_PARSED_MODEL_JSON.json')).read_text('utf-8'))
def analyzer():
 with patch.object(GeminiAnalyzer,'_init_litellm',return_value=None):return GeminiAnalyzer(config=Config(stock_list=[]))
@pytest.mark.parametrize('c',['NVDA','MU','QQQ'])
def test_close_labels(c):
 x=ctx(c);assert _phase_aware_quote_labels(x)==('上一完整交易日行情','上一完整交易日收盘价')
 x['today']['is_partial_bar']=True;assert _phase_aware_quote_labels(x)[1]=='盘中估算价'
@pytest.mark.parametrize('c',['NVDA','MU','QQQ'])
def test_pairs_and_volume(c):
 x=ctx(c);before=copy.deepcopy(x);text=GeminiAnalyzer._format_computed_quote_facts(x)
 for a,b in [(5,10),(5,20),(5,60),(10,20),(10,60),(20,60)]:
  u,v=x['today']['ma'+str(a)],x['today']['ma'+str(b)];op='>' if u>v else '<' if u<v else '='
  assert f'MA{a}={u:g} {op} MA{b}={v:g}' in text
 ratio=x['today']['volume']/x['yesterday']['volume'];assert f'volume / previous_session_volume = {ratio:.4f}' in text
 assert f"daily volume_ratio = {x['today']['volume_ratio']:g}" in text
 assert 'shift 1' in text and '不是运行时的盘中估算价' in text and x==before
@pytest.mark.parametrize('c',['NVDA','MU'])
def test_finance_provenance(c):
 x=ctx(c);t=GeminiAnalyzer._format_computed_quote_facts(x);f=x['fundamental_context']['earnings']['data']['financial_report']
 assert f['report_date'] in t and 'financial currency=USD' in t and 'yfinance' in t
@pytest.mark.parametrize('p',[{'mode':'watch','max_position_pct':0,'existing_position_cap_pct':None,'scenarios':[]},data('MU')['dashboard']['battle_plan']['risk_plan']])
def test_observe_plan(p):
 before=copy.deepcopy(p);assert is_watch_plan(p) and calculate_risk_plan(p)==([],0,[])
 t=format_risk_plan(p);assert '观望' in t and '不虚构' in t and '现有持仓上限未提供' in t and p==before
@pytest.mark.parametrize('v',[False,-1,True,101])
def test_bad_existing_cap(v):assert calculate_risk_plan({'mode':'watch','max_position_pct':0,'scenarios':[],'existing_position_cap_pct':v})[2]
def test_watch_numeric_exposure_rejected():assert calculate_risk_plan({'mode':'watch','max_position_pct':0,'scenarios':[{'entry':100,'stop':95,'target':110,'position_pct':1}]})[2]
def test_no_plan_no_fake_price():assert '不虚构' in format_risk_plan(None)
def test_separate_caps():
 t=format_risk_plan({'mode':'watch','max_position_pct':0,'existing_position_cap_pct':30,'scenarios':[]});assert '新增仓位上限0%' in t and '现有持仓上限：30%' in t
@pytest.mark.parametrize('c',['NVDA','MU','QQQ'])
def test_original_replay(c):
 a=analyzer();raw=(F/(c+'_MODEL_RAW_TEXT.txt')).read_text('utf-8');r=a._parse_response(raw,c,c);r.raw_response=raw;r.report_language='zh';r.market_snapshot=a._build_market_snapshot(ctx(c))
 assert r.success;text=NotificationService().generate_single_stock_report(r)
 assert 'volume / previous_session_volume' in text and 'daily volume_ratio' in text and r.raw_response==raw
 for k in ('ma_analysis','short_term_outlook','volume_analysis','fundamental_analysis'):assert data(c)[k] in text
 if c=='MU':assert '观望：新增仓位上限0%' in text and 'scenario_1:numeric_value_required' not in text
 if c=='NVDA':assert 'MA20(228.58) ≥ MA10' in raw
@pytest.mark.parametrize('lang',['zh','en'])
def test_prompt_contract(lang):
 t=analyzer()._format_prompt(ctx(),'NVDA',report_language=lang);assert 'existing_position_cap_pct' in t and '"mode":"watch"' in t and 'Yahoo' in t
