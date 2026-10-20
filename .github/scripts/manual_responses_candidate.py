"""Prepare a Responses migration draft, without reading keys or sending requests."""
import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


LEGACY_US_MARKET_RULE = '- 美股无涨跌停限制（但有熔断机制），支持 T+0 交易和盘前盘后交易，需关注美元汇率、美联储政策及 SEC 监管动态。'
QUALIFIED_US_MARKET_RULE = (
    '- 美股通常不设固定每日涨跌幅上限，但个股存在 LULD 价格带及暂停交易机制，市场亦有熔断。'
    '符合券商、账户及监管要求时可进行日内交易；多数适用证券交易的常规交收周期为 T+1。'
    '盘前盘后需关注流动性、价差与成交风险，以及美元汇率、美联储政策和 SEC 监管动态。')


def qualify_us_market_rules(packet):
    """Correct the known legacy system line without changing supplied evidence."""
    result = copy.deepcopy(packet)
    for message in result.get('messages', []):
        if message.get('role') == 'system' and isinstance(message.get('content'), str):
            message['content'] = message['content'].replace(LEGACY_US_MARKET_RULE, QUALIFIED_US_MARKET_RULE)
    return result


def hosted_endpoint(base):
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ValueError('public_https_api_base_without_credentials_required')
    host = parsed.hostname.lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local')):
        raise ValueError('local_proxy_not_reachable_from_GitHub_runner')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError('local_proxy_not_reachable_from_GitHub_runner')
    return base.rstrip('/') + '/responses'


def qualify_session_references(context, packet):
    """Bind the two supplied daily bars to dates; never infer older extrema."""
    from datetime import date
    today, previous = context.get('today') or {}, context.get('yesterday') or {}
    if not today or not previous:
        raise ValueError('two_saved_daily_bars_required')
    current_date = date.fromisoformat(today['date'])
    previous_date = date.fromisoformat(previous['date'])
    if previous_date >= current_date or context.get('date') != current_date.isoformat():
        raise ValueError('ordered_session_dates_required')
    rows = []
    for bar, day in ((today, current_date), (previous, previous_date)):
        values = [bar.get(k) for k in ('open', 'high', 'low', 'close')]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError('finite_daily_OHLC_required')
        op, hi, lo, cl = values
        if not lo <= min(op, cl) <= max(op, cl) <= hi:
            raise ValueError('daily_OHLC_order_invalid')
        rows.append('| ' + day.isoformat() + ' | ' + ' | '.join(f'{value:.2f}' for value in values) + ' |')
    marker = '### Session date references / 日线日期对照'
    section = ('\n\n' + marker + '\n'
               'Use the absolute session date when citing a high or low; avoid unanchored today/yesterday/previous-day labels.\n'
               '引用高低点请写绝对交易日日期；目标日是已完成日线，不是运行时盘中日。不要用无日期锚点的本日、昨日或前日混指。\n'
               '| Session date / 交易日 | Open / 开盘 | High / 最高 | Low / 最低 | Close / 收盘 |\n'
               '|---|---:|---:|---:|---:|\n' + '\n'.join(rows) + '\n'
               'Rounded display only; original numeric precision is preserved in context. '
               '显示值保留两位小数，原始精度仍在上下文；本表不证明其他历史前低不存在，也不确认支撑有效。\n')
    result = copy.deepcopy(packet)
    user_messages = [m for m in result['messages'] if m.get('role') == 'user' and isinstance(m.get('content'), str)]
    if not user_messages:
        raise ValueError('user_text_message_required')
    existing = [m for m in result['messages'] if marker in str(m.get('content', ''))]
    if existing:
        if len(existing) != 1 or existing[0]['content'].count(marker) != 1 or section not in existing[0]['content']:
            raise ValueError('stale_or_ambiguous_session_reference_section')
    else:
        user_messages[-1]['content'] += section
    return result


