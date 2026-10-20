"""Prepare a Responses migration draft, without reading keys or sending requests."""
import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


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


def build_request(chat_packet, profile):
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
    cost_upper = max(uncached, all_cached, alternative_cost or Decimal(0))
    within_reservation = cost_upper <= reservation
    if not within_reservation and alternative_cost is None:
        raise ValueError('estimated_reservation_exceeded')
    return dict(currency='CNY', quoted_rates_CNY_per_1M={k: str(v) for k, v in rates.items()},
                input_byte_token_proxy=token_proxy, not_a_tokenizer_count=True,
                full_output_uncached_input_estimate_CNY=str(uncached),
                full_output_all_cached_input_estimate_CNY=str(all_cached),
                alternative_astra_reference_estimate_CNY=str(alternative_cost) if alternative_cost is not None else None,
                pricing_ambiguity_blocks_live=not within_reservation,
                proposed_reservation_sufficient_for_all_scenarios=within_reservation,
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
    request = build_request(chat, profile)
    result = dict(
        status='draft_waiting_for_public_API_base_and_credential_setup',
        model=profile['model'], wire_api='responses', authorize_paid_POST=False,
        new_model_POSTs=0, source_batch_not_reused_as_authorization=True,
        source_model=chat['model'], source_request_sha256=member['request_sha256'],
        draft_request_sha256=hashlib.sha256(canonical(request)).hexdigest(),
        profile_sha256=hashlib.sha256(canonical(profile)).hexdigest(),
        source_analysis_asof=member['analysis_asof'],
        source_material_expires_at=member['material_expires_at'],
        native_messages_preserved=request['input'] == chat['messages'],
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
