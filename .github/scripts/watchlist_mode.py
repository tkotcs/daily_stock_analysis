"""Freeze one manual mode from a new native capture; never send requests."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import pathlib
import re
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


def qualify_financial_fields(context, packet, audit, quote_currency=None):
    context, packet = copy.deepcopy(context), copy.deepcopy(packet)
    report = (((context.get('fundamental_context') or {}).get('earnings') or {}).get('data') or {}).get('financial_report') or {}
    fields = audit.get('fields') or {}
    if not fields:
        if any(report.get(field) is not None for field in ('revenue', 'net_profit_parent', 'operating_cash_flow')):
            raise GuardStop('financial_field_audit_required')
        return context, packet
    official = context.get('official_research') or {}
    earnings = (context.get('fundamental_context') or {}).get('earnings') or {}
    dividend = (earnings.get('data') or {}).get('dividend') or {}
    quarantine = bool(quote_currency and report.get('currency') and report['currency'] != quote_currency
                      and dividend.get('currency') == quote_currency and not dividend.get('events')
                      and any(type(dividend.get(field)) in (int, float) and dividend[field] != 0
                              for field in ('ttm_cash_dividend_per_share', 'ttm_dividend_yield_pct')))
    restriction = '财务及分红暂不可用：财报与报价币种不同，分红缺少逐事件币种及存托股份口径证据；不换算，不推导盈利能力、ROE、分红收益率或估值，仅作技术研究。'
    notes = {}
    labels = {'revenue': '营业收入', 'net_profit_parent': '归母净利润', 'operating_cash_flow': '经营现金流', 'roe': 'ROE'}
    for field in labels:
        item = fields.get(field) or {}
        value = report.get(field)
        supplied_official = value is not None and value == (official.get('values') or {}).get(field)
        classification = 'not_applicable_ETF' if audit.get('enterprise_applicable') is False else item.get('classification', 'TTM_or_unknown_info_fallback')
        if supplied_official:
            classification = 'reviewed_official_packet_not_revalidated'
            period, source = official.get('period_end'), official.get('source_url')
            warning = '复用已审阅官方资料包；本批未附原网页逐字段复核，不宣称已独立核验'
        else:
            period = item.get('actual_series_period') if classification == 'quarterly_Yahoo_not_officially_verified' else None
            source = item.get('source_url') or 'Yahoo聚合字段'
            warning = 'Yahoo季度表，未独立官方核验' if period else 'TTM或期间未知，非正式单季度数字'
            if classification == 'estimated_revenue_times_margin':
                warning = '收入乘利润率推算，期间未知；不是正式季度归母净利润，不得用于季度同比或利润质量结论'
            if classification == 'not_applicable_ETF':
                warning = 'ETF企业财务不适用'
        notes[field] = dict(value=value, classification=classification, period_end=period, adapter_report_date=report.get('report_date'), currency=report.get('currency'), source_url=source, independently_official_verified=False, limitation=warning)
        if field == 'net_profit_parent':
            notes[field]['limitation'] += '；供应商字段名不证明已独立核验归母归属'
        if quarantine:
            notes[field].update(value=None, classification='quarantined_currency_and_receipt_basis', period_end=None, limitation=restriction)
    counts = {field: 0 for field in labels}
    dividend_counts = {field: 0 for field in ('ttm_cash_dividend_per_share', 'ttm_dividend_yield_pct', 'ttm_event_count')}
    for message in packet['messages']:
        if not isinstance(message.get('content'), str):
            continue
        text = message['content']
        text = re.sub(r'(?m)^\| 最近报告期 \|[^\n]*$', '| 报告期口径 | 见逐字段说明 | 适配器日期不代表所有字段属于同一季度 |', text)
        for field, label in labels.items():
            note = notes[field]
            expected = str(report[field]) if field in report else 'N/A'
            def replace_row(match):
                if match.group(1).strip() != expected:
                    raise GuardStop('financial_prompt_value_mismatch')
                counts[field] += 1
                detail = f"期间={note['period_end'] or '未知/不适用'}；{note['classification']}；{note['limitation']}；来源={note['source_url']}"
                display_label = '净利润（供应商字段，归母归属未独立核验）' if field == 'net_profit_parent' else label
                return f"| {display_label} | {'N/A' if quarantine else expected} | {detail} |"
            text = re.sub(r'(?m)^\| ' + re.escape(label) + r' \| ([^|\n]*) \|[^\n]*$', replace_row, text)
        if quarantine:
            message_dividend_count = 0
            for field, label in [('ttm_cash_dividend_per_share', '近12个月每股现金分红'), ('ttm_dividend_yield_pct', 'TTM 股息率'), ('ttm_event_count', 'TTM 分红事件数')]:
                pattern = r'(?m)^\| ' + re.escape(label) + r' \| ([^|\n]*) \|[^\n]*$'
                def replace_dividend(match):
                    if match.group(1).strip() != str(dividend.get(field, 'N/A')):
                        raise GuardStop('dividend_prompt_value_mismatch')
                    return f'| {label} | N/A | {restriction} |'
                text, count = re.subn(pattern, replace_dividend, text)
                dividend_counts[field] += count
                message_dividend_count += count
            if message_dividend_count:
                text += '\n\n' + restriction
        message['content'] = text
    if any(count != 1 for count in counts.values()):
        raise GuardStop('native_financial_table_required')
    if quarantine:
        if any(count != 1 for count in dividend_counts.values()):
            raise GuardStop('native_dividend_table_required')
        data = earnings['data']
        data['financial_report'] = dict(report_date=None, revenue=None, net_profit_parent=None, operating_cash_flow=None, roe=None, currency=report.get('currency'))
        data['dividend'] = dict(events=[], ttm_cash_dividend_per_share=None, ttm_dividend_yield_pct=None, ttm_event_count=None, currency=None)
        earnings['status'] = 'unavailable_currency_and_receipt_basis'
        context['financial_input_restriction'] = restriction
    context['financial_field_provenance'] = notes
    return context, packet


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
        financial_audit = json.loads((directory / 'FINANCIAL_AUDIT.json').read_text('utf-8'))
        price_audit_path = directory / 'PRICE_AUDIT.json'
        quote_currency = (json.loads(price_audit_path.read_text('utf-8')).get('metadata') or {}).get('currency') if price_audit_path.exists() else None
        context_value, packet = qualify_financial_fields(context_value, packet, financial_audit, quote_currency)
        if context_value.get('financial_field_provenance'):
            context = encode(context_value)
        packet.update(max_tokens=limit, thinking={'type': 'enabled' if mode == 'thinking' else 'disabled'}, stream=True, stream_options={'include_usage': True})
        packet.pop('reasoning_effort', None)
        if mode == 'thinking':
            packet['reasoning_effort'] = 'high'
        raw = encode(packet)
        asof = dt.datetime.fromisoformat(financial_audit['fetched_at'])
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
