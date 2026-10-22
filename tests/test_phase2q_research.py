"""Native research arithmetic, fixed real response replay and long-field coverage."""
import copy
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.analyzer import GeminiAnalyzer
from src.config import Config
from src.notification import NotificationService
from src.trade_plan import calculate_risk_plan, format_risk_plan

FIXTURES = Path(__file__).parent / 'fixtures/phase2p'


def plan(entry=219.6, stop=219, target=228.69, cap=20, position=10):
    return {'max_position_pct': cap, 'scenarios': [dict(entry=entry, stop=stop,
            target=target, position_pct=position, trigger='收盘及量能条件', invalidation='失守假设') ]}


def analyzer():
    with patch.object(GeminiAnalyzer, '_init_litellm', return_value=None):
        return GeminiAnalyzer(config=Config(stock_list=[]))


def real_result():
    raw = (FIXTURES / 'MODEL_RAW_TEXT.txt').read_text(encoding='utf-8')
    a = analyzer()
    r = a._parse_response(raw, 'NVDA', '英伟达')
    r.raw_response = raw
    r.report_language = 'zh'
    c = json.loads((FIXTURES / 'ORIGINAL_ENHANCED_CONTEXT.json').read_text(encoding='utf-8'))[0]
    r.market_snapshot = a._build_market_snapshot(c)
    return a, r, c


@pytest.mark.parametrize('entry,stop,expected', [(219.6,219,.273224), (221,219,.904977),
                         (221.3,219,1.039313), (227.2,219.63,3.331866)])
def test_real_known_arithmetic(entry, stop, expected):
    rows, _, errors = calculate_risk_plan(plan(entry, stop, target=None))
    assert not errors and rows[0]['loss_pct'] == pytest.approx(expected, abs=.000001)


def test_reward_risk_and_input_immutable():
    p = plan(100, 95, 110); original = copy.deepcopy(p)
    rows, cap, errors = calculate_risk_plan(p)
    assert not errors and cap == 20 and rows[0]['loss_pct'] == 5 and rows[0]['reward_risk'] == 2
    assert p == original


@pytest.mark.parametrize('entry,stop,target,cap,position', [
    (0,95,110,20,10), (100,100,110,20,10), (100,105,110,20,10),
    (100,95,90,20,10), (True,95,110,20,10), ('100',95,110,20,10),
    (float('nan'),95,110,20,10), (100,95,float('inf'),20,10),
    (100,95,110,101,10), (100,95,110,20,30), (100,95,110,-1,0),
    (100,95,110,20,-1), (100,95,110,20,True)])
def test_invalid_numbers_fail_closed(entry,stop,target,cap,position):
    rows, _, errors = calculate_risk_plan(plan(entry,stop,target,cap,position))
    assert not rows and errors


@pytest.mark.parametrize('value', [None, {}, [], {'max_position_pct':20,'scenarios':[]},
                                 {'max_position_pct':20,'scenarios':[None]}])
def test_missing_plan_is_not_inferred(value):
    assert calculate_risk_plan(value)[2]


def test_one_bad_scenario_blocks_all_rows():
    p=plan(); p['scenarios'].append(dict(entry=0))
    assert calculate_risk_plan(p)[0] == []


def test_conditions_required_and_table_escaped():
    p=plan(); p['scenarios'][0]['trigger']=''
    assert calculate_risk_plan(p)[2]
    p['scenarios'][0]['trigger']='a|b\nc'
    assert 'a\\|b c' in format_risk_plan(p)


def test_real_ma_states_and_events():
    _,r,c=real_result()
    facts=r.market_snapshot['computed_quote_facts']
    assert '低开' in facts
    for n in (5,10):
        line=next(x for x in facts.splitlines() if f'MA{n}=' in x)
        assert '低于' in line and '本日无新收盘穿越' in line
    assert '本日收盘新下穿' in next(x for x in facts.splitlines() if 'MA20=' in x)
    assert '高于' in next(x for x in facts.splitlines() if 'MA60=' in x)
    assert c['today']['close'] == pytest.approx(221.3000030517578)


def test_historical_response_stays_unapproved_and_unmodified():
    _,r,_=real_result(); original=r.raw_response
    assert '1.5%–2.5%' in original
    assert calculate_risk_plan(r.dashboard['battle_plan'].get('risk_plan'))[2]
    text=NotificationService().generate_single_stock_report(r)
    assert '未经确定性风险核验' in text
    assert r.raw_response == original


@pytest.mark.parametrize('session,unverified', [('2026-10-15',False),('2026-10-14',True),(None,True)])
def test_intraday_partial_flag_belongs_to_its_own_session(session,unverified):
    a,_,c=real_result()
    c['market_phase_context']['session_date']=session
    text=a._format_computed_quote_facts(c)
    line=next(x for x in text.splitlines() if 'MA20=' in x)
    assert ('穿越事件无法核实' in line) is unverified


@pytest.mark.parametrize('method', ['generate_single_stock_report','generate_dashboard_report','generate_daily_report'])
def test_structured_risk_one_position_source(method):
    _,r,_=real_result(); original=r.raw_response
    r.dashboard['battle_plan']['risk_plan']=plan()
    svc=NotificationService()
    text=getattr(svc, method)(r if method=='generate_single_stock_report' else [r])
    assert '统一仓位上限20%' in text and '0.273' in text
    assert '1.5%–2.5%' not in text and '再加至2–3成' not in text
    assert r.raw_response == original


@pytest.mark.parametrize('method', ['generate_single_stock_report','generate_dashboard_report'])
def test_conflicting_position_plan_does_not_render_as_valid(method):
    _,r,_=real_result();r.dashboard['battle_plan']['risk_plan']=plan(position=30)
    svc=NotificationService();text=getattr(svc,method)(r if method=='generate_single_stock_report' else [r])
    assert 'position_exceeds_shared_cap' in text and '1.5%–2.5%' not in text


def test_long_valid_json_parser_and_render_no_clipping():
    a,r,_=real_result()
    payload=json.loads(r.raw_response.strip().removeprefix('```json').removesuffix('```'))
    body='离线长字段解析与渲染样本。'*4000+'END_OF_LONG_FIELD'
    payload['dashboard']['intelligence']['earnings_outlook']=body
    payload['dashboard']['intelligence']['risk_alerts']=[body+'RISK_END']*5
    payload['dashboard']['intelligence']['positive_catalysts']=[body+'CAT_END']*5
    parsed=a._parse_response(json.dumps(payload,ensure_ascii=False),'NVDA','英伟达')
    parsed.report_language='zh'
    assert parsed.success
    text=NotificationService().generate_single_stock_report(parsed)
    assert body in text and text.count('RISK_END')==5 and text.count('CAT_END')==5


@pytest.mark.parametrize('language', ['zh','en'])
def test_prompt_depth_without_removing_original_schema(language):
    a,_,c=real_result();text=a._format_prompt(c,'NVIDIA',report_language=language)
    assert 'risk_plan' in text and 'max_position_pct' in text and '5000' in text
    assert 'entry' in text and 'invalidation' in text
    assert '收盘' in text if language=='zh' else 'closing' in text


def test_new_research_config_default():
    assert Config(stock_list=[]).stock_analysis_max_tokens == 16384


@pytest.mark.parametrize('value,expected', [('8192',8192),('16384',16384),('99999',16384),('0',256),('bad',16384)])
def test_config_env_reaches_native_setting(value,expected):
    with patch('src.config.setup_env'), patch.dict(os.environ, {'STOCK_ANALYSIS_MAX_TOKENS':value}, clear=True):
        assert Config._load_from_env().stock_analysis_max_tokens == expected
