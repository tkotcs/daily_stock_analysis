"""Offline contract tests; all prices, credentials and model replies here are synthetic."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import daily_briefing as daily
from manual_responses_candidate import canonical

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 20, 11, 30, tzinfo=timezone.utc)
SESSION = '2026-10-19'
PROFILE = ROOT / '.github/research/gpt-6.1-sol-review-profile.json'
SOURCE = Path(os.environ.get('DSA_FIXED_SOURCE', ROOT))


@pytest.fixture(autouse=True)
def configured_public_endpoint(monkeypatch):
    monkeypatch.setenv('RESEARCH_API_BASE', 'https://api.sequenceq.com/v1')


def context(symbol='AAPL', pct=3.0):
    today = dict(date=SESSION, open=101.0, high=105.0, low=100.0, close=103.0,
                 ma5=102.0, ma10=101.0, ma20=100.5, ma60=100.0, pct_chg=pct, volume_ratio=1.6)
    yesterday = dict(date='2026-10-16', open=102.0, high=104.0, low=98.0, close=99.0,
                     ma5=100.0, ma10=99.5, ma20=99.0, ma60=98.0)
    return dict(code=symbol, stock_name='SYNTHETIC fixture ' + symbol, date=SESSION,
                today=today, yesterday=yesterday, trend_analysis=dict(rsi_12=55),
                fundamental_context={})


def price_audit(symbol='AAPL'):
    return dict(canonical_symbol=symbol, metadata=dict(currency='USD'),
                fetched_at='2026-10-20T11:00:00+00:00', identity_limit=None)


def fixture_capture(folder):
    folder.mkdir()
    statuses = []
    for symbol in daily.WATCHLIST:
        good = symbol in ('AAPL', 'MSFT', 'QQQ')
        statuses.append(dict(symbol=symbol, status='success_simulated_model' if good else 'failed',
                             error=None if good else 'SYNTHETIC_failure', real_POSTs=0))
        if not good:
            continue
        child = folder / symbol
        child.mkdir()
        for name, value in {
            'NATIVE_CONTEXT.json': context(symbol, 3 if symbol == 'AAPL' else 2),
            'FINAL_REQUEST.json': dict(model='deepseek-flash', messages=[
                dict(role='system', content='SYNTHETIC native system'),
                dict(role='user', content='SYNTHETIC native focus input')]),
            'FINANCIAL_AUDIT.json': dict(fields={}),
            'TECHNICAL.json': dict(MA60_verified=True, rows_read=63),
            'PRICE_AUDIT.json': price_audit(symbol),
            'STATUS.json': statuses[-1],
        }.items():
            daily.save(child / name, value)
    daily.save(folder / 'RESULTS.json', dict(business_commit=daily.BUSINESS,
               mode='LIVE_FREE_DATA_MOCK_MODEL', real_POSTs=0, symbols=statuses, run_id='SYNTHETIC_CAPTURE'))
    return folder


def bundle(tmp_path, *, historical=False,automatic=False):
    data = fixture_capture(tmp_path / 'capture')
    target = tmp_path / 'prepared'
    daily.prepare(data, SOURCE, PROFILE, target, SESSION, historical=historical, now=NOW,
                  automatic=automatic)
    return data, target, (target / 'BATCH_SHA256.txt').read_text().strip()


def test_one_consolidated_request_and_35_rows_keep_failed_symbols(tmp_path):
    data, target, digest = bundle(tmp_path)
    facts = daily.read(target / 'DAILY_FACTS.json')
    request = daily.read(target / 'REQUEST.json')
    assert len(facts['rows']) == 3 and len(facts['omitted']) == 32
    assert facts['focus']['symbol'] == 'AAPL'
    assert facts['baseline_model_POSTs'] == 0 and facts['max_total_model_POSTs'] == 1
    assert request['model'] == 'gpt-6.1-sol'
    assert request['reasoning'] == {'effort': 'high'} and request['max_output_tokens'] == 32768
    text = '\n'.join(m['content'] for m in request['input'])
    assert all(title in text for title in daily.SECTIONS)
    assert 'context:股票代码' in text and '不要逐股重写长文' in text
    md = (target / 'DAILY_REPORT.md').read_text('utf-8')
    assert all('| ' + symbol + ' |' in md for symbol in daily.WATCHLIST)
    assert '尚未调用模型' in md and 'SYNTHETIC native focus input' not in text
    assert '汇总截止时间：' + NOW.isoformat() in md
    assert '2026-10-20T11:00:00+00:00' in md
    assert (target / 'DAILY_PREVIEW.eml').exists()
    assert daily.sha((target / 'DAILY_LOCK.json').read_bytes()) == digest


def test_saved_news_is_prioritized_without_claiming_independent_or_full_coverage(monkeypatch):
    rows = [daily.fact_row('AAPL', context(), dict(MA60_verified=True, rows_read=63),
                          price_audit(), NOW.isoformat()),
            daily.fact_row('MSFT', context('MSFT', 1), dict(MA60_verified=True, rows_read=63),
                          price_audit('MSFT'), NOW.isoformat())]
    contexts = {symbol: context(symbol) for symbol in ('AAPL', 'MSFT')}
    contexts['MSFT']['saved_news_audit'] = dict(accepted=[dict(
        source='SYNTHETIC publisher', title='SYNTHETIC title',
        url='https://example.test/article', published_at='2026-10-19T16:00:00+00:00',
        fetched_at='2026-10-20T10:00:00+00:00', content_kind='metadata_only')])
    before = copy.deepcopy(contexts)
    selected = daily.choose_focus(rows, contexts, NOW)
    assert selected['symbol'] == 'MSFT' and selected['priority'] == 2
    assert selected['investment_recommendation'] is False and selected['rotation'] is False
    assert contexts == before
    contexts['MSFT']['saved_news_audit']['accepted'][0]['published_at'] = '2026-09-01T16:00:00+00:00'
    assert daily.choose_focus(rows, contexts, NOW)['symbol'] == 'AAPL'


def test_no_eligible_equity_does_not_invent_a_focus():
    ctx = context('QQQ')
    row = daily.fact_row('QQQ', ctx, dict(MA60_verified=True, rows_read=63),
                         price_audit('QQQ'), NOW.isoformat())
    assert daily.choose_focus([row], {'QQQ': ctx}, NOW) is None
    row['symbol'] = 'AAPL'
    row['identity_limit'] = 'SYNTHETIC unverified issuer'
    assert daily.choose_focus([row], {'AAPL': context()}, NOW) is None


def test_all_capture_failures_are_distinct_from_no_eligible_equity(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, 'source_check', lambda *a: None)
    omitted = [dict(symbol=code, reason='native_capture_failed',
                    detail='SYNTHETIC latest_completed_session_missing')
               for code in daily.WATCHLIST]
    monkeypatch.setattr(daily, 'load_capture', lambda *a: ([], {}, omitted, {}))
    out = tmp_path/'blocked'
    assert daily.prepare(tmp_path, tmp_path, PROFILE, out, SESSION, now=NOW) is None
    state = daily.read(out/'PREPARATION_STATUS.json')
    assert state['status'] == 'capture_unavailable_no_POST'
    assert state['valid_rows'] == 0 and state['omitted_rows'] == 35
    assert state['capture_failure_details'] == omitted
    assert not (out/'REQUEST.json').exists()


def test_MACD_display_keeps_DIF_DEA_histogram_order_after_canonical_JSON_roundtrip(tmp_path):
    ctx = context()
    row = daily.fact_row('AAPL', ctx, dict(MA60_verified=True, rows_read=63,
                         macd_dif=1.0, macd_dea=2.0, macd_bar=3.0),
                         price_audit(), NOW.isoformat())
    facts = dict(session=SESSION, symbols=daily.WATCHLIST, rows=[row],
                 omitted=[dict(symbol=s, reason='SYNTHETIC_missing') for s in daily.WATCHLIST if s != 'AAPL'],
                 focus=dict(symbol='AAPL', reason='SYNTHETIC'))
    # Canonical serialization sorts object keys; rendering must use explicit column order.
    daily.render_report(tmp_path, json.loads(canonical(facts)))
    assert '1.0000 / 2.0000 / 3.0000' in (tmp_path / 'DAILY_REPORT.md').read_text('utf-8')


@pytest.mark.parametrize('change', ['previous_date', 'wrong_date', 'NaN', 'identity', 'short_history', 'fixture'])
def test_invalid_evidence_is_an_explicit_gap_without_dropping_watchlist_rows(tmp_path, change):
    data = fixture_capture(tmp_path / 'capture')
    child = data / 'AAPL'
    if change in ('previous_date', 'wrong_date', 'NaN', 'fixture'):
        ctx = daily.read(child / 'NATIVE_CONTEXT.json')
        if change == 'previous_date':
            ctx['yesterday']['date'] = '2026-10-15'
        elif change == 'wrong_date':
            ctx['date'] = '2026-10-16'
        elif change == 'NaN':
            ctx['today']['close'] = float('nan')
        else:
            ctx['fixture_only'] = True
        daily.save(child / 'NATIVE_CONTEXT.json', ctx)
    elif change == 'identity':
        audit = price_audit('WRONG')
        daily.save(child / 'PRICE_AUDIT.json', audit)
    else:
        daily.save(child / 'TECHNICAL.json', dict(MA60_verified=True, rows_read=20))
    daily.source_check(SOURCE)
    rows, _, omitted, _ = daily.load_capture(data, SESSION, NOW)
    assert not any(row['symbol'] == 'AAPL' for row in rows)
    assert any(row['symbol'] == 'AAPL' and row['reason'] == 'capture_evidence_rejected' for row in omitted)
    assert len(rows) + len(omitted) == 35


def test_historical_preview_cannot_be_sent_even_with_its_correct_hash(tmp_path, monkeypatch):
    _, target, digest = bundle(tmp_path, historical=True)
    monkeypatch.setenv('RESEARCH_API_BASE', 'https://api.sequenceq.com/v1')
    with pytest.raises(ValueError, match='daily_one_call_or_live_material_invalid'):
        daily.load_live_bundle(target, digest)


def test_missing_endpoint_is_blocked_without_assuming_a_provider_url(tmp_path, monkeypatch):
    monkeypatch.delenv('RESEARCH_API_BASE')
    data = fixture_capture(tmp_path / 'capture')
    target = tmp_path / 'not-configured'
    lock = daily.prepare(data, SOURCE, PROFILE, target, SESSION, now=NOW)
    assert lock['endpoint'] is None
    assert 'public_endpoint_not_configured' in lock['blockers']
    assert daily.read(target / 'PREPARATION_STATUS.json')['status'] == 'blocked'


@pytest.mark.parametrize('change', ['changed_file', 'missing_file_entry', 'context_values'])
def test_changed_bundle_or_rebound_semantic_mismatch_is_rejected(tmp_path, monkeypatch, change):
    _, target, digest = bundle(tmp_path)
    monkeypatch.setenv('RESEARCH_API_BASE', 'https://api.sequenceq.com/v1')
    lock = daily.read(target / 'DAILY_LOCK.json')
    if change == 'changed_file':
        with (target / 'DAILY_FACTS.json').open('ab') as handle:
            handle.write(b' ')
    elif change == 'missing_file_entry':
        lock['files'].pop('CONTEXTS.json')
    else:
        facts = daily.read(target / 'DAILY_FACTS.json')
        facts['rows'][0]['close'] += 1
        daily.save(target / 'DAILY_FACTS.json', facts)
        lock['files']['DAILY_FACTS.json'] = daily.sha((target / 'DAILY_FACTS.json').read_bytes())
    if change != 'changed_file':
        daily.save(target / 'DAILY_LOCK.json', lock)
        digest = daily.sha((target / 'DAILY_LOCK.json').read_bytes())
    with pytest.raises(ValueError, match='changed|invalid|mismatch'):
        daily.load_live_bundle(target, digest)


def test_daily_schema_refuses_wrong_focus_order_and_invented_citations():
    facts = dict(focus=dict(symbol='AAPL'), rows=[dict(symbol='AAPL')], evidence_cutoff=NOW.isoformat())
    model = dict(focus_symbol='AAPL', dashboard=dict(battle_plan=dict(
                     risk_plan=dict(mode='watch', max_position_pct=0, scenarios=[]))),
                 analysis_summary='SYNTHETIC', risk_warning='SYNTHETIC',
                 daily_sections=[dict(title=title, text='SYNTHETIC explanation', sources=['context:AAPL'])
                                 for title in daily.SECTIONS])
    assert len(daily.validate_sections(model, facts, {'AAPL': context()})) == 7
    for mutate in ('focus', 'order', 'citation'):
        bad = copy.deepcopy(model)
        if mutate == 'focus':
            bad['focus_symbol'] = 'MSFT'
        elif mutate == 'order':
            bad['daily_sections'].reverse()
        else:
            bad['daily_sections'][0]['sources'] = ['news:unprovided:0']
        with pytest.raises(ValueError):
            daily.validate_sections(bad, facts, {'AAPL': context()})
    model['dashboard']['battle_plan']['risk_plan'] = dict(
        mode='trade', max_position_pct=10, scenarios=[dict(entry=100, stop=110, target=90,
                                                          position_pct=10, trigger='SYNTHETIC',
                                                          invalidation='SYNTHETIC')])
    with pytest.raises(ValueError, match='risk_plan_invalid'):
        daily.validate_sections(model, facts, {'AAPL': context()})


def test_consolidated_input_cannot_silently_exceed_the_selected_reservation(tmp_path):
    data = fixture_capture(tmp_path / 'capture')
    ctx = daily.read(data / 'AAPL/NATIVE_CONTEXT.json')
    ctx['stock_name'] = 'SYNTHETIC-LARGE-EVIDENCE ' * 20000
    daily.save(data / 'AAPL/NATIVE_CONTEXT.json', ctx)
    target = tmp_path / 'oversized'
    with pytest.raises(ValueError, match='long_context|reservation_exceeded'):
        daily.prepare(data, SOURCE, PROFILE, target, SESSION, now=NOW)
    assert not (target / 'DAILY_LOCK.json').exists()
    assert not (target / 'POST_ATTEMPT.json').exists()


@pytest.mark.parametrize('timestamp,expected', [
    ('2026-10-20T11:00:00+00:00', True),
    ('2026-10-17T11:00:00+00:00', False),
    ('2026-12-25T11:00:00+00:00', False),
    # Beijing Saturday morning is still Friday in New York.
    ('2026-10-17T05:00:00+08:00', True),
])
def test_trading_day_gate_uses_market_day_instead_of_beijing_weekday(timestamp, expected):
    daily.source_check(SOURCE)
    assert daily.trading_day_gate(datetime.fromisoformat(timestamp))['run'] is expected


def github_env(monkeypatch):
    for key, value in dict(SEEKERX='SYNTHETIC-key-not-real', GITHUB_TOKEN='SYNTHETIC-GitHub',
                           GITHUB_REPOSITORY='owner/repo', GITHUB_RUN_ID='987654',
                           GITHUB_SHA='b' * 40, GITHUB_RUN_ATTEMPT='1',
                           GITHUB_ACTOR='owner', GITHUB_REPOSITORY_OWNER='owner',
                           GITHUB_REF='refs/heads/deploy/phase2h-request-preparation',
                           RESEARCH_API_BASE='https://api.sequenceq.com/v1').items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize('outcome', ['success', 'bad_sections', 'transport_failure','confirmed_QA','section_QA'])
@pytest.mark.parametrize('automatic',[False,True])
def test_daily_generation_uses_single_shared_transport_keeps_failure_evidence(tmp_path, monkeypatch, outcome,automatic):
    github_env(monkeypatch)
    if automatic:
        from test_daily_automatic import automatic_env
        automatic_env(tmp_path,monkeypatch)
    _, target, digest = bundle(tmp_path,automatic=automatic)
    # The synthetic capture clock is fixed; transport tests do not weaken production clocks.
    monkeypatch.setattr(daily, 'check_time', lambda lock: None)
    from datetime import date
    import src.core.trading_calendar as calendar
    monkeypatch.setattr(calendar,'get_effective_trading_date',lambda *a,**k:date.fromisoformat(SESSION))
    import remote_execution_claim as remote
    events = []
    class Claim:
        def __init__(self, api, batch, *args, **kwargs):
            assert batch == daily.sha(('DSA:consolidated-daily:v1:' + SESSION).encode())
        def reserve(self, members):
            events.append('reserve')
            return {'SYNTHETIC': members}
        def before_send(self, *args):
            events.append('before_send')
    monkeypatch.setattr(remote, 'GitHubAPI', lambda *args: None)
    monkeypatch.setattr(remote, 'RemoteExecutionClaim', Claim)
    model = dict(stock_name='SYNTHETIC（AAPL）', focus_symbol='AAPL', action='watch',
                 operation_advice='观望', decision_type='hold', sentiment_score=50,
                 dashboard=dict(battle_plan=dict(risk_plan=dict(mode='watch', max_position_pct=0, scenarios=[]))),
                 analysis_summary='SYNTHETIC summary', risk_warning='SYNTHETIC risk',
                 daily_sections=[dict(title=title, text='SYNTHETIC explanation', sources=['context:AAPL'])
                                 for title in daily.SECTIONS])
    if outcome == 'bad_sections':
        model['daily_sections'][0]['sources'] = ['SYNTHETIC-invented']
    if outcome == 'confirmed_QA':
        model['technical_analysis']='SYNTHETIC: MA5<MA10<MA20<MA60'
    if outcome == 'section_QA':
        model['daily_sections'][0]['text']='SYNTHETIC: MA5<MA10<MA20<MA60'
    import httpx
    class Response:
        status_code = 503 if outcome == 'transport_failure' else 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_bytes(self):
            value = dict(model='gpt-6.1-sol', status='completed',
                         usage=dict(input_tokens=20, output_tokens=10),
                         output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(model))])])
            yield ('data: ' + json.dumps(dict(type='response.completed', response=value)) + '\n\n').encode()
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['transport']._pool._retries == 0
            assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def stream(self, method, *args, **kwargs):
            assert method == 'POST'
            events.append('POST')
            return Response()
    monkeypatch.setattr(httpx, 'Client', Client)
    result = daily.generate(target, digest, SOURCE, tmp_path / 'real', 'SYNTHETIC authorization',
                            automatic=automatic)
    assert events == ['reserve', 'before_send', 'POST']
    assert result['actual_model_POST_attempts'] == 1
    assert (tmp_path / 'real/RAW_RESPONSE_BODY.bin').exists()
    expected='generated_daily_automatic_validated' if automatic else 'generated_daily_preview_requires_review'
    passed=outcome=='success' or outcome in ('confirmed_QA','section_QA') and not automatic
    assert result['status'] == (expected if passed else 'failed_no_retry')
    if passed:
        assert (tmp_path / 'real/DAILY_REPORT.md').exists()
        assert result['report_sha256']==daily.sha((tmp_path/'real/DAILY_REPORT.md').read_bytes())
        if automatic:
            assert '按用户授权自动发送' in (tmp_path/'real/DAILY_REPORT.md').read_text('utf-8')
    elif outcome in ('bad_sections','confirmed_QA','section_QA'):
        assert result['usage']['input_tokens'] == 20
        assert (tmp_path / 'real/PARSED_MODEL_JSON.json').exists()
        assert not (tmp_path / 'real/DAILY_REPORT.md').exists()
        if outcome in ('confirmed_QA','section_QA'):
            assert daily.read(tmp_path/'real/AUTOMATIC_VALIDATION.json')['confirmed_blockers']>0
    if outcome=='section_QA':
        findings=daily.read(tmp_path/'real/focus/QA_FINDINGS.json')['findings']
        assert any(f['field_path']=='daily_sections[0].text'
                   and f['discovery_origin']=='automatic_narrow_rule' for f in findings)
