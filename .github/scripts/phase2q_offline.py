"""Offline native 16K request capture/replay. No live flag, no authorization input."""
import argparse
import copy
import hashlib
import ipaddress
import json
import os
import pathlib
import re
import smtplib
import socket
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True, type=pathlib.Path)
    args = p.parse_args()
    root = pathlib.Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    assert not (root / '.env').exists(), 'Use a clean checkout, not a credential-bearing .env'
    fixtures = root / 'tests/fixtures/phase2p'
    before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in fixtures.iterdir() if f.is_file()}
    for k in list(os.environ):
        if any(x in k for x in ('API_KEY', 'PASSWORD', 'ACCESS_TOKEN', 'WEBHOOK')) or k in (
                'LLM_CHANNELS', 'LITELLM_CONFIG', 'OPENAI_BASE_URL', 'OPENAI_API_BASE'):
            os.environ.pop(k, None)
    os.environ.update(DEEPSEEK_API_KEY='offline-placeholder-never-transmitted',
                      LITELLM_CONFIG=str(root / '.github/phase2l-deepseek.yaml'),
                      LITELLM_MODEL='deepseek/deepseek-flash', LITELLM_FALLBACK_MODELS='',
                      LITELLM_LOCAL_MODEL_COST_MAP='True', STOCK_ANALYSIS_MAX_TOKENS='16384',
                      REPORT_INTEGRITY_RETRY='0', GEMINI_REQUEST_DELAY='0', REPORT_LANGUAGE='zh',
                      AGENT_MODE='false', SINGLE_STOCK_NOTIFY='false', MARKET_REVIEW_ENABLED='false',
                      DATABASE_PATH=str(out / 'offline.sqlite'))

    def deny(*a, **kw):
        raise AssertionError('network_or_SMTP_forbidden_offline')

    connect = socket.socket.connect

    def local_only(sock, address):
        # Windows asyncio builds its self-pipe using loopback socketpair.
        if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
            return connect(sock, address)
        return deny()

    socket.socket.connect = local_only
    socket.create_connection = deny
    smtplib.SMTP = deny
    smtplib.SMTP_SSL = deny
    sys.path.insert(0, str(root))
    from authorized_once import canonical_sha, with_usage_options
    from deepseek_post_guard import OnePostGuard, PreflightIntercept
    from src.analyzer import GeminiAnalyzer
    from src.config import get_config
    from src.notification import NotificationService
    from src.trade_plan import calculate_risk_plan
    NotificationService.send = deny
    context = json.loads((fixtures / 'ORIGINAL_ENHANCED_CONTEXT.json').read_text('utf-8'))[0]
    old_packet = json.loads((fixtures / 'ORIGINAL_REQUEST_PACKET.json').read_text('utf-8'))
    old_prompt = old_packet['messages'][1]['content']
    news_match = re.search(r'## 📰 舆情情报.*?```\s*(.*?)```', old_prompt, re.S)
    assert news_match, 'Saved official news block must not be silently dropped'
    news = news_match.group(1)
    material = json.loads((fixtures / 'RESEARCH_MATERIAL_AUDIT.json').read_text('utf-8'))
    official = material['official_verification']
    context['news_source_note'] = str(context.get('news_source_note') or '') + (
        f"\n离线已保存官方财务核对：{material['official_source']}；期间截至{official['period_end']}，"
        f"公告日{official['published_date']}，币种{official['currency']}。三个金额核对不代表全部比率或归属口径已核验。")
    config = get_config()
    config.gemini_request_delay = 0
    analyzer = GeminiAnalyzer(config=config)
    assert analyzer._router and len(config.llm_model_list) == 1 and not config.litellm_fallback_models
    analyzer._router.num_retries = 0
    dispatch = analyzer._dispatch_litellm_completion

    def with_usage(model, kwargs, *a, **kw):
        return dispatch(model, with_usage_options(kwargs), *a, **kw)

    analyzer._dispatch_litellm_completion = with_usage
    guard = OnePostGuard(preflight=True)
    guard.install()
    intercepted = False
    try:
        analyzer.analyze(copy.deepcopy(context), news_context=news)
    except PreflightIntercept:
        intercepted = True
    finally:
        guard.restore()
    assert intercepted and guard.allowed == 0 and guard.attempts == 1
    wire = guard.captured[0]['body']
    assert wire['model'] == 'deepseek-flash' and wire['thinking'] == {'type': 'disabled'}
    assert wire['max_tokens'] == 16384 and wire['stream'] is True
    assert wire['stream_options'] == {'include_usage': True}
    (out / 'OFFLINE_REQUEST.json').write_text(json.dumps(wire, ensure_ascii=False, indent=2), encoding='utf-8')
    raw = (fixtures / 'MODEL_RAW_TEXT.txt').read_text('utf-8')
    old = analyzer._parse_response(raw, 'NVDA', '英伟达')
    old.raw_response = raw
    old.report_language = 'zh'
    old.market_snapshot = analyzer._build_market_snapshot(context)
    service = NotificationService()
    (out / 'PHASE2P_UNMODIFIED_REPLAY.md').write_text(service.generate_single_stock_report(old), encoding='utf-8')
    assert calculate_risk_plan(old.dashboard['battle_plan'].get('risk_plan'))[2]
    # Explicitly labeled fixture: selected old hypothetical levels are entered manually,
    # never inferred by reverse-parsing prose or presented as a new model response.
    candidate = copy.deepcopy(old)
    candidate.dashboard['battle_plan']['risk_plan'] = {
        'max_position_pct': 20,
        'scenarios': [dict(entry=e, stop=s, target=t, position_pct=pos,
                           trigger='离线假设：缩量止跌或收盘收复并明确量能基准',
                           invalidation='该情景止损或确认条件失效')
                      for e, s, t, pos in [(219.6, 219, 228.69, 10), (221, 219, 228.69, 10),
                                           (227.2, 219.63, 231.63, 20)]]}
    assert not calculate_risk_plan(candidate.dashboard['battle_plan']['risk_plan'])[2]
    text = '# 离线结构化情景演示；非新模型合格研报，AI旧原文仍待审核\n\n'
    text += service.generate_single_stock_report(candidate)
    (out / 'OFFLINE_CANDIDATE.md').write_text(text, encoding='utf-8')
    assert old.raw_response == candidate.raw_response == raw
    import tiktoken
    estimate = sum(len(tiktoken.get_encoding('cl100k_base').encode(m['content'])) for m in wire['messages']) + 4 * len(wire['messages']) + 3
    summary = {'protocol': 'native_dashboard_JSON_with_numeric_risk_plan', 'model': wire['model'],
               'thinking': wire['thinking'], 'max_tokens': wire['max_tokens'], 'stream_options': wire['stream_options'],
               'endpoint': guard.captured[0]['url'], 'offline_body_canonical_sha256': canonical_sha(wire),
               'cl100k_input_estimate_not_supplier_usage': estimate, 'real_paid_POSTs': guard.allowed,
               'intercepted_first_POST': intercepted, 'router_num_retries': analyzer._router.num_retries,
               'source_data_session': context['date'], 'source_status': 'Historical Phase2P fixture; NOT a fresh/authorized live request',
               'historical_report_publishable': False, 'offline_fixture_arithmetic_passed': True,
               'new_real_model_quality_verified': False, 'fixture_hashes': before}
    assert before == {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in fixtures.iterdir() if f.is_file()}
    (out / 'OFFLINE_RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
