"""Freeze one new AAPL candidate after successful native capture; never authorize."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

from watchlist_mode import prepare, load_set
from authorized_once import canonical_sha


def check_comparison(context, before, packet):
    text = '\n'.join(message.get('content', '') for message in packet['messages'])
    if context['financial_evidence'] != before['financial_evidence']:
        raise ValueError('independent_financial_evidence_changed')
    if context['fundamental_context'] != before['fundamental_context'] or context['today'] != before['today']:
        raise ValueError('vendor_financial_or_quote_changed')
    if '| 归母净利润 |' in text or '净利润（供应商字段，归母归属未独立核验）' not in text:
        raise ValueError('ambiguous_vendor_income_label')
    if '| 最近报告期 |' in text:
        raise ValueError('unqualified_vendor_period_label')
    for required in ('derived_from_ytd_difference', 'direct_quarter', '116996', '82627',
                     '2026-06-27', '2026-03-28', '不是近三日新闻'):
        if required not in text:
            raise ValueError('independent_financial_prompt_content_missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'data', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = dict(created_at=datetime.now(timezone.utc).isoformat(),
                  authorize_paid_POST=False, actual_supplier_POSTs=0,
                  symbol='AAPL', status='preparing_free_candidate')
    try:
        capture = json.loads((args.data / 'RESULTS.json').read_text('utf-8'))
        rows = capture['symbols']
        if len(rows) != 1 or rows[0]['symbol'] != 'AAPL' or rows[0]['status'] != 'success_simulated_model':
            raise ValueError('fresh_AAPL_capture_failed_no_pricing_GET_no_freeze')
        url = 'https://api-docs.deepseek.com/quick_start/pricing'
        receipt = dict(url=url, fetched_at=datetime.now(timezone.utc).isoformat(), retries=0)
        with urlopen(Request(url, headers={'User-Agent': 'DSA manual pricing review'}), timeout=25) as response:
            raw = response.read()
            receipt.update(status=response.status, final_url=response.url,
                           sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        pricing = out / 'OFFICIAL_PRICING.html'
        pricing.write_bytes(raw)
        (out / 'PRICING_CAPTURE.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        bundle = out / 'candidate'
        lock = prepare(args.data.resolve(), args.source.resolve(), bundle, 'nonthinking', pricing, ['AAPL'])
        digest = canonical_sha(lock)
        _, packets, contexts = load_set(bundle, digest)
        before = json.loads((args.data / 'AAPL/NATIVE_CONTEXT.json').read_text('utf-8'))
        check_comparison(contexts['AAPL'], before, packets['AAPL'])
        result.update(status='candidate_ready_not_authorized', batch_sha256=digest,
                      max_total_POSTs=lock['max_total_POSTs'],
                      reservation_USD=lock['total_reservation_USD'],
                      member=lock['members'][0], final_financial_comparison_check=True)
    except Exception as error:
        result.update(status='blocked_before_paid_authorization', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        (out / 'PREPARATION_RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        summary = __import__('os').environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a', encoding='utf-8') as handle:
                handle.write('# AAPL free preparation: no paid POST\n\n```json\n'
                             + json.dumps(result, ensure_ascii=False, indent=2) + '\n```\n')


if __name__ == '__main__':
    main()