def build_request(chat_packet, profile, context=None):
    chat_packet = qualify_us_market_rules(chat_packet)
    if context is not None:
        chat_packet = qualify_session_references(context, chat_packet)
    messages = chat_packet.get('messages')
    if not isinstance(messages, list) or not messages:
        raise ValueError('saved_native_messages_required')
    for message in messages:
        if (set(message) != {'role', 'content'} or message['role'] not in ('system', 'developer', 'user', 'assistant')
                or not isinstance(message['content'], str)):
            raise ValueError('text_only_native_messages_required')
    if profile.get('wire_api') != 'responses' or profile.get('reasoning_effort') not in ('low', 'medium', 'high', 'xhigh'):
        raise ValueError('reviewed_responses_profile_required')
    if type(profile.get('max_output_tokens')) is not int or not 1 <= profile['max_output_tokens'] <= 128000:
        raise ValueError('reviewed_output_limit_required')
    if profile.get('automatic_retry') is not False or profile.get('fallback') is not False:
        raise ValueError('retry_and_fallback_forbidden')
    if profile.get('max_total_POSTs') != 1 or profile.get('authorize_paid_POST') is not False:
        raise ValueError('unapproved_single_call_profile_required')
    return dict(
        model=profile['model'], input=copy.deepcopy(messages),
        reasoning=dict(effort=profile['reasoning_effort']),
        max_output_tokens=profile['max_output_tokens'], stream=True, store=False,
        service_tier=profile['service_tier'])


def rebuild_with_saved_news(chat, context, news_packet, asof, source, financial_audit):
    """Reformat the native user prompt with news, rather than append to old missing-news prose."""
    import subprocess
    import sys
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip() != '577624ad8459871630c690e5760ae504ac6f2b9f':
        raise ValueError('reviewed_native_source_required')
    sys.path.insert(0, str(source.resolve()))
    from src.analyzer import GeminiAnalyzer
    from src.services.analysis_context_builder import PipelineAnalysisArtifacts, AnalysisContextBuilder
    from src.analysis_context_pack_prompt import format_analysis_context_pack_prompt_section
    from saved_news import attach_saved_news_context
    from nvda_research_materials import format_financial_evidence, format_dividend_announcements
    from watchlist_mode import qualify_financial_fields
    artifacts = PipelineAnalysisArtifacts(
        code=context['code'], stock_name=context.get('stock_name', context['code']),
        market='us', phase=None, base_context=copy.deepcopy(context), enhanced_context=copy.deepcopy(context),
        realtime_quote=None, trend_result=None, chip_data=None,
        fundamental_context=copy.deepcopy(context.get('fundamental_context')),
        news_context=None, news_result_count=None, metadata={})
    prepared = attach_saved_news_context(artifacts, news_packet, asof)
    if not prepared.enhanced_context['saved_news_audit']['accepted']:
        raise ValueError('new_request_requires_at_least_one_accepted_saved_news_item')
    pack = AnalysisContextBuilder.build(prepared)
    summary = format_analysis_context_pack_prompt_section(pack, report_language='zh')
    # Formatting only: explicit supported overrides select the original legacy scaffold.
    # No Config, Router, SDK client, dispatch or network is initialized.
    analyzer = object.__new__(GeminiAnalyzer)
    analyzer._skill_instructions_override = ''
    analyzer._default_skill_policy_override = ''
    analyzer._use_legacy_default_prompt_override = True
    prompt = analyzer._format_prompt(prepared.enhanced_context, artifacts.stock_name,
        news_context=prepared.news_context, report_language='zh', analysis_context_pack_summary=summary)
    prompt += format_financial_evidence(prepared.enhanced_context, 'zh')
    prompt += format_dividend_announcements(prepared.enhanced_context, 'zh')
    prompt += ('\n消息材料截止时间（带时区）：' + asof.isoformat() +
               '\n行情与盘前阶段仍沿用原采集时刻；不以新闻采集时间替换行情日期或假装是当前实时报价。'
               '新闻条目数量不等于独立来源数，按各条标明的出版社核对来源集中度；不代表综合新闻覆盖，'
               '文章中的产品预期/原因推断必须保留媒体或传闻归属，不当作发行人确认、实际需求或收入结论。\n')
    packet = copy.deepcopy(chat)
    indices = [i for i, message in enumerate(packet['messages']) if message.get('role') == 'user']
    if len(indices) != 1:
        raise ValueError('one_native_user_prompt_required')
    packet['messages'][indices[0]]['content'] = prompt
    updated, packet = qualify_financial_fields(prepared.enhanced_context, packet, financial_audit, 'USD')
    return updated, packet


