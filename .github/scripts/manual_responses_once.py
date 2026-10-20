"""Hash-locked one-attempt Responses sender, only behind the human Environment gate."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys

from manual_responses_candidate import canonical, hosted_endpoint, budget_estimate


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_bundle(bundle, expected):
    raw = (bundle / 'RESPONSES_LOCK.json').read_bytes()
    if digest(raw) != expected:
        raise ValueError('new_batch_hash_mismatch')
    lock = json.loads(raw)
    if (lock.get('profile') != 'manual_responses_once_v1' or lock.get('symbol') != 'AAPL'
            or lock.get('max_total_POSTs') != 1 or lock.get('authorize_paid_POST') is not False
            or lock.get('retry') is not False or lock.get('fallback') is not False
            or lock.get('endpoint') != 'https://api.sequenceq.com/v1/responses'):
        raise ValueError('reviewed_one_call_lock_required')
    loaded = {}
    for name, field in [('REQUEST.json', 'request_sha256'), ('CONTEXT.json', 'context_sha256'),
                        ('PROFILE.json', 'profile_sha256')]:
        body = (bundle / name).read_bytes()
        if digest(body) != lock[field]:
            raise ValueError('frozen_file_hash_mismatch')
        loaded[name] = json.loads(body)
    request, profile = loaded['REQUEST.json'], loaded['PROFILE.json']
    if (set(request) != {'model', 'input', 'reasoning', 'max_output_tokens', 'stream', 'store', 'service_tier'}
            or request['model'] != 'gpt-6.1-sol' or request['reasoning'] != {'effort': 'high'}
            or request['max_output_tokens'] != 32768 or request['stream'] is not True
            or request['store'] is not False or request['service_tier'] != 'default'):
        raise ValueError('frozen_model_or_parameters_invalid')
    if (profile['pricing'].get('selected_reference') != 'sol'
            or profile['pricing']['rates'] != {'input': '0.4998', 'cached_input': '0.02499', 'output': '0.62475'}
            or profile['proposed_reservation_CNY'] != lock['reservation_CNY'] or lock['reservation_CNY'] != '0.05'):
        raise ValueError('selected_Sol_budget_required')
    if budget_estimate(request, profile)['pricing_ambiguity_blocks_live']:
        raise ValueError('budget_not_approved')
    check_time(lock)
    return lock, request, loaded['CONTEXT.json'], profile


def check_time(lock):
    now = datetime.now(timezone.utc)
    asof = datetime.fromisoformat(lock['analysis_asof'])
    expiry = datetime.fromisoformat(lock['material_expires_at'])
    if asof.utcoffset() is None or expiry.utcoffset() is None or not asof <= now < expiry:
        raise ValueError('material_expired_or_invalid_no_refresh')
    if expiry > asof + timedelta(hours=24):
        raise ValueError('material_expiry_extended')


def completed_response(raw):
    """Accept only an explicit completed response; never treat a partial delta as success."""
    final = None
    for line in raw.decode('utf-8').splitlines():
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if payload == '[DONE]':
            continue
        event = json.loads(payload)
        if event.get('type') in ('error', 'response.failed', 'response.incomplete'):
            raise ValueError('response_failed_or_incomplete_no_retry')
        if event.get('type') == 'response.completed':
            if final is not None:
                raise ValueError('duplicate_completed_event')
            final = event['response']
    if not final or final.get('status') != 'completed' or final.get('error'):
        raise ValueError('completion_not_proven_no_retry')
    text = ''.join(part['text'] for item in final.get('output', []) if item.get('type') == 'message'
                   for part in item.get('content', []) if part.get('type') == 'output_text')
    if not text:
        raise ValueError('completed_output_text_missing')
    return final, text


def cost(usage, profile):
    if not isinstance(usage, dict):
        return dict(status='unknown_usage', estimated_CNY=None)
    i, o = usage.get('input_tokens'), usage.get('output_tokens')
    c = (usage.get('input_tokens_details') or {}).get('cached_tokens')
    if any(type(n) is not int or n < 0 for n in (i, o)) or (c is not None and (type(c) is not int or not 0 <= c <= i)):
        return dict(status='unknown_usage', estimated_CNY=None)
    r = profile['pricing']['rates']
    value = (Decimal(i - (c or 0)) * Decimal(r['input'])
             + Decimal(c or 0) * Decimal(r['cached_input']) + Decimal(o) * Decimal(r['output'])) / 1000000
    return dict(status='estimated_using_user_selected_Sol_reference_not_bill',
                estimated_CNY=str(value), cache_split_reported=c is not None,
                missing_cache_assumed_uncached=c is None, reasoning_not_added_twice=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--batch-sha', required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    key = os.environ.get('SEEKERX', '')
    result = dict(published=False, quality_accepted=False, actual_model_POST_attempts=0,
                  automatic_retry=False, fallback=False, status='blocked_before_POST')
    def save(name, value):
        text = json.dumps(value, ensure_ascii=False, indent=2)
        if key:
            text = text.replace(key, '[REDACTED]')
        (out / name).write_text(text, encoding='utf-8')
    exit_code = 1
    try:
        if (not key or os.environ.get('GITHUB_RUN_ATTEMPT') != '1'
                or os.environ.get('GITHUB_REF') != 'refs/heads/deploy/phase2h-request-preparation'
                or os.environ.get('GITHUB_ACTOR') != os.environ.get('GITHUB_REPOSITORY_OWNER')):
            raise ValueError('owner_first_attempt_deploy_and_key_required')
        lock, request, context, profile = load_bundle(args.bundle, args.batch_sha)
        if hosted_endpoint(os.environ.get('RESEARCH_API_BASE', '')) != lock['endpoint']:
            raise ValueError('public_endpoint_changed')
        if args.batch_sha not in os.environ.get('APPROVAL_REF', ''):
            raise ValueError('hash_scoped_human_authorization_required')
        import subprocess
        if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.source, text=True).strip() != lock['business_commit']:
            raise ValueError('fixed_source_changed')
        sys.path.insert(0, str(args.source.resolve()))
        from src.core.trading_calendar import get_effective_trading_date
        if get_effective_trading_date('us', current_time=datetime.now(timezone.utc)).isoformat() != lock['target_session']:
            raise ValueError('latest_completed_session_changed')
        if key.encode() in canonical(request):
            raise ValueError('credential_in_body')
        from remote_execution_claim import GitHubAPI, RemoteExecutionClaim
        claim = RemoteExecutionClaim(
            GitHubAPI(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN']),
            args.batch_sha, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_SHA'], symbols=('AAPL',))
        save('REMOTE_CLAIM.json', claim.reserve([dict(symbol='AAPL', request_sha256=lock['request_sha256'])]))
        claim.before_send('AAPL', lock['request_sha256'])
        check_time(lock)
        save('AUTHORIZATION_USED.json', dict(batch_sha256=args.batch_sha, request_sha256=lock['request_sha256'],
            run_id=os.environ['GITHUB_RUN_ID'], authorization_reference=os.environ['APPROVAL_REF'],
            secret_reference='repository Secret SEEKERX; user added it and requested this paid approval',
            reservation_CNY='0.05', pricing=profile['pricing'], material_expires_at=lock['material_expires_at']))
        import httpx
        raw = bytearray()
        # Marker is persisted before transport. Every ambiguous result is consumed; never retry.
        save('POST_ATTEMPT.json', dict(state='reserved_before_transport_may_be_charged', batch_sha256=args.batch_sha))
        result['actual_model_POST_attempts'] = 1
        try:
            with httpx.Client(transport=httpx.HTTPTransport(retries=0), follow_redirects=False,
                              trust_env=False, timeout=httpx.Timeout(600, connect=25)) as client:
                with client.stream('POST', lock['endpoint'], headers={'Authorization': 'Bearer ' + key,
                                   'Content-Type': 'application/json'}, content=canonical(request)) as response:
                    result['HTTP_status'] = response.status_code
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 16000000:
                            raise ValueError('response_size_limit_no_retry')
        finally:
            (out / 'RAW_RESPONSE_BODY.bin').write_bytes(bytes(raw).replace(key.encode(), b'[REDACTED]'))
        if result['HTTP_status'] != 200:
            raise ValueError('HTTP_failure_do_not_retry')
        response, text = completed_response(bytes(raw))
        response = json.loads(json.dumps(response, ensure_ascii=False).replace(key, '[REDACTED]'))
        text = text.replace(key, '[REDACTED]')
        save('RESPONSE_RESULT.json', response)
        (out / 'MODEL_RAW_TEXT.txt').write_text(text, encoding='utf-8')
        result['usage'] = response.get('usage')
        result['cost_estimate'] = cost(response.get('usage'), profile)
        result['response_model'] = response.get('model')
        result['response_service_tier'] = response.get('service_tier')
        from src.analyzer import GeminiAnalyzer
        analyzer = object.__new__(GeminiAnalyzer)
        _, model = analyzer._extract_analysis_json_object(text)
        save('PARSED_MODEL_JSON.json', model)
        from manual_reports import save_full_report
        save_full_report(out, 'AAPL', model, context,
                         analyzer._format_computed_quote_facts(context), False)
        report = '# AAPL · GPT-6.1 Sol 单次真实生成测试\n\n'
        report += '> 未发布，整体质量未验收；行情截至' + lock['target_session'] + '，未执行综合新闻检索。\n\n'
        report += (out / 'MODEL_ALL_FIELDS.md').read_text('utf-8')
        (out / 'REPORT.md').write_text(report, encoding='utf-8')
        result['status'] = 'generated_preview_requires_manual_quality_review'
        exit_code = 0
    except BaseException as error:
        result['status'] = 'failed_no_retry' if result['actual_model_POST_attempts'] else 'blocked_before_POST'
        result['error_category'] = type(error).__name__
        # Avoid exception text that may contain URLs, headers or credential-bearing bodies.
        result['reason'] = str(error) if type(error) is ValueError else 'inspect_saved_evidence_no_retry'
    finally:
        save('STATUS.json', result)
        if key and any(key.encode() in p.read_bytes() for p in out.rglob('*') if p.is_file()):
            raise SystemExit('credential_scan_failed_no_upload')
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a', encoding='utf-8') as handle:
                handle.write('# AAPL Responses single attempt\n\n```json\n' + json.dumps(result, ensure_ascii=False, indent=2) + '\n```\n')
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
