"""Classify public adapter evidence and verify native MA60 locally, without AI."""
import argparse
import collections
import hashlib
import json
import math
import os
import pathlib
import socket
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=pathlib.Path, required=True)
    p.add_argument('--out', type=pathlib.Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    for k in list(os.environ):
        if any(s in k for s in ('API_KEY', 'PASSWORD', 'ACCESS_TOKEN', 'WEBHOOK')):
            os.environ.pop(k, None)
    def deny(*args, **kwargs):
        raise AssertionError('data_review_offline_only')
    socket.socket.connect = deny; socket.create_connection = deny
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    import pandas as pd
    from src.stock_analyzer import StockTrendAnalyzer
    def load(name): return json.loads((a.data/name).read_text(encoding='utf-8'))
    rows = load('RESULTS.json'); summary = load('SUMMARY.json'); trace = load('HTTP_TRACE.json')
    guard = load('FREE_NETWORK_GUARD.json')
    assert guard['blocked_calls'] == guard['real_model_POSTs'] == guard['mail_sent'] == 0
    assert guard['allowed_yahoo_GETs'] == len(trace)
    reviewed = []; technical = []; table = []
    for r in rows:
        r = dict(r); fields = {}; is_etf = (r.get('identity') or {}).get('quoteType') == 'ETF'
        for field, raw in r['financial_fields'].items():
            v = dict(raw)
            mode = 'missing' if v['value'] is None else 'quarterly_Yahoo_unverified' if v['direct_value'] is not None else 'estimated_revenue_times_margin' if field == 'net_profit_parent' else 'TTM_or_unknown_info_fallback'
            v['classification'] = mode
            v['officially_verified'] = False
            if v['direct_value'] is None: v['period_end'] = None
            v['usable_as_official_quarterly_financial'] = False
            fields[field] = v
        r['classified_financial_fields'] = fields
        r['enterprise_financials_applicable'] = not is_etf
        r['identity_scope'] = 'Yahoo metadata only; not independent issuer/ADR legal verification'
        if r['code'] == 'SKHY':
            r['ADR_ratio'] = None
            r['identity_limit'] = 'USD quote and KRW financial currency kept separate; ADR ratio not reverified'
        if r['code'] == 'SPCX': r['identity_limit'] = 'Provider name/market do not prove legal issuer identity'
        if r['code'] == 'BRK.B':
            assert r['provider_symbol'] == 'BRK-B'
            r['canonical_identity_kept'] = 'BRK.B'
        if r['quote_valid']:
            frame = pd.read_csv(a.data/(r['code']+'-daily.csv'))
            tr = StockTrendAnalyzer().analyze(frame, r['code'])
            assert tr.data_points == len(frame) >= 60
            assert math.isclose(tr.ma60, float(frame.close.tail(60).mean()), rel_tol=1e-12)
            technical.append({'code': r['code'], 'session': r['latest_date'], 'rows': len(frame),
                              'close': tr.current_price, 'ma5': tr.ma5, 'ma10': tr.ma10,
                              'ma20': tr.ma20, 'ma60': tr.ma60, 'true_60_window_passed': True,
                              'rsi12': tr.rsi_12, 'macd_bar': tr.macd_bar, 'LLM_calls': 0})
        reviewed.append(r)
        labels = [v['classification'] for v in fields.values()]
        table.append(f"|{r['code']} / {r['provider_symbol']}|{r['rows']}|{r.get('latest_date','未知')}|{r['quote_valid']}|{' / '.join(labels) or '未取到'}|{r['requests']}|{'；'.join(r['errors']) or '无终态错误'}|")
    recovery = []
    for i, t in enumerate(trace):
        if t.get('status') == 401:
            recovery.append({'code': t['code'], 'path': t['path'], 'later_same_path_HTTP200': any(
                u['code'] == t['code'] and u['path'] == t['path'] and u.get('status') == 200 for u in trace[i+1:])})
    status = dict(collections.Counter(str(t.get('status')) for t in trace))
    result = {'summary': summary, 'HTTP_status_counts': status, 'auth_401_observations': recovery,
              'native_true_MA60_verified': len(technical), 'rows': reviewed, 'technical': technical,
              'paid_POSTs': 0, 'emails': 0, 'AI_quality_tested': False}
    (a.out/'DATA_REVIEW.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    md = '# 本轮托管免费数据实测\n\n' + json.dumps(summary, ensure_ascii=False, indent=2) + '\n\nHTTP状态：' + str(status) + '\n\n|代码/供应商|根数|最新日线|行情有效|财务分类|请求数|失败/缺失原因|\n|---|---:|---|---|---|---:|---|\n' + '\n'.join(table)
    md += '\n\nYahoo字段不是独立官方GAAP核验；info回退与推算不能标成该季度正式数据。ETF企业财务允许缺失。只有本轮真实采集可计入数据可用性；本次与此前相同交易日不算新增连续交易日。没有历史缓存替代、AI调用或邮件。\n'
    (a.out/'WATCHLIST_COVERAGE.md').write_text(md, encoding='utf-8')
    print(json.dumps({'valid': summary['valid_quotes'], 'total': len(rows), 'MA60_passed': len(technical), 'HTTP': status, 'model_calls': 0}))


if __name__ == '__main__':
    main()
