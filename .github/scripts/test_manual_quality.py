import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manual_reports import quality_findings, record_outputs, render_status_index, save_full_report, save_quality_review


def context():
    return dict(today=dict(date='2026-10-16', low=136.23, ma5=149.89, ma10=164.48, ma20=176.88, ma60=166.207), yesterday=dict(date='2026-10-15', low=137.80))


def test_ma_order_counterexample_and_correct_order():
    findings = quality_findings(dict(analysis_summary='MA5<MA10<MA20<MA60', ma_analysis='MA5<MA10<MA60<MA20'), context())
    assert len(findings) == 1
    assert findings[0]['field_path'] == 'analysis_summary'
    assert findings[0]['category'] == 'MA_ORDER_CONTRADICTION'


def test_equal_averages_do_not_satisfy_strict_order():
    facts = context()
    facts['today']['ma10'] = facts['today']['ma5']
    assert quality_findings(dict(analysis_summary='MA5<MA10'), facts)


def test_negated_and_hypothetical_order_is_not_a_factual_contradiction():
    for text in ('不满足MA5>MA10>MA20', 'MA5>MA10>MA20多头排列不成立', '多头排列（MA5>MA10>MA20）是买入必要条件，当前不满足', '多头排列需MA5>MA10>MA20，当前完全不满足'):
        assert not quality_findings(dict(ma_analysis=text), context())


def test_low_date_and_unproven_historical_support():
    for text in ('136.23（前日低点）', '前日低点136.23', '136.23前低'):
        findings = quality_findings(dict(ma_analysis=text), context())
        assert findings[0]['category'] == 'LOW_DATE_REFERENCE_REVIEW'
        assert findings[0]['evidence']['previous_low'] == 137.80
    assert not quality_findings(dict(ma_analysis='当日低点136.23'), context())


def test_missing_scenarios_and_defined_references():
    model = dict(dashboard=dict(battle_plan=dict(sniper_points=dict(ideal_buy='情景B条件'), risk_plan=dict(mode='watch', scenarios=[]))))
    assert quality_findings(model, context())[0]['category'] == 'UNDEFINED_SCENARIO_REFERENCE'
    model['dashboard']['battle_plan']['risk_plan']['scenarios'] = [dict(id='B')]
    assert not quality_findings(model, context())


def test_buy_is_conditional_without_trusted_trigger_evaluation():
    model = dict(action='buy', decision_type='buy', operation_advice='持有')
    finding = quality_findings(model, context())[0]
    assert finding['category'] == 'CONDITIONAL_ENTRY_NOT_VERIFIED'
    assert finding['evidence']['trigger_evaluation'] == 'not_performed'


def test_sidecars_preserve_original_model_and_raw_evidence(tmp_path):
    model = dict(action='watch', analysis_summary='MA5<MA10<MA20<MA60')
    before = copy.deepcopy(model)
    raw = tmp_path / 'MODEL_RAW_TEXT.txt'
    raw.write_bytes(b'original raw bytes\r\n')
    review = save_quality_review(tmp_path, 'SYNTHETIC', model, context(), [dict(category='BLOCKED_PERIOD_MAPPING', field_path='fundamental_analysis', original_content='synthetic', evidence='column headers absent', recommendation='quarantine financial conclusions')])
    assert model == before and raw.read_bytes() == b'original raw bytes\r\n'
    assert review['quality_accepted'] is False and review['published'] is False
    assert len(review['findings']) == 2
    assert json.loads((tmp_path / 'QA_FINDINGS.json').read_text('utf-8'))['findings'][-1]['category'] == 'BLOCKED_PERIOD_MAPPING'


def test_future_report_and_index_expose_independent_qa(tmp_path):
    save_full_report(tmp_path, 'SYNTHETIC', dict(action='buy', operation_advice='持有'), context(), 'synthetic facts', True)
    row = dict(symbol='SYNTHETIC', execution_success=True)
    record_outputs(row, tmp_path, True)
    index = render_status_index([row], 'SIMULATED')
    assert 'SYNTHETIC/QUALITY_REVIEW.html' in index and '独立质量审核' in index
    assert 'QUALITY_REVIEW.html' in (tmp_path / 'MODEL_ALL_FIELDS.html').read_text('utf-8')
    assert 'CONDITIONAL_ENTRY_NOT_VERIFIED' in (tmp_path / 'QA_FINDINGS.json').read_text('utf-8')


def test_missing_facts_are_not_invented_and_html_escaped(tmp_path):
    model = dict(analysis_summary='MA5<MA10<MA20<MA60<script>not executed</script>')
    save_quality_review(tmp_path, '<synthetic>', model, {})
    assert not quality_findings(model, {})
    assert '<synthetic>' not in (tmp_path / 'QUALITY_REVIEW.html').read_text('utf-8')


