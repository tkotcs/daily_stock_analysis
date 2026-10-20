"""Synthetic RSS fixtures; these tests never request publisher pages."""
from datetime import datetime, timezone
import json

import pytest

from daily_news import parse_feed, capture

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
FEED = dict(symbol='NVDA', source='SYNTHETIC publisher', url='https://example.test/feed')


def rss(items):
    return ('<rss><channel>' + ''.join(
        '<item><title>SYNTHETIC headline</title><link>https://example.test/' + name +
        '</link>' + ('<pubDate>' + date + '</pubDate>' if date else '') +
        '<description>DO NOT TREAT THIS AS SAVED FULL TEXT</description></item>'
        for name, date in items) + '</channel></rss>').encode()


def test_valid_metadata_stale_missing_future_and_duplicates_have_distinct_receipts():
    raw = rss([
        ('good', 'Tue, 20 Oct 2026 08:00:00 +0000'),
        ('good', 'Tue, 20 Oct 2026 08:00:00 +0000'),
        ('old', 'Fri, 16 Oct 2026 08:00:00 +0000'),
        ('missing', None),
        ('future', 'Wed, 21 Oct 2026 08:00:00 +0000'),
        ('zone', '2026-10-20T08:00:00'),
    ])
    accepted, rejected = parse_feed(raw, FEED, NOW)
    assert len(accepted) == 1
    assert accepted[0]['content_kind'] == 'metadata_only'
    assert 'text' not in accepted[0] and 'description' not in accepted[0]
    assert accepted[0]['fetched_at'] == NOW.isoformat()
    assert {r['reason'] for r in rejected} == {
        'duplicate_article_URL', 'publication_outside_three_day_window',
        'publication_timestamp_missing', 'publication_timezone_missing'}


def test_revision_only_atom_entry_is_not_promoted_to_publication_time():
    xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>SYNTHETIC</title><link href="https://example.test/a"/><updated>2026-10-20T08:00:00Z</updated></entry></feed>'
    accepted, rejected = parse_feed(xml, FEED, NOW)
    assert accepted == [] and rejected[0]['reason'] == 'publication_timestamp_missing'


def test_top_n_uses_actual_instants_across_timezone_offsets():
    raw = rss([('earlier', '2026-10-20T10:00:00+03:00'),
               ('later', '2026-10-20T08:30:00+00:00')])
    accepted, rejected = parse_feed(raw, FEED, NOW, limit=1)
    assert accepted[0]['url'].endswith('/later')
    assert rejected[-1]['reason'] == 'top_n_limit'


def test_dtd_is_refused_before_xml_expansion():
    with pytest.raises(ValueError, match='DTD'):
        parse_feed(b'<!DOCTYPE rss [<!ENTITY x "x">]><rss/>', FEED, NOW)


@pytest.mark.parametrize('failure', ['429', '503', 'timeout'])
def test_feed_failure_is_not_retried_or_reported_as_no_company_events(tmp_path, monkeypatch, failure):
    import httpx
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(dict(max_GETs_per_feed=1, max_items_per_symbol=3, feeds=[FEED])))
    events = []
    class Response:
        status_code = int(failure) if failure != 'timeout' else 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_bytes(self):
            yield b'SYNTHETIC rate limit'
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['transport']._pool._retries == 0 and not kwargs['follow_redirects']
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def stream(self, method, *args, **kwargs):
            assert method == 'GET'
            events.append('GET')
            if failure == 'timeout':
                raise httpx.ReadTimeout('SYNTHETIC timeout')
            return Response()
    monkeypatch.setattr(httpx, 'Client', Client)
    out = tmp_path / 'source'
    result = capture(config, out)
    assert events == ['GET'] and result['model_POSTs'] == 0
    if failure != 'timeout':
        assert result['captures'][0]['HTTP_status'] == int(failure)
    else:
        assert result['captures'][0]['response_complete'] is False
    assert len(result['captures'][0]['sha256']) == 64
    assert result['comprehensive_news_coverage'] is False
    assert (out / 'NVDA.xml').read_bytes() == (b'' if failure == 'timeout' else b'SYNTHETIC rate limit')
    assert json.loads((out / 'NEWS_PACKET.json').read_bytes())['NVDA'] == []
