"""Freeze one manual mode from a new native capture; never send requests."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
from decimal import Decimal

from authorized_once import WATCHLIST_BUSINESS, WATCHLIST_PROFILE, canonical_sha, verify_prices
from deepseek_post_guard import GuardStop
from free_market_validation import WATCHLIST


def mode_parameters(mode):
    if mode not in ('nonthinking', 'thinking'):
        raise GuardStop('watchlist_mode_invalid')
    return (32768, '0.06') if mode == 'thinking' else (16384, '0.03')


def batch_spec(lock):
    _, reservation = mode_parameters(lock.get('mode'))
    symbols = [member.get('symbol') for member in lock.get('members', [])]
    if not symbols or len(set(symbols)) != len(symbols) or symbols != [symbol for symbol in WATCHLIST if symbol in symbols]:
        raise GuardStop('watchlist_order_or_symbols_invalid')
    return WATCHLIST_BUSINESS, symbols, len(symbols), str(Decimal(reservation) * len(symbols))


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def load_set(bundle, approved_sha):
    raw = (bundle / 'WATCHLIST_LOCK.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != approved_sha:
        raise GuardStop('batch_hash_mismatch')
    lock = json.loads(raw)
    business, symbols, count, reservation = batch_spec(lock)
    limit, per_request = mode_parameters(lock['mode'])
    if lock.get('profile') != WATCHLIST_PROFILE or lock.get('business_commit') != business:
        raise GuardStop('watchlist_profile_invalid')
    if lock.get('authorize_paid_POST') is not False or lock.get('max_total_POSTs') != count or lock.get('max_POSTs_per_symbol') != 1 or lock.get('total_reservation_USD') != reservation:
        raise GuardStop('watchlist_call_limits_invalid')
    if lock.get('automatic_retry') is not False or lock.get('fallback') is not False:
        raise GuardStop('retry_or_fallback_forbidden')
    packets, contexts = {}, {}
    for member in lock['members']:
        symbol = member['symbol']
        body = (bundle / symbol / 'FINAL_REQUEST.json').read_bytes()
        context = (bundle / symbol / 'NATIVE_CONTEXT.json').read_bytes()
        packet = json.loads(body)
        if hashlib.sha256(body).hexdigest() != member.get('request_sha256') or canonical_sha(packet) != member.get('request_sha256'):
            raise GuardStop('full_request_hash_mismatch')
        if hashlib.sha256(context).hexdigest() != member.get('context_sha256') or json.loads(context).get('code') != symbol:
            raise GuardStop('context_identity_mismatch')
        expected_thinking = {'type': 'enabled' if lock['mode'] == 'thinking' else 'disabled'}
        if packet.get('model') != 'deepseek-flash' or packet.get('max_tokens') != limit or packet.get('thinking') != expected_thinking or packet.get('stream') is not True or packet.get('stream_options') != {'include_usage': True}:
            raise GuardStop('request_parameters_changed')
        if (lock['mode'] == 'thinking' and packet.get('reasoning_effort') != 'high') or (lock['mode'] == 'nonthinking' and 'reasoning_effort' in packet):
            raise GuardStop('watchlist_effort_invalid')
        if set(packet) - {'model', 'max_tokens', 'thinking', 'stream', 'stream_options', 'reasoning_effort', 'messages', 'temperature'}:
            raise GuardStop('unreviewed_request_parameters')
        if member.get('mode') != lock['mode'] or member.get('request_id') != symbol or member.get('reservation_USD') != per_request or member.get('reservation_check') is not True:
            raise GuardStop('watchlist_member_invalid')
        if canonical_sha(packet['messages']) != member.get('messages_sha256'):
            raise GuardStop('watchlist_messages_mismatch')
        packets[symbol], contexts[symbol] = packet, json.loads(context)
    if hashlib.sha256((bundle / 'OFFICIAL_PRICING.html').read_bytes()).hexdigest() != lock.get('pricing_sha256'):
        raise GuardStop('pricing_material_mismatch')
    return lock, packets, contexts


def prepare(data, source, out, mode, pricing, symbols=None, offline_only=False):
    limit, reservation = mode_parameters(mode)
    symbols = WATCHLIST if symbols is None else symbols
    batch_spec({'mode': mode, 'members': [{'symbol': symbol} for symbol in symbols]})
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip() != WATCHLIST_BUSINESS:
        raise GuardStop('watchlist_business_mismatch')
    capture = json.loads((data / 'RESULTS.json').read_text('utf-8'))
    expected_mode = 'SYNTHETIC_LOCAL_TEST' if offline_only else 'LIVE_FREE_DATA_MOCK_MODEL'
    if capture.get('business_commit') != WATCHLIST_BUSINESS or capture.get('mode') != expected_mode:
        raise GuardStop('new_native_capture_required')
    sys.path.insert(0, str(source))
    from src.core.trading_calendar import get_effective_trading_date
    import exchange_calendars as calendars
    import pandas as pd
    now = dt.datetime.now(dt.timezone.utc)
    target = get_effective_trading_date('us', current_time=now).isoformat()
    calendar = calendars.get_calendar('XNYS')
    pricing_raw = pricing.read_bytes()
    verify_prices(pricing_raw)
    members, files = [], []
    for symbol in symbols:
        directory = data / symbol
        status = json.loads((directory / 'STATUS.json').read_text('utf-8'))
        if status.get('status') != 'success_simulated_model' or status.get('session') != target or status.get('data_mode') != ('synthetic' if offline_only else 'fresh_Yahoo_this_run'):
            raise GuardStop('fresh_successful_capture_required')
        context = (directory / 'NATIVE_CONTEXT.json').read_bytes()
        context_value = json.loads(context)
        if context_value.get('code') != symbol or (not offline_only and context_value.get('fixture_only')):
            raise GuardStop('context_identity_mismatch')
        if str((context_value.get('today') or {}).get('date', ''))[:10] != target:
            raise GuardStop('context_session_mismatch')
        packet = copy.deepcopy(json.loads((directory / 'FINAL_REQUEST.json').read_text('utf-8')))
        if packet.get('model') != 'deepseek-flash' or not isinstance(packet.get('messages'), list) or not packet['messages']:
            raise GuardStop('native_packet_required')
        packet.update(max_tokens=limit, thinking={'type': 'enabled' if mode == 'thinking' else 'disabled'}, stream=True, stream_options={'include_usage': True})
        packet.pop('reasoning_effort', None)
        if mode == 'thinking':
            packet['reasoning_effort'] = 'high'
        raw = encode(packet)
        asof = dt.datetime.fromisoformat(json.loads((directory / 'FINANCIAL_AUDIT.json').read_text('utf-8'))['fetched_at'])
        deadline = min(asof + dt.timedelta(hours=24), calendar.session_close(calendar.next_session(pd.Timestamp(target))).to_pydatetime())
        if asof.tzinfo is None or asof > now or now >= deadline:
            raise GuardStop('material_EXPIRED_or_invalid')
        estimate = (Decimal(len(raw) + 1024) * Decimal('.30') + Decimal(limit) * Decimal('1.20')) / 1000000
        if estimate > Decimal(reservation):
            raise GuardStop('estimated_reservation_exceeded')
        members.append(dict(symbol=symbol, request_id=symbol, mode=mode, request_sha256=canonical_sha(packet), context_sha256=hashlib.sha256(context).hexdigest(), messages_sha256=canonical_sha(packet['messages']), target_session=target, analysis_asof=asof.isoformat(), material_expires_at=deadline.isoformat(), reservation_USD=reservation, reservation_check=True, peak_byte_allowance_estimate_not_hard_bound_USD=str(estimate)))
        files.append((symbol, raw, context))
    lock = dict(profile=WATCHLIST_PROFILE, business_commit=WATCHLIST_BUSINESS, mode=mode, offline_only=offline_only, created_at=now.isoformat(), members=members, max_total_POSTs=len(symbols), max_POSTs_per_symbol=1, total_reservation_USD=str(Decimal(reservation) * len(symbols)), automatic_retry=False, fallback=False, authorize_paid_POST=False, pricing_sha256=hashlib.sha256(pricing_raw).hexdigest(), source_free_run=capture.get('run_id'))
    out.mkdir(parents=True, exist_ok=False)
    for symbol, raw, context in files:
        directory = out / symbol
        directory.mkdir()
        (directory / 'FINAL_REQUEST.json').write_bytes(raw)
        (directory / 'NATIVE_CONTEXT.json').write_bytes(context)
    (out / 'OFFICIAL_PRICING.html').write_bytes(pricing_raw)
    (out / 'WATCHLIST_LOCK.json').write_bytes(encode(lock))
    (out / 'BATCH_SHA256.txt').write_text(canonical_sha(lock) + '\n', encoding='utf-8')
    load_set(out, canonical_sha(lock))
    return lock


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'source', 'out', 'pricing'):
        parser.add_argument('--' + name, required=True, type=pathlib.Path)
    parser.add_argument('--mode', choices=('nonthinking', 'thinking'), default='nonthinking')
    parser.add_argument('--only', help='Optional ordered subset; every new batch needs new approval')
    arguments = parser.parse_args()
    result = prepare(arguments.data.resolve(), arguments.source.resolve(), arguments.out.resolve(), arguments.mode, arguments.pricing.resolve(), arguments.only.split(',') if arguments.only else None)
    print('Prepared one mode, no authorization or POST: ' + canonical_sha(result))
