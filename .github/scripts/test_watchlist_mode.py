"""Only new single-mode watchlist contracts and native offline integration."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from authorized_once import WATCHLIST_BUSINESS, WATCHLIST_PROFILE, canonical_sha, usage_cost
from deepseek_post_guard import GuardStop
from free_market_validation import WATCHLIST
from manual_reports import summarize_usage
from watchlist_mode import batch_spec, encode, load_set, prepare, qualify_financial_fields


@pytest.fixture
def capture(tmp_path):
    source = Path(os.environ['DSA_FIXED_SOURCE'])
    sys.path.insert(0, str(source))
    from src.core.trading_calendar import get_effective_trading_date
    now = dt.datetime.now(dt.timezone.utc)
    target = get_effective_trading_date('us', current_time=now).isoformat()
    data = tmp_path / 'new-synthetic-capture'
    data.mkdir()
    (data / 'RESULTS.json').write_bytes(encode(dict(business_commit=WATCHLIST_BUSINESS, mode='SYNTHETIC_LOCAL_TEST')))
    for symbol in WATCHLIST:
        directory = data / symbol
        directory.mkdir()
        context = dict(code=symbol, stock_name='SYNTHETIC ' + symbol, date=target, fixture_only=True, today=dict(date=target, open=99, close=100, high=101, low=98, volume=1000, volume_ratio=1, ma5=101, ma10=102, ma20=103, ma60=104), yesterday=dict(date=target, close=100, volume=1000, ma5=101, ma10=102, ma20=103, ma60=104), trend_analysis={}, fundamental_context=dict(status='not_supported'))
        (directory / 'NATIVE_CONTEXT.json').write_bytes(encode(context))
        (directory / 'STATUS.json').write_bytes(encode(dict(status='success_simulated_model', session=target, data_mode='synthetic')))
        (directory / 'FINANCIAL_AUDIT.json').write_bytes(encode(dict(fetched_at=now.isoformat())))
        (directory / 'FINAL_REQUEST.json').write_bytes(encode(dict(model='deepseek-flash', messages=[dict(role='user', content='NEW SYNTHETIC TEST ONLY ' + symbol)], thinking=dict(type='disabled'), max_tokens=16384, stream=True, stream_options=dict(include_usage=True))))
    return data, source, ROOT / '.github/frozen/mvp-three/OFFICIAL_PRICING.html'


@pytest.mark.parametrize('mode,limit,reserve', [('nonthinking', 16384, '1.05'), ('thinking', 32768, '2.10')])
def test_35_ordered_single_mode_packets(capture, tmp_path, mode, limit, reserve):
    data, source, pricing = capture
    bundle = tmp_path / mode
    lock = prepare(data, source, bundle, mode, pricing, offline_only=True)
    loaded, packets, contexts = load_set(bundle, canonical_sha(lock))
    assert batch_spec(loaded) == (WATCHLIST_BUSINESS, WATCHLIST, 35, reserve)
    assert len(packets) == len(contexts) == 35
    for symbol in WATCHLIST:
        packet = packets[symbol]
        assert packet['max_tokens'] == limit
        assert packet['thinking'] == {'type': 'enabled' if mode == 'thinking' else 'disabled'}
        assert packet.get('reasoning_effort') == ('high' if mode == 'thinking' else None)
        original = json.loads((data / symbol / 'FINAL_REQUEST.json').read_text('utf-8'))
        assert packet['messages'] == original['messages']
    changed = copy.deepcopy(lock)
    changed['members'][0]['mode'] = 'invalid'
    (bundle / 'WATCHLIST_LOCK.json').write_bytes(encode(changed))
    with pytest.raises(GuardStop, match='watchlist_member_invalid'):
        load_set(bundle, canonical_sha(changed))


@pytest.mark.parametrize('mode', ['nonthinking', 'thinking'])
def test_native_parameters_long_report_and_failure_isolation(capture, tmp_path, mode):
    data, source, pricing = capture
    bundle = tmp_path / 'bundle'
    lock = prepare(data, source, bundle, mode, pricing, ['NVDA', 'MU', 'XLE'], offline_only=True)
    output = tmp_path / 'reports'
    environment = {name: value for name, value in os.environ.items() if not any(part in name.upper() for part in ('KEY', 'TOKEN', 'PASSWORD', 'WEBHOOK'))}
    environment.update(ENV_FILE=str(tmp_path / 'nonexistent.env'), PYTHONIOENCODING='utf-8', LITELLM_LOCAL_MODEL_COST_MAP='True', DSA_FIXED_SOURCE=str(source))
    for name in ('CUSTOM_TIKTOKEN_CACHE_DIR', 'TIKTOKEN_CACHE_DIR'):
        environment[name] = os.environ[name]
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--source', str(source), '--bundle', str(bundle), '--out', str(output), '--batch-sha', canonical_sha(lock), '--simulate', '--inject-failure', 'MU']
    result = subprocess.run(command, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((output / 'BATCH_RESULT.json').read_text('utf-8'))
    assert summary['successful'] == 2 and summary['failed'] == 1
    assert summary['actual_paid_POSTs'] == 0 and summary['fake_calls'] == ['NVDA', 'MU', 'XLE']
    assert all(row['automatic_retry'] is False and row['transport_attempts'] == 1 for row in summary['symbols'])
    assert summary['usage_summary']['source'] == 'synthetic_test_only'
    assert summary['usage_summary']['input_tokens'] == 400
    assert summary['usage_summary']['output_tokens'] == 200
    assert summary['usage_summary']['reported_reasoning_tokens'] == (160 if mode == 'thinking' else 0)
    assert not summary['usage_summary']['complete'] and summary['usage_summary']['estimated_peak_usd'] is None
    for symbol in ('NVDA', 'XLE'):
        for name in ('REPORT.md', 'REPORT.html', 'MODEL_ALL_FIELDS.md', 'MODEL_ALL_FIELDS.html', 'MODEL_COMPLETE.html', 'PROGRAM_FACTS.html', 'MODEL_RAW_TEXT.txt'):
            assert (output / symbol / name).is_file()
        model = json.loads((output / symbol / 'PARSED_MODEL_JSON.json').read_text('utf-8'))
        assert model['technical_analysis'].endswith('LONG_END')
        full = (output / symbol / 'MODEL_ALL_FIELDS.html').read_text('utf-8')
        assert 'LONG_END' in full and '&lt;script&gt;' in full and '<script>' not in full
        assert 'LONG_END' in (output / symbol / 'MODEL_ALL_FIELDS.md').read_text('utf-8')
        assert 'LONG_END' in (output / symbol / 'MODEL_RAW_TEXT.txt').read_text('utf-8')
    index = (output / 'index.html').read_text('utf-8')
    assert 'XLE/REPORT.md' in index and 'NVDA/MODEL_ALL_FIELDS.html' in index
    assert 'MU/REPORT.html' not in index and 'MU/STATUS.json' in index


def test_usage_totals_missing_and_reasoning_not_double_billed():
    usage = dict(prompt_tokens=100, completion_tokens=900, prompt_cache_hit_tokens=60, prompt_cache_miss_tokens=40, completion_tokens_details=dict(reasoning_tokens=800))
    row = dict(transport_attempts=1, actual_paid_POSTs=1, usage=usage, cost_estimate=usage_cost(usage))
    summary = summarize_usage([row, row], False)
    assert summary['input_tokens'] == 200 and summary['output_tokens'] == 1800
    assert summary['reported_reasoning_tokens'] == 1600 and summary['complete']
    from decimal import Decimal
    assert Decimal(summary['estimated_peak_usd']) == Decimal(usage_cost(usage)['peak_usd']) * 2
    assert Decimal(summary['estimated_off_peak_usd']) == Decimal(usage_cost(usage)['off_peak_usd']) * 2
    unknown = summarize_usage([row, dict(transport_attempts=1, actual_paid_POSTs=1)], False)
    assert unknown['estimated_peak_usd'] is None and unknown['missing_usage_requests'] == 1


def test_workflow_remains_manual_and_user_approved():
    import yaml
    workflow = yaml.load((ROOT / '.github/workflows/05-manual-watchlist-mode.yml').read_text('utf-8'), Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'workflow_dispatch', 'workflow_call'}
    assert workflow['on']['workflow_dispatch']['inputs']['execute_live']['default'] == 'false'
    assert workflow['jobs']['live']['environment'] == 'nvda-one-call-approval'
    assert 'secrets.' not in json.dumps(workflow['jobs']['offline'])


def test_workflow_secret_reference_is_explicit(monkeypatch):
    import ast
    import yaml
    workflow = yaml.load((ROOT / '.github/workflows/05-manual-watchlist-mode.yml').read_text('utf-8'), Loader=yaml.BaseLoader)
    live = workflow['jobs']['live']
    assert live['env']['SECRET_APPROVAL_REF'] == '${{ inputs.secret_upload_approval_reference }}'
    assert 'secret_upload_approval_reference' in workflow['on']['workflow_dispatch']['inputs']
    script = next(step['run'] for step in live['steps'] if step.get('name') == 'Bind new batch after user Environment approval')
    tree = ast.parse(script.split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0])
    nodes = [node for node in tree.body if isinstance(node, ast.Assert) and 'SECRET_APPROVAL_REF' in ast.unparse(node)]
    nodes += [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'approval' for target in node.targets)]
    assert len(nodes) == 2
    code = compile(ast.Module(body=nodes, type_ignores=[]), '<workflow-secret-reference>', 'exec')
    monkeypatch.setenv('BATCH_SHA', 'a' * 64)
    monkeypatch.setenv('GITHUB_RUN_ID', 'OFFLINE-TEST')
    monkeypatch.setenv('APPROVAL_REF', 'OFFLINE ONLY ' + 'a' * 64)
    namespace = dict(os=os, count=35, reserve='2.10')
    monkeypatch.setenv('SECRET_APPROVAL_REF', '   ')
    with pytest.raises(AssertionError, match='existing_secret_authorization_reference_required'):
        exec(code, namespace)
    assert 'approval' not in namespace
    monkeypatch.setenv('SECRET_APPROVAL_REF', '  OFFLINE TEST user message reference  ')
    exec(code, namespace)
    assert namespace['approval']['secret_upload_approval_reference'] == 'OFFLINE TEST user message reference'


@pytest.mark.parametrize('execute_live', [False, True])
def test_registered_dispatch_selects_only_the_requested_profile(execute_live):
    import yaml
    from types import SimpleNamespace
    workflow = yaml.load((ROOT / '.github/workflows/04-nvda-free-preflight.yml').read_text('utf-8'), Loader=yaml.BaseLoader)
    route = workflow['jobs']['single_mode_watchlist']
    assert route['uses'] == './.github/workflows/05-manual-watchlist-mode.yml'
    assert route['with']['mode'] == 'nonthinking'
    assert route['with']['bundle_path'] == '.github/frozen/manual-watchlist-approved-bf7c3b89'
    github = SimpleNamespace(actor='tkotcs', repository_owner='tkotcs', ref='refs/heads/deploy/phase2h-request-preparation')
    for universe in ('three', 'watchlist35', 'single_mode_watchlist'):
        inputs = SimpleNamespace(execute_live=execute_live, mvp_universe=universe, mvp_three=True, comparison_modes=False, request_sha256='bf7c3b89f955f50a7836d68c0adc31602a5943f8d3b4bb45bb7263a9228abbc3')
        enabled = []
        for name, job in workflow['jobs'].items():
            expression = job['if'].removeprefix('${{').removesuffix('}}').strip().replace('&&', 'and').replace('||', 'or').replace('!inputs.', 'not inputs.')
            if eval(expression, {'__builtins__': {}}, dict(inputs=inputs, github=github)):
                enabled.append(name)
        assert enabled == (['single_mode_watchlist'] if universe == 'single_mode_watchlist' else ['mvp_live'] if execute_live else ['mvp'])
    called = yaml.load((ROOT / '.github/workflows/05-manual-watchlist-mode.yml').read_text('utf-8'), Loader=yaml.BaseLoader)
    assert set(route['with']) == set(called['on']['workflow_call']['inputs'])
    assert called['jobs']['live']['environment'] == 'nvda-one-call-approval'
    assert called['concurrency']['group'] != workflow['concurrency']['group']


def financial_fixture():
    report = dict(report_date='2026-06-30', revenue=700.0, net_profit_parent=70.0, operating_cash_flow=20.0, roe=10.0, currency='USD')
    context = dict(code='AMZN', fundamental_context=dict(earnings=dict(data=dict(financial_report=report))))
    audit = dict(fields=dict(revenue=dict(classification='TTM_or_unknown_info_fallback', value=700.0), net_profit_parent=dict(classification='estimated_revenue_times_margin', value=70.0), operating_cash_flow=dict(classification='quarterly_Yahoo_not_officially_verified', actual_series_period='2026-06-30', value=20.0)))
    table = '| 最近报告期 | 2026-06-30 | 来自结构化财报字段 |\n'
    table += '\n'.join(f'| {label} | {report[field]} | |' for field, label in [('revenue', '营业收入'), ('net_profit_parent', '归母净利润'), ('operating_cash_flow', '经营现金流'), ('roe', 'ROE')])
    return context, dict(messages=[dict(role='user', content=table)]), audit


def test_financial_periods_and_source_classes_are_field_specific():
    context, packet, audit = financial_fixture()
    before = encode(context), encode(packet), encode(audit)
    qualified, updated = qualify_financial_fields(context, packet, audit)
    notes = qualified['financial_field_provenance']
    assert notes['revenue']['period_end'] is None
    assert notes['net_profit_parent']['classification'] == 'estimated_revenue_times_margin'
    assert notes['operating_cash_flow']['period_end'] == '2026-06-30'
    assert '不是正式季度归母净利润' in updated['messages'][0]['content']
    assert '| 最近报告期 |' not in updated['messages'][0]['content']
    assert before == (encode(context), encode(packet), encode(audit))
    context['official_research'] = dict(values=dict(revenue=700.0, net_profit_parent=70.0, operating_cash_flow=20.0), period_end='2026-07-26', source_url='https://example.invalid/official-fixture')
    official, _ = qualify_financial_fields(context, packet, audit)
    assert official['financial_field_provenance']['revenue']['period_end'] == '2026-07-26'
    assert official['financial_field_provenance']['revenue']['classification'] == 'reviewed_official_packet_not_revalidated'
    assert all(not item['independently_official_verified'] for item in official['financial_field_provenance'].values())
    assert official['financial_field_provenance']['roe']['period_end'] is None


def test_financial_qualifier_rejects_ambiguous_prompt():
    context, packet, audit = financial_fixture()
    packet['messages'][0]['content'] = packet['messages'][0]['content'].replace('700.0', '701.0')
    with pytest.raises(GuardStop, match='financial_prompt_value_mismatch'):
        qualify_financial_fields(context, packet, audit)


@pytest.mark.parametrize('mode', ['nonthinking', 'thinking'])
def test_preparer_qualifies_financials_without_extending_material(capture, tmp_path, mode):
    data, source, pricing = capture
    directory = data / 'AMZN'
    financial_context, financial_packet, audit = financial_fixture()
    context = json.loads((directory / 'NATIVE_CONTEXT.json').read_text('utf-8'))
    context.update(financial_context)
    packet = json.loads((directory / 'FINAL_REQUEST.json').read_text('utf-8'))
    packet['messages'] = financial_packet['messages']
    original_asof = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
    audit['fetched_at'] = original_asof
    (directory / 'NATIVE_CONTEXT.json').write_bytes(encode(context))
    (directory / 'FINAL_REQUEST.json').write_bytes(encode(packet))
    (directory / 'FINANCIAL_AUDIT.json').write_bytes(encode(audit))
    before = {name: (directory / name).read_bytes() for name in ('NATIVE_CONTEXT.json', 'FINAL_REQUEST.json', 'FINANCIAL_AUDIT.json')}
    lock = prepare(data, source, tmp_path / 'qualified', mode, pricing, ['AMZN'], offline_only=True)
    _, packets, contexts = load_set(tmp_path / 'qualified', canonical_sha(lock))
    assert lock['members'][0]['analysis_asof'] == original_asof
    assert lock['members'][0]['request_sha256'] != canonical_sha(packet)
    assert packets['AMZN']['messages'] != packet['messages']
    assert contexts['AMZN']['today'] == context['today']
    assert contexts['AMZN']['financial_field_provenance']['revenue']['period_end'] is None
    assert dt.datetime.fromisoformat(lock['members'][0]['material_expires_at']) <= dt.datetime.fromisoformat(original_asof) + dt.timedelta(hours=24)
    assert before == {name: (directory / name).read_bytes() for name in before}


@pytest.mark.parametrize('event_evidence', [False, True])
def test_cross_currency_dividend_quarantine(event_evidence):
    context, packet, audit = financial_fixture()
    report = context['fundamental_context']['earnings']['data']['financial_report']
    report['currency'] = 'KRW'
    dividend = dict(events=[dict(cash_dividend_per_share=1.0)] if event_evidence else [], currency='USD', ttm_cash_dividend_per_share=3750.0, ttm_dividend_yield_pct=2747.454, ttm_event_count=1 if event_evidence else 0)
    context['fundamental_context']['earnings']['data']['dividend'] = dividend
    packet['messages'].insert(0, dict(role='system', content='Original native system text'))
    packet['messages'][1]['content'] += '\n' + '\n'.join(f'| {label} | {dividend[field]} | |' for field, label in [('ttm_cash_dividend_per_share', '近12个月每股现金分红'), ('ttm_dividend_yield_pct', 'TTM 股息率'), ('ttm_event_count', 'TTM 分红事件数')])
    before = encode(context), encode(packet), encode(audit)
    qualified, updated = qualify_financial_fields(context, packet, audit, 'USD')
    data = qualified['fundamental_context']['earnings']['data']
    if event_evidence:
        assert 'financial_input_restriction' not in qualified
        assert data['dividend']['ttm_cash_dividend_per_share'] == 3750.0
    else:
        assert 'financial_input_restriction' in qualified
        assert all(data['financial_report'][field] is None for field in ('revenue', 'net_profit_parent', 'operating_cash_flow', 'roe'))
        assert data['dividend']['ttm_cash_dividend_per_share'] is None
        assert '3750.0' not in json.dumps(updated)
        assert '2747.454' not in json.dumps(updated)
        assert all(note['value'] is None for note in qualified['financial_field_provenance'].values())
        assert updated['messages'][0] == packet['messages'][0]
    assert before == (encode(context), encode(packet), encode(audit))


def test_old_profile_business_bindings_unchanged():
    from authorized_once import authorized_business, COMPARISON_PROFILE, MANUAL_BUSINESS
    from mvp_three_live import batch_spec as executor_spec
    assert authorized_business({'test_profile': 'mvp_manual_v2'}) == MANUAL_BUSINESS
    assert executor_spec({'profile': 'mvp_manual_v2', 'members': [{'symbol': 'NVDA'}]}) == (MANUAL_BUSINESS, ['NVDA'], 1, '0.03')
    assert executor_spec({'profile': COMPARISON_PROFILE})[2:] == (6, '0.27')


def test_expired_capture_is_not_repackaged(capture, tmp_path):
    data, source, pricing = capture
    (data / 'NVDA' / 'FINANCIAL_AUDIT.json').write_bytes(encode(dict(fetched_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat())))
    output = tmp_path / 'expired'
    with pytest.raises(GuardStop, match='material_EXPIRED'):
        prepare(data, source, output, 'thinking', pricing, ['NVDA'], offline_only=True)
    assert not output.exists()


if __name__ == '__main__' and '--worker' in sys.argv:
    sys.argv.remove('--worker')
    original_connect = socket.socket.connect
    def deny_connection(instance, address):
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return original_connect(instance, address)
        raise AssertionError('offline integration attempted a network connection')
    socket.socket.connect = deny_connection
    import mvp_three
    original_fixture = mvp_three.fixture
    def long_fixture(symbol, context):
        model = original_fixture(symbol, context)
        model['technical_analysis'] += '<script>UNTRUSTED</script>' + '长报告字段。' * 7000 + 'LONG_END'
        return model
    mvp_three.fixture = long_fixture
    from mvp_three_live import main
    main()