def budget_estimate(request, profile):
    pricing = profile['pricing']
    if pricing.get('unit') != 'CNY_per_1M_text_tokens':
        raise ValueError('direct_CNY_unit_prices_required')
    if set(pricing.get('rates', {})) != {'input', 'cached_input', 'output'}:
        raise ValueError('three_quoted_CNY_rates_required')
    rates = {name: Decimal(value) for name, value in pricing['rates'].items()}
    if any(not rate.is_finite() or rate < 0 for rate in rates.values()):
        raise ValueError('nonnegative_finite_quoted_rates_required')
    if 'reference_official_USD_per_1M' in pricing:
        for name, rate in rates.items():
            official = Decimal(pricing['reference_official_USD_per_1M'][name])
            target = Decimal(pricing['target_official_USD_per_1M'][name])
            reference = Decimal(pricing['reference_gateway_CNY_per_1M'][name])
            if (not all(value.is_finite() for value in (official, target, reference))
                    or official <= 0 or target < 0 or reference < 0
                    or reference * target / official != rate):
                raise ValueError('category_specific_extrapolation_mismatch')
    # Byte allowance is an estimate, not a tokenizer measurement or billing cap.
    token_proxy = len(canonical(request['input'])) + 1024
    if token_proxy > 272000:
        raise ValueError('long_context_requires_new_pricing_review')
    output = Decimal(request['max_output_tokens']) * rates['output'] / 1000000
    uncached = Decimal(token_proxy) * rates['input'] / 1000000 + output
    all_cached = Decimal(token_proxy) * rates['cached_input'] / 1000000 + output
    alternative_rates = {name: Decimal(value) for name, value in
                         pricing.get('alternative_astra_extrapolation_CNY_per_1M', {}).items()}
    alternative_cost = None
    if alternative_rates:
        if (set(alternative_rates) != set(rates)
                or any(not rate.is_finite() or rate < 0 for rate in alternative_rates.values())):
            raise ValueError('invalid_alternative_pricing_scenario')
        alternative_cost = (Decimal(token_proxy) * max(alternative_rates['input'], alternative_rates['cached_input'])
                            + Decimal(request['max_output_tokens']) * alternative_rates['output']) / 1000000
    reservation = Decimal(profile['proposed_reservation_CNY'])
    if not reservation.is_finite() or reservation <= 0:
        raise ValueError('positive_finite_CNY_reservation_required')
    selected_sol = pricing.get('selected_reference') == 'sol' and bool(pricing.get('selection_authority'))
    cost_upper = max(uncached, all_cached, Decimal(0) if selected_sol else alternative_cost or Decimal(0))
    within_reservation = cost_upper <= reservation
    if not within_reservation and alternative_cost is None:
        raise ValueError('estimated_reservation_exceeded')
    return dict(currency='CNY', quoted_rates_CNY_per_1M={k: str(v) for k, v in rates.items()},
                input_byte_token_proxy=token_proxy, not_a_tokenizer_count=True,
                full_output_uncached_input_estimate_CNY=str(uncached),
                full_output_all_cached_input_estimate_CNY=str(all_cached),
                alternative_astra_reference_estimate_CNY=str(alternative_cost) if alternative_cost is not None else None,
                pricing_ambiguity_blocks_live=not within_reservation,
                selected_reference='sol' if selected_sol else 'all_scenarios',
                alternative_reference_is_disclosure_only=selected_sol,
                proposed_reservation_sufficient_for_selected_scenario=within_reservation,
                proposed_reservation_CNY=str(reservation), reservation_authorized=False,
                is_bill=False, is_provider_enforced_cap=False,
                reasoning_tokens_in_output_not_charged_twice=True,
                quoted_prices_independently_verified=False,
                multiplier_applied=False, currency_conversion_applied=False,
                assumptions=pricing['assumptions'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-bundle', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--news-data', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--financial-audit', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    lock = json.loads((args.source_bundle / 'WATCHLIST_LOCK.json').read_text('utf-8'))
    if len(lock.get('members', [])) != 1 or lock['members'][0]['symbol'] != 'AAPL':
        raise ValueError('single_AAPL_source_material_required')
    member = lock['members'][0]
    if datetime.now(timezone.utc) >= datetime.fromisoformat(member['material_expires_at']):
        raise ValueError('source_material_expired_do_not_refresh')
    raw = (args.source_bundle / 'AAPL/FINAL_REQUEST.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != member['request_sha256']:
        raise ValueError('source_request_hash_mismatch')
    context_raw = (args.source_bundle / 'AAPL/NATIVE_CONTEXT.json').read_bytes()
    if hashlib.sha256(context_raw).hexdigest() != member['context_sha256']:
        raise ValueError('source_context_hash_mismatch')
    chat = json.loads(raw)
    profile = json.loads(args.profile.read_text('utf-8'))
    context = json.loads(context_raw)
    news_sha = None
    news_cutoff = None
    source_messages = copy.deepcopy(chat['messages'])
    if args.news_data:
        if not args.source or not args.financial_audit:
            raise ValueError('saved_news_requires_native_source_and_financial_audit')
        news_raw = args.news_data.read_bytes()
        news_sha = hashlib.sha256(news_raw).hexdigest()
        news_cutoff = datetime.now(timezone.utc)
        context, chat = rebuild_with_saved_news(
            chat, context, json.loads(news_raw), news_cutoff, args.source.resolve(),
            json.loads(args.financial_audit.read_text('utf-8')))
        (out / 'SAVED_NEWS_AUDIT.json').write_text(json.dumps(context['saved_news_audit'], ensure_ascii=False, indent=2), encoding='utf-8')
        (out / 'PREPARED_CONTEXT.json').write_bytes(canonical(context))
    request = build_request(chat, profile, context=context)
    result = dict(
        status='draft_waiting_for_public_API_base_and_credential_setup',
        model=profile['model'], wire_api='responses', authorize_paid_POST=False,
        new_model_POSTs=0, source_batch_not_reused_as_authorization=True,
        source_model=chat['model'], source_request_sha256=member['request_sha256'],
        draft_request_sha256=hashlib.sha256(canonical(request)).hexdigest(),
        profile_sha256=hashlib.sha256(canonical(profile)).hexdigest(),
        source_analysis_asof=member['analysis_asof'],
        source_material_expires_at=member['material_expires_at'],
        native_messages_preserved=request['input'] == source_messages,
        session_reference_table_added=True,
        original_message_text_retained=all(
            new['role'] == old['role'] and new['content'].startswith(old['content'])
            for old, new in zip(source_messages, request['input'])),
        source_system_messages_preserved=[m for m in source_messages if m['role'] != 'user'] == [
            m for m in request['input'] if m['role'] != 'user'],
        known_US_market_rule_qualified=any(
            m.get('role') == 'system' and LEGACY_US_MARKET_RULE in m.get('content', '')
            for m in source_messages),
        news_user_prompt_rebuilt=bool(args.news_data),
        saved_news_packet_sha256=news_sha,
        news_cutoff=news_cutoff.isoformat() if news_cutoff else None,
        api_base_env=profile['api_base_env'], api_key_env=profile['api_key_env'],
        public_endpoint=None, budget=budget_estimate(request, profile))
    if result['budget']['pricing_ambiguity_blocks_live']:
        result['status'] = 'draft_waiting_for_target_tariff_confirmation_and_public_API_setup'
    base = os.environ.get(profile['api_base_env'])
    if base:
        result['public_endpoint'] = hosted_endpoint(base)
        if not result['budget']['pricing_ambiguity_blocks_live']:
            result['status'] = 'draft_endpoint_configured_not_frozen_or_authorized'
    (out / 'RESPONSES_REQUEST_DRAFT.json').write_bytes(canonical(request))
    (out / 'MIGRATION_STATUS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'PROFILE_NOT_AUTHORIZATION.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
