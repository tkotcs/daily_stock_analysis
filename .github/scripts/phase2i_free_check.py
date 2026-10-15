"""Bounded, read-only native Yahoo probe. No model, notification or old cache."""
import argparse
import datetime as dt
import json
import math
import os
import pathlib
import platform
import sys
import time
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = pathlib.Path(args.out).resolve(); out.mkdir(exist_ok=False)
    for name in list(os.environ):
        if any(s in name for s in ('API_KEY', 'PASSWORD', 'ACCESS_TOKEN', 'WEBHOOK')):
            os.environ.pop(name, None)
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    import pandas as pd
    import yfinance as yf
    import curl_cffi.requests as curl
    from data_provider.yfinance_fetcher import YfinanceFetcher
    from data_provider.yfinance_fundamental_adapter import (
        YfinanceFundamentalAdapter, _pick_row, _latest_value,
        _INCOME_REVENUE_KEYS, _INCOME_NET_PROFIT_KEYS, _CASHFLOW_OP_KEYS,
    )
    from src.core.trading_calendar import get_effective_trading_date
    from free_market_validation import WATCHLIST
    started = time.monotonic(); trace = []; circuit = []; results = []
    now = dt.datetime.now(dt.timezone.utc)
    target = get_effective_trading_date('us', current_time=now).isoformat()
    end = (dt.date.fromisoformat(target) + dt.timedelta(days=1)).isoformat()
    original = curl.Session.request
    active = {'code': None}; raw = {}

    def request(session, method, url, *a, **kw):
        parsed = urlsplit(str(url)); host = parsed.hostname or ''
        if method.upper() != 'GET' or not (host == 'yahoo.com' or host.endswith('.yahoo.com')):
            raise RuntimeError('only_free_yahoo_GET_allowed')
        if circuit or time.monotonic() - started > 480:
            raise RuntimeError('circuit_or_deadline_no_request')
        kw['timeout'] = min(float(kw.get('timeout') or 12), 12)
        kw['allow_redirects'] = False
        record = {'code': active['code'], 'at': dt.datetime.now(dt.timezone.utc).isoformat(),
                  'method': 'GET', 'host': host, 'path': parsed.path}
        begin = time.monotonic()
        try:
            response = original(session, method, url, *a, **kw)
            record['status'] = response.status_code
            record['retry_after'] = response.headers.get('Retry-After')
            if response.status_code in (403, 429):
                circuit.append({'status': response.status_code, 'retry_after': record['retry_after']})
            # Persist public source bodies only, never authentication/crumb/cookies.
            if '/finance/chart/' in parsed.path or '/fundamentals-timeseries/' in parsed.path or '/quoteSummary/' in parsed.path:
                (out / f'http-{len(trace):04d}.json').write_bytes(response.content)
            return response
        except Exception as exc:
            record['error'] = type(exc).__name__; raise
        finally:
            record['seconds'] = round(time.monotonic() - begin, 3); trace.append(record)

    curl.Session.request = request
    original_ticker = yf.Ticker

    class Recorder:
        def __init__(self, code): self.inner = original_ticker(code)
        def get_info(self):
            value = self.inner.get_info(); raw['info'] = value; return value
        def __getattr__(self, name):
            value = getattr(self.inner, name)
            if name in ('quarterly_income_stmt', 'quarterly_cashflow', 'dividends'):
                raw[name] = value
            return value

    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    for code in WATCHLIST:
        begin = time.monotonic(); active['code'] = code; raw = {}
        row = {'code': code, 'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
               'target_session': target, 'provider': 'Yahoo/yfinance', 'auto_adjust': True,
               'quote_valid': False, 'rows': 0, 'financial_fields': {}, 'errors': []}
        row['provider_symbol'] = YfinanceFetcher()._convert_stock_code(code)
        before = len(trace)
        if circuit or time.monotonic() - started > 480:
            row['errors'] = ['not_attempted_after_access_restriction' if circuit else 'not_attempted_after_deadline']
        else:
            try:
                # Same native fetcher API as the accepted prefill, isolated from its database.
                df = YfinanceFetcher().get_daily_data(code, end_date=end, days=90)
                df.to_csv(out / (code + '-daily.csv'), index=False)
                row['rows'] = len(df)
                values = df[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric, errors='coerce')
                valid = values.apply(lambda s: s.map(lambda v: pd.notna(v) and math.isfinite(v))).all(axis=1)
                valid &= (values[['open', 'high', 'low', 'close']] > 0).all(axis=1) & (values.volume >= 0)
                valid &= (values.low <= values[['open', 'close']].min(axis=1)) & (values.high >= values[['open', 'close']].max(axis=1)) & (values.low <= values.high)
                dates = pd.to_datetime(df.date)
                row['latest_date'] = dates.max().date().isoformat()
                row['valid_ohlcv_rows'] = int(valid.sum())
                row['quote_valid'] = bool(valid.all() and len(df) >= 60 and dates.is_unique and dates.is_monotonic_increasing and row['latest_date'] == target)
                if not row['quote_valid']: row['errors'].append('history_or_freshness_or_ohlcv_invalid')
            except Exception as exc: row['errors'].append('quote:' + type(exc).__name__)
            if not circuit:
                yf.Ticker = Recorder
                try:
                    bundle = YfinanceFundamentalAdapter().get_fundamental_bundle(code)
                    save(code + '-fundamental.json', bundle)
                    info = raw.get('info') or {}; save(code + '-info.json', info)
                    row['identity'] = {k: info.get(k) for k in ('symbol', 'longName', 'exchange', 'quoteType', 'currency', 'financialCurrency')}
                    report = (bundle.get('earnings') or {}).get('financial_report') or {}
                    for field, table, keys in [('revenue', 'quarterly_income_stmt', _INCOME_REVENUE_KEYS), ('net_profit_parent', 'quarterly_income_stmt', _INCOME_NET_PROFIT_KEYS), ('operating_cash_flow', 'quarterly_cashflow', _CASHFLOW_OP_KEYS)]:
                        frame = raw.get(table)
                        series = _pick_row(frame, keys) if frame is not None else None
                        direct = _latest_value(series)
                        finite = series.dropna() if series is not None else None
                        period = str(finite.index[0]) if finite is not None and not finite.empty else None
                        row['financial_fields'][field] = {'value': report.get(field), 'direct_value': direct,
                            'period_end': period, 'adapter_report_date': report.get('report_date'),
                            'currency': report.get('currency'), 'source': 'yfinance.' + table if direct is not None else 'Yahoo_info_fallback_or_estimate',
                            'officially_verified': False, 'publication_at': None,
                            'missing': report.get(field) is None,
                            'estimated': field == 'net_profit_parent' and direct is None and report.get(field) is not None,
                            'ttm_or_unknown_fallback': field != 'net_profit_parent' and direct is None and report.get(field) is not None,
                            'source_url': f'https://finance.yahoo.com/quote/{row["provider_symbol"]}/financials/' if table == 'quarterly_income_stmt' else f'https://finance.yahoo.com/quote/{row["provider_symbol"]}/cash-flow/'}
                    for table in ('quarterly_income_stmt', 'quarterly_cashflow'):
                        if raw.get(table) is not None: raw[table].to_csv(out / (code + '-' + table + '.csv'))
                    row['adapter_errors'] = bundle.get('errors', [])
                except Exception as exc: row['errors'].append('financial:' + type(exc).__name__)
                finally: yf.Ticker = original_ticker
            else: row['errors'].append('financial_not_attempted_after_access_restriction')
        row['requests'] = len(trace) - before
        row['seconds'] = round(time.monotonic() - begin, 3)
        results.append(row); save('RESULTS.json', results); save('HTTP_TRACE.json', trace)
        print(code, row['quote_valid'], row['rows'], row['requests'], flush=True)
        if not circuit: time.sleep(1)
    curl.Session.request = original
    save('SUMMARY.json', {'observed_at': now.isoformat(), 'target_session': target,
         'environment': platform.platform(), 'valid_quotes': sum(r['quote_valid'] for r in results),
         'total': len(results), 'requests': len(trace), 'circuit': circuit,
         'seconds': round(time.monotonic() - started, 3), 'paid_POSTs': 0, 'emails': 0,
         'old_market_cache_used': False, 'security_identity_fully_verified': False})


if __name__ == '__main__': main()
