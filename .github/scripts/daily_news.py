"""One GET per configured official feed; retain raw bytes and admit dated metadata only."""
import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from free_market_validation import WATCHLIST
from manual_responses_candidate import hosted_endpoint


def aware_date(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        result = parsedate_to_datetime(value)
    if result.utcoffset() is None:
        raise ValueError('publication_timezone_missing')
    return result


def parse_feed(raw, feed, fetched_at, *, limit=3):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('RSS_DTD_or_entities_rejected')
    tree = ET.fromstring(raw)
    admitted, rejected, seen = [], [], set()
    for index, node in enumerate(n for n in tree.iter()
                                  if n.tag.rsplit('}', 1)[-1] in ('item', 'entry')):
        try:
            children = {}
            for child in node:
                key = child.tag.rsplit('}', 1)[-1]
                children.setdefault(key, child)
            title = ''.join(children['title'].itertext()).strip()
            link = children['link']
            url = link.attrib.get('href') or (link.text or '').strip()
            # updated is a revision time, not a publication timestamp.
            publication = children.get('pubDate')
            if publication is None:
                publication = children.get('published')
            if publication is None or not publication.text:
                raise ValueError('publication_timestamp_missing')
            published = aware_date(publication.text.strip())
            if not fetched_at - timedelta(days=3) <= published <= fetched_at:
                raise ValueError('publication_outside_three_day_window')
            hosted_endpoint(url)
            if not title:
                raise ValueError('headline_missing')
            if url in seen:
                raise ValueError('duplicate_article_URL')
            seen.add(url)
            admitted.append(dict(source=feed['source'], publisher=feed['source'],
                url=url, title=title, published_at=published.isoformat(),
                fetched_at=fetched_at.isoformat(), content_kind='metadata_only',
                content_sha256=None, original_HTTP_sha256=hashlib.sha256(raw).hexdigest(),
                source_scope='configured_publisher_feed_only_not_comprehensive_search'))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            rejected.append(dict(index=index, reason=str(error)))
    admitted.sort(key=lambda item: aware_date(item['published_at']), reverse=True)
    if len(admitted) > limit:
        rejected.extend(dict(url=item['url'], reason='top_n_limit') for item in admitted[limit:])
    return admitted[:limit], rejected


def capture(config_path, out):
    config = json.loads(config_path.read_bytes())
    feeds = config['feeds']
    symbols = [item['symbol'] for item in feeds]
    if (config.get('max_GETs_per_feed') != 1 or not 1 <= config.get('max_items_per_symbol', 0) <= 3
            or not 1 <= len(symbols) <= 3 or len(symbols) != len(set(symbols))
            or any(symbol not in WATCHLIST for symbol in symbols)):
        raise ValueError('reviewed_feed_limits_required')
    for feed in feeds:
        hosted_endpoint(feed['url'])
    out.mkdir(parents=True, exist_ok=False)
    packet, receipts = {symbol: [] for symbol in WATCHLIST}, []
    import httpx
    with httpx.Client(transport=httpx.HTTPTransport(retries=0), follow_redirects=False,
                      trust_env=False, timeout=25) as client:
        for feed in feeds:
            receipt = dict(symbol=feed['symbol'], url=feed['url'], attempts=1,
                           retries=0, redirects_followed=False, response_complete=False)
            raw = bytearray()
            try:
                with client.stream('GET', feed['url'], headers={'User-Agent': 'DSA daily RSS metadata'}) as response:
                    receipt['HTTP_status'] = response.status_code
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000:
                            raise ValueError('feed_size_limit')
                receipt['response_complete'] = True
                fetched = datetime.now(timezone.utc)
                receipt.update(fetched_at=fetched.isoformat(), bytes=len(raw),
                               sha256=hashlib.sha256(raw).hexdigest())
                if receipt['HTTP_status'] != 200:
                    raise ValueError('feed_HTTP_failure_no_retry')
                accepted, rejected = parse_feed(bytes(raw), feed, fetched,
                                               limit=config['max_items_per_symbol'])
                packet[feed['symbol']] = accepted
                receipt.update(accepted=len(accepted), rejected=rejected)
            except Exception as error:
                receipt['error'] = str(error) if type(error) is ValueError else type(error).__name__
            receipt.setdefault('fetched_at', datetime.now(timezone.utc).isoformat())
            receipt.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            (out / (feed['symbol'] + '.xml')).write_bytes(raw)
            receipts.append(receipt)
    result = dict(configured_symbols=symbols, universe_count=len(WATCHLIST), captures=receipts,
                  model_POSTs=0, search_performed=False, comprehensive_news_coverage=False,
                  other_symbols_have_no_configured_feed=True)
    (out / 'NEWS_PACKET.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2), 'utf-8')
    (out / 'CAPTURES.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = capture(args.config, args.out)
    print(json.dumps(dict(GET_attempts=len(result['captures']), model_POSTs=0,
                          comprehensive_news_coverage=False)))


if __name__ == '__main__':
    main()
