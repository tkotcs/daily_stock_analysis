"""Synthetic survival paths; no real provider, SMTP or paid model requests."""
import copy
from datetime import datetime, timezone, timedelta
import json

import pytest

import daily_briefing as daily
import daily_delivery as delivery
import daily_news
from mvp_three import reconcile_missing_close
from test_daily_briefing import NOW, SESSION, SOURCE, PROFILE, fixture_capture
from test_daily_automatic import automatic_env


def charts():
    stamp = int(datetime(2026, 10, 19, 13, 30, tzinfo=timezone.utc).timestamp())
    chart = dict(meta=dict(symbol='AAPL', currency='USD', dataGranularity='1d',
                          exchangeTimezoneName='America/New_York', instrumentType='EQUITY'),
                 timestamp=[stamp], indicators=dict(
                     quote=[dict(open=[100.], high=[104.], low=[99.], close=[None], volume=[1000])],
                     adjclose=[dict(adjclose=[None])]))
    other = copy.deepcopy(chart)
    other['timestamp'] = [stamp+23400]
    other['indicators']['quote'][0]['close'] = [103.]
    other['indicators']['adjclose'][0]['adjclose'] = [102.]
    return dict(chart=dict(result=[chart])), other


@pytest.mark.parametrize('bad', [None, 'symbol', 'currency', 'interval', 'OHLV',
                                'adjclose', 'future', 'disagree'])
def test_daily_close_reconciliation_requires_matching_complete_saved_bar(bad):
    payload, other = charts()
    originals = copy.deepcopy(payload), copy.deepcopy(other)
    now = NOW
    if bad == 'symbol': other['meta']['symbol'] = 'MSFT'
    if bad == 'currency': other['meta']['currency'] = 'HKD'
    if bad == 'interval': other['meta']['dataGranularity'] = '1m'
    if bad == 'OHLV': other['indicators']['quote'][0]['volume'][0] = 999
    if bad == 'adjclose': other['indicators']['adjclose'][0]['adjclose'][0] = None
    if bad == 'future': now = datetime(2026, 10, 19, 19, tzinfo=timezone.utc)
    companions = [other]
    if bad == 'disagree':
        conflict = copy.deepcopy(other)
        conflict['indicators']['quote'][0]['close'][0] = 102.
        companions.append(conflict)
    fixed, changes = reconcile_missing_close(payload, companions, now)
    assert payload == originals[0]
    assert bool(changes) is (bad is None)
    if bad is None:
        assert other == originals[1]
        assert fixed['chart']['result'][0]['indicators']['quote'][0]['close'] == [103.]
        assert fixed['chart']['result'][0]['indicators']['adjclose'][0]['adjclose'] == [102.]