def test_review_states_and_discovery_origins(tmp_path):
    model = dict(analysis_summary='MA5<MA10<MA20<MA60')
    manual = [dict(category='BLOCKED_PERIOD_MAPPING', field_path='fundamental_analysis', original_content='synthetic', evidence='missing headers', recommendation='financial conclusions blocked'), dict(category='UNVERIFIED_FINANCIAL_PLAUSIBILITY', field_path='fundamental_analysis', original_content='synthetic', evidence='unusual ratio, not proof of error', recommendation='verify source')]
    before = copy.deepcopy(manual)
    review = save_quality_review(tmp_path, 'SYNTHETIC', model, context(), manual)
    assert manual == before
    assert review['findings'][0]['discovery_origin'] == 'automatic_narrow_rule'
    assert review['findings'][0]['evidence_status'] == 'CONFIRMED_CONTRADICTION'
    assert review['findings'][1]['discovery_origin'] == 'operator_supplied_review'
    assert review['findings'][1]['evidence_status'] == 'SOURCE_BLOCKER'
    assert review['findings'][2]['evidence_status'] == 'REVIEW_CANDIDATE'
    assert review['evidence_status_counts'] == dict(CONFIRMED_CONTRADICTION=1, REVIEW_CANDIDATE=1, SOURCE_BLOCKER=1, INTERPRETATION_LIMITATION=0)


def test_normal_report_path_accepts_review_additions_without_publication(tmp_path):
    manual = [dict(category='ESTIMATE_NOT_REPORTED_QUARTERLY_INCOME', field_path='fundamental_analysis', original_content='synthetic estimate', evidence='mixed periods', recommendation='do not compute quarterly profit margin')]
    model = dict(action='buy', operation_advice='持有')
    save_full_report(tmp_path, 'SYNTHETIC', model, context(), 'synthetic facts', True, additional_findings=manual)
    review = json.loads((tmp_path / 'QA_FINDINGS.json').read_text('utf-8'))
    assert review['published'] is False and review['quality_accepted'] is False
    assert review['evidence_status_counts']['INTERPRETATION_LIMITATION'] == 2
    assert review['findings'][-1]['discovery_origin'] == 'operator_supplied_review'
    assert 'synthetic estimate' not in (tmp_path / 'MODEL_ALL_FIELDS.md').read_text('utf-8')


def test_unknown_categories_remain_review_candidates(tmp_path):
    review = save_quality_review(tmp_path, 'SYNTHETIC', {}, {}, [dict(category='NEW_UNVERIFIED_CASE')])
    assert review['findings'][0]['evidence_status'] == 'REVIEW_CANDIDATE'
    assert review['quality_accepted'] is False


def test_empty_risk_dependencies_across_battle_plan():
    model = dict(dashboard=dict(battle_plan=dict(risk_plan=dict(mode='watch', scenarios=[]), sniper_points=dict(ideal_buy='待risk_plan情景触发后评估'), position_strategy=dict(entry_plan='触发后按risk_plan情景评估'))))
    findings = quality_findings(model, {})
    assert len(findings) == 2
    assert all(item['category'] == 'EMPTY_SCENARIO_DEPENDENCY' for item in findings)
    model['dashboard']['battle_plan']['risk_plan']['scenarios'] = [dict(id='S1')]
    assert not quality_findings(model, {})


def test_position_reference_checked_but_definition_not_scanned():
    model = dict(dashboard=dict(battle_plan=dict(risk_plan=dict(mode='watch', scenarios=[]), position_strategy=dict(entry_plan='仅情景S2成立后考虑'))))
    assert quality_findings(model, {})[0]['evidence']['missing'] == ['S2']
    model['dashboard']['battle_plan']['risk_plan']['scenarios'] = [dict(id='S2', trigger='情景S3只是描述')]
    assert not quality_findings(model, {})


def test_decision_scope_warning_does_not_rewrite_or_reject_watch_hold(tmp_path):
    model = dict(action='watch', decision_type='sell', operation_advice='观望')
    before = copy.deepcopy(model)
    review = save_quality_review(tmp_path, 'SYNTHETIC', model, {})
    assert model == before
    assert review['findings'][0]['category'] == 'DECISION_LABEL_SCOPE_REVIEW'
    assert review['findings'][0]['evidence_status'] == 'REVIEW_CANDIDATE'
    assert not quality_findings(dict(action='watch', decision_type='hold', operation_advice='观望'), {})


def test_buy_trigger_remains_unknown_despite_model_claim():
    model = dict(action='buy', decision_type='buy', operation_advice='持有', dashboard=dict(battle_plan=dict(risk_plan=dict(mode='trade', scenarios=[dict(id='S1', trigger='已触发')]))))
    findings = quality_findings(model, {})
    trigger = next(item for item in findings if item['category'] == 'CONDITIONAL_ENTRY_NOT_VERIFIED')
    assert trigger['evidence']['trigger_evaluation'] == 'not_performed'
    assert any(item['category'] == 'DECISION_LABEL_SCOPE_REVIEW' for item in findings)


def test_defensive_reference_path_is_candidate_not_fabricated_field(tmp_path):
    model = dict(dashboard=dict(battle_plan=dict(risk_plan=dict(mode='watch', scenarios=[]), sniper_points=dict(stop_loss='参考risk_plan中防守观察条件'), position_strategy=dict(risk_control='收盘跌破观察线再评估'))))
    review = save_quality_review(tmp_path, 'SYNTHETIC', model, {})
    finding = review['findings'][0]
    assert finding['category'] == 'RISK_PLAN_REFERENCE_PATH_REVIEW'
    assert finding['evidence_status'] == 'REVIEW_CANDIDATE'
    assert 'risk_control' not in model['dashboard']['battle_plan']['risk_plan']
