"""Manual evidence only: original provider API plus isolated Yahoo Class-B probe.

Never patches provider routing, persists prices into the CLI database, or runs AI.
"""
import argparse
import json
import math
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from free_market_validation import Limits, SafetyStop, WATCHLIST, NAMES, ETFS, ROOT

LISTING_DATES = {'SPCX': '2026-06-12', 'SKHY': '2026-07-10'}


def validate_rows(rows, target, expected_dates):
    errors = []
    dates = [r['date'] for r in rows]
    if len(rows) < 60:
        errors.append('fewer_than_60_complete_bars')
    if len(set(dates)) != len(dates):
        errors.append('duplicate_dates')
    if not dates or max(dates) != target:
        errors.append('latest_completed_session_missing')
    if set(dates) != set(expected_dates):
        errors.append('missing_or_non_session_dates')
    for r in rows:
        values = [r.get(k) for k in ('open', 'high', 'low', 'close', 'volume')]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            errors.append('invalid_ohlcv'); break
        o, h, l, c, v = values
        if min(o, h, l, c) <= 0 or v <= 0 or not l <= min(o, c) <= max(o, c) <= h:
            errors.append('ohlcv_order_or_sign'); break
    return sorted(set(errors))


def match_source(rows, charts, symbol):
    matches = 0
    for r in rows:
        matched = False
        for chart in charts:
            if chart.get('meta', {}).get('symbol') != symbol:
                continue
            q = (chart.get('indicators', {}).get('quote') or [{}])[0]
            adj = (chart.get('indicators', {}).get('adjclose') or [{}])[0].get('adjclose', [])
            for i, stamp in enumerate(chart.get('timestamp', [])):
                if datetime.fromtimestamp(stamp, ZoneInfo('America/New_York')).date().isoformat() != r['date']:
                    continue
                try:
                    factor = adj[i] / q['close'][i] if len(adj) > i and adj[i] is not None else 1
                    matched = all(math.isclose(r[k], q[k][i] * (1 if k == 'volume' else factor), rel_tol=1e-6, abs_tol=1e-5) for k in ('open', 'high', 'low', 'close', 'volume'))
                except (KeyError, IndexError, TypeError, ZeroDivisionError):
                    pass
                if matched:
                    break
            if matched:
                break
        matches += int(matched)
    return matches


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    a = p.parse_args()
    out = pathlib.Path(a.out).resolve(); out.mkdir(exist_ok=False)
    started = datetime.now(timezone.utc); clock = time.monotonic()
    credentials = [k for k, v in os.environ.items() if v and (k.endswith(('_API_KEY', '_API_KEYS', '_PASSWORD', '_ACCESS_TOKEN', '_APP_SECRET')) or k in ('TUSHARE_TOKEN', 'MODELFLARE_KEY', 'AIHUBMIX_KEY', 'TELEGRAM_BOT_TOKEN'))]
    if credentials or (ROOT / '.env').exists():
        raise SafetyStop('credential_or_env_file_present')
    os.environ.update(DATABASE_PATH=str(out / 'unused-fresh.sqlite'), LOG_DIR=str(out / 'logs'), SCHEDULE_ENABLED='false', MARKET_REVIEW_ENABLED='false', DAILY_MARKET_CONTEXT_ENABLED='false', AGENT_MODE='false', SINGLE_STOCK_NOTIFY='false', SEARXNG_PUBLIC_INSTANCES_ENABLED='false', ENABLE_CHIP_DISTRIBUTION='false', LITELLM_LOCAL_MODEL_COST_MAP='True')
    sys.path.insert(0, str(ROOT))
    from src.core.trading_calendar import get_effective_trading_date, _XCALS_AVAILABLE
    if not _XCALS_AVAILABLE:
        raise SafetyStop('calendar_dependency_missing')
    import exchange_calendars as xc
    from data_provider import DataFetcherManager, YfinanceFetcher
    import yfinance as yf
    limits = Limits(out); limits.install()
    target = get_effective_trading_date('us', current_time=started).isoformat()
    end = (datetime.fromisoformat(target) + timedelta(days=1)).date().isoformat()
    start = (datetime.fromisoformat(end) - timedelta(days=180)).date().isoformat()
    calendar = xc.get_calendar('XNYS')
    manager = DataFetcherManager()
    fetcher = YfinanceFetcher()
    mappings = {c: fetcher._convert_stock_code(c) for c in WATCHLIST}
    mappings['literal_BRK-B'] = fetcher._convert_stock_code('BRK-B')
    statuses = []; all_rows = []; charts = []; stopped = False
    for code in WATCHLIST:
        before = len(limits.http); begin = time.monotonic()
        diagnostic = code == 'BRK.B'; yf_symbol = 'BRK-B' if diagnostic else mappings[code]
        rows = []; failure = None
        try:
            if stopped:
                raise SafetyStop('earlier_safety_stop')
            if diagnostic:
                raw = yf.Ticker('BRK-B').history(start=start, end=end, interval='1d', auto_adjust=True, actions=False, timeout=20, raise_errors=True)
                # Evidence columns only. No write-back or alias patch to upstream.
                for index, row in raw.iterrows():
                    rows.append({'date': index.date().isoformat(), **{k: float(row[k.title()]) for k in ('open', 'high', 'low', 'close', 'volume')}})
                provider = 'Yahoo/yfinance isolated Class-B diagnostic (not original CLI routing)'
            else:
                df, provider = manager.get_daily_data(code, end_date=end, days=90)
                for _, row in df.iterrows():
                    rows.append({'date': str(row['date'])[:10], **{k: float(row[k]) for k in ('open', 'high', 'low', 'close', 'volume')}})
            rows.sort(key=lambda r: r['date'])
        except BaseException as e:
            provider = None; failure = type(e).__name__ + ':' + str(e)
            if isinstance(e, SafetyStop):
                stopped = True
        for item in limits.http[before:]:
            if item.get('response_file'):
                payload = json.loads((out / item['response_file']).read_text(encoding='utf-8'))
                charts.extend(payload.get('chart', {}).get('result') or [])
        meta = next((c.get('meta', {}) for c in reversed(charts) if c.get('meta', {}).get('symbol') == yf_symbol), {})
        listing = LISTING_DATES.get(code)
        pre_listing = [r for r in rows if listing and r['date'] < listing]
        eligible = [r for r in rows if start <= r['date'] <= target and (not listing or r['date'] >= listing)]
        lower = max(start, listing or start)
        expected = [d.date().isoformat() for d in calendar.sessions_in_range(lower, target)]
        errors = validate_rows(eligible, target, expected)
        if pre_listing:
            errors.append('unexpected_pre_listing_prices')
        name = meta.get('longName') or meta.get('shortName')
        if not name or not re.search(NAMES[code], name, re.I):
            errors.append('identity_name_missing_or_wrong')
        if meta.get('symbol') != yf_symbol or meta.get('currency') != 'USD' or meta.get('exchangeTimezoneName') != 'America/New_York':
            errors.append('identity_symbol_currency_timezone')
        if meta.get('instrumentType') != ('ETF' if code in ETFS else 'EQUITY'):
            errors.append('identity_type')
        matched = match_source(eligible, charts, yf_symbol)
        if matched != len(eligible) or not eligible:
            errors.append('source_ohlcv_not_fully_matched')
        if failure:
            errors.append('fetch_failure')
        status = {'symbol': code, 'requested_yahoo_symbol': yf_symbol, 'original_conversion': mappings[code], 'diagnostic_only': diagnostic, 'provider': provider, 'metadata': meta, 'valid': not errors, 'errors': sorted(set(errors)), 'failure': failure, 'raw_rows': len(rows), 'complete_valid_window_rows': len(eligible), 'expected_session_count': len(expected), 'source_matched_rows': matched, 'pre_listing_rows': len(pre_listing), 'first_date': min((r['date'] for r in eligible), default=None), 'last_date': max((r['date'] for r in eligible), default=None), 'target_session': target, 'http_requests': len(limits.http) - before, 'seconds': round(time.monotonic() - begin, 3), 'fetched_this_run': True, 'cache_restored': False}
        statuses.append(status)
        all_rows.append({'symbol': code, 'raw_rows': rows, 'complete_window_rows': eligible})
        print(json.dumps({k: status[k] for k in ('symbol', 'valid', 'complete_valid_window_rows', 'errors')}, ensure_ascii=False), flush=True)
        time.sleep(0.25)
    safety = all(v == 0 for v in limits.calls.values())
    summary = {'started_at': started.isoformat(), 'ended_at': datetime.now(timezone.utc).isoformat(), 'seconds': round(time.monotonic() - clock, 3), 'run_id': os.getenv('GITHUB_RUN_ID'), 'commit': os.getenv('GITHUB_SHA'), 'runner_os': os.getenv('RUNNER_OS'), 'start_inclusive': start, 'end_exclusive': end, 'target_session': target, 'provider_parameter_days': 90, 'calendar_window_days': 180, 'min_complete_bars': 60, 'valid_data_availability': sum(s['valid'] for s in statuses), 'original_provider_valid': sum(s['valid'] and not s['diagnostic_only'] for s in statuses), 'total': len(WATCHLIST), 'native_cli_executed': False, 'brkb_cli_mapping_fixed': False, 'safety_passed': safety, 'attempt_counters': limits.calls, 'http_requests': len(limits.http), 'http_status_counts': {str(k): sum(h.get('http_status') == k for h in limits.http) for k in sorted({h['http_status'] for h in limits.http if 'http_status' in h})}, 'rate_limited': limits.yahoo_rate_limited, 'paid_requests': 0, 'emails_sent': 0, 'passed': safety and all(s['valid'] for s in statuses)}
    for name, value in [('summary.json', summary), ('statuses.json', statuses), ('daily-rows.json', all_rows), ('http-trace.json', limits.http), ('conversion-map.json', mappings), ('denied-outbound.json', limits.denied)]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