def test_transport_exposes_reconciled_json_and_preserves_original_source(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import curl_cffi.requests as curl
    from mvp_three import install_capture_transport
    payload, other = charts()
    responses = iter([dict(chart=dict(result=[other])), payload])
    monkeypatch.setattr(curl.Session, 'request', lambda *a, **kw:
                        SimpleNamespace(status_code=200, json=lambda: next(responses)))
    trace = install_capture_transport(tmp_path)
    client = curl.Session()
    client.get('https://query2.finance.yahoo.com/v8/finance/chart/AAPL')
    response = client.get('https://query2.finance.yahoo.com/v8/finance/chart/AAPL')
    assert response.json()['chart']['result'][0]['indicators']['quote'][0]['close'] == [103.]
    raw = json.loads((tmp_path/trace[-1]['response_file']).read_bytes())
    fixed = json.loads((tmp_path/trace[-1]['reconciled_file']).read_bytes())
    assert raw == payload and fixed != raw
    assert trace[-1]['reconciliation'][0]['fields'] == ['close', 'adjclose']


def feed(folder, *, raw_change=False, old=False):
    folder.mkdir()
    config = daily.read(daily_news.Path(daily_news.__file__).resolve().parents[1] /
                        'research/daily-news-feeds.json')
    spec = config['feeds'][0]
    fetched = NOW-timedelta(days=4) if old else NOW
    raw = (b'<rss><channel><item><title>SYNTHETIC official headline</title>'
           b'<link>https://nvidianews.nvidia.com/news/synthetic</link>'
           b'<pubDate>2026-10-20T08:00:00Z</pubDate></item></channel></rss>')
    (folder/'NVDA.xml').write_bytes(raw+b'changed' if raw_change else raw)
    daily.save(folder/'CAPTURES.json', dict(captures=[dict(
        symbol='NVDA', url=spec['url'], fetched_at=fetched.isoformat(),
        HTTP_status=200, response_complete=True, sha256=daily.sha(raw))]))


@pytest.mark.parametrize('bad', [None, 'raw_change', 'old'])
def test_news_survives_all_price_failures_but_requires_current_raw_hash(tmp_path, bad):
    feed(tmp_path/'daily-news', raw_change=bad == 'raw_change', old=bad == 'old')
    text, audit = delivery.partial_content(tmp_path, SESSION, NOW)
    assert audit['valid_rows'] == 0
    assert audit['headlines'] == (1 if bad is None else 0)
    if bad is None:
        assert 'SYNTHETIC official headline' in text and '仅官网标题元数据' in text
        assert '错误说明' not in text and '待一次综合模型生成' not in text
    else:
        assert text is None


def test_one_bad_stock_does_not_remove_other_valid_rows(tmp_path):
    capture = fixture_capture(tmp_path/'daily-capture')
    ctx = daily.read(capture/'AAPL/NATIVE_CONTEXT.json')
    ctx['fixture_only'] = True
    daily.save(capture/'AAPL/NATIVE_CONTEXT.json', ctx)
    daily.source_check(SOURCE)
    text, audit = delivery.partial_content(tmp_path, SESSION, NOW)
    assert audit['valid_rows'] == 2
    assert '| MSFT |' in text and '| QQQ |' in text and '| AAPL |' not in text
    assert 'SYNTHETIC_failure' not in text
    text, audit = delivery.partial_content(tmp_path, SESSION, NOW+timedelta(days=2))
    assert text is None and audit['valid_rows'] == 0


def partial_model(tmp_path, monkeypatch):
    automatic_env(tmp_path, monkeypatch)
    data = fixture_capture(tmp_path/'daily-capture')
    ready = tmp_path/'daily-ready'
    daily.prepare(data, SOURCE, PROFILE, ready, SESSION, now=NOW, automatic=True)
    child = tmp_path/'daily-real'
    child.mkdir()
    daily.save(child/'STATUS.json', dict(
        status='failed_no_retry', actual_model_POST_attempts=1,
        reason='automatic_confirmed_quality_blocker_no_mail_no_retry'))
    authority = delivery.execution_authority(automatic=True)
    daily.save(child/'AUTHORIZATION_USED.json', dict(
        batch_sha256=daily.sha((ready/'DAILY_LOCK.json').read_bytes()),
        run_id='987654', target_session=SESSION, execution_authority=authority))
    model = dict(focus_symbol='AAPL', dashboard=dict(battle_plan=dict(
        risk_plan=dict(mode='watch', max_position_pct=0, scenarios=[]))),
        analysis_summary='SYNTHETIC useful explanation', risk_warning='SYNTHETIC risk',
        ma_analysis='当前MA5<MA10<MA20<MA60',
        daily_sections=[
            dict(title=daily.SECTIONS[0], text='SYNTHETIC useful section', sources=['context:AAPL']),
            dict(title=daily.SECTIONS[1], text='SYNTHETIC invalid citation', sources=['news:invented:0']),
            dict(title=daily.SECTIONS[2], text='当前MA5<MA10<MA20<MA60', sources=['context:AAPL'])])
    daily.save(child/'PARSED_MODEL_JSON.json', model)
    response = dict(status='completed', model='gpt-6.1-sol', output=[dict(
        type='message', content=[dict(type='output_text', text=json.dumps(model))])])
    (child/'RAW_RESPONSE_BODY.bin').write_bytes(
        ('data: '+json.dumps(dict(type='response.completed', response=response))+'\n').encode())
    import manual_responses_once
    monkeypatch.setattr(manual_responses_once, 'check_time', lambda *a: None)
    monkeypatch.setattr(daily, 'check_time', lambda *a: None)
    return child


@pytest.mark.parametrize('bad', [None, 'incomplete', 'binding', 'model_changed'])
def test_complete_model_filters_bad_units_and_keeps_good_text(tmp_path, monkeypatch, bad):
    child = partial_model(tmp_path, monkeypatch)
    if bad == 'incomplete':
        (child/'RAW_RESPONSE_BODY.bin').write_bytes(b'data: {"type":"response.incomplete"}\n')
    if bad == 'binding':
        auth = daily.read(child/'AUTHORIZATION_USED.json')
        auth['run_id'] = 'other'
        daily.save(child/'AUTHORIZATION_USED.json', auth)
    if bad == 'model_changed':
        model = daily.read(child/'PARSED_MODEL_JSON.json')
        model['analysis_summary'] = 'CHANGED'
        daily.save(child/'PARSED_MODEL_JSON.json', model)
    kept, removed = delivery.surviving_model(tmp_path, SESSION, NOW)
    text = json.dumps(kept)
    if bad is None:
        assert 'SYNTHETIC useful section' in text and 'SYNTHETIC useful explanation' in text
        assert 'invalid citation' not in text and 'MA5<' not in text
        assert 'ma_analysis' in removed and 'daily_sections[2].text' in removed
    else:
        assert kept == []


def test_partial_delivery_recomputes_content_then_uses_one_mail_claim(tmp_path, monkeypatch):
    from test_daily_delivery import setup
    setup(tmp_path, monkeypatch, 'upstream_overloaded_no_retry')
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    monkeypatch.setattr(delivery, 'datetime', Clock)
    feed(tmp_path/'daily-news')
    import daily_briefing_mail as mail
    import remote_execution_claim as remote
    monkeypatch.setattr(mail, 'source_check', lambda *a: None)
    monkeypatch.setattr(remote, 'GitHubAPI', lambda *a: None)
    events = []
    class Claim:
        def __init__(self, api, key, *a, **kw):
            assert key == daily.sha(('DSA:daily-mail:v1:'+SESSION).encode())
        def reserve(self, *a): events.append('claim'); return {}
        def before_send(self, *a): events.append('before_send')
    monkeypatch.setattr(remote, 'RemoteExecutionClaim', Claim)
    daily.source_check(SOURCE)
    import src.notification_sender.email_sender as sender
    def send(self, text, **kw):
        events.append('SMTP')
        assert 'SYNTHETIC official headline' in text
        assert kw['subject'] == '美股晨报（可用内容版）｜'+SESSION
        return True
    monkeypatch.setattr(sender.EmailSender, 'send_to_email', send)
    status = delivery.deliver_daily(tmp_path, SOURCE, tmp_path/'mail-result')
    assert status['status'] == 'delivered' and status['delivery_kind'] == 'partial_research'
    assert events == ['claim', 'before_send', 'SMTP']
    with pytest.raises(ValueError, match='mail_state_exists_no_retry'):
        delivery.deliver_daily(tmp_path, SOURCE, tmp_path/'mail-result')


def test_source_changes_before_smtp_block_the_partial_mail(tmp_path, monkeypatch):
    from test_daily_delivery import setup
    setup(tmp_path, monkeypatch)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    monkeypatch.setattr(delivery, 'datetime', Clock)
    feed(tmp_path/'daily-news')
    import daily_briefing_mail as mail
    original = mail.deliver
    def changed(report, source, out, digest, **kwargs):
        (tmp_path/'daily-news/NVDA.xml').write_bytes(b'changed_source')
        return original(report, source, out, digest, **kwargs)
    monkeypatch.setattr(mail, 'deliver', changed)
    import remote_execution_claim as remote
    monkeypatch.setattr(remote, 'RemoteExecutionClaim',
                        lambda *a, **kw: pytest.fail('changed source must not reserve or send'))
    result = delivery.deliver_daily(tmp_path, SOURCE, tmp_path/'mail-result')
    assert result['status'] == 'blocked_before_mail' and result['mail_attempts'] == 0
