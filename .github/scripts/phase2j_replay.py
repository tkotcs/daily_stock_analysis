"""Read-only historical response replay through the current native renderer."""
import argparse
import copy
import hashlib
import ipaddress
import json
import os
import pathlib
import shutil
import smtplib
import socket
import sys
from unittest.mock import patch


def main():
    p = argparse.ArgumentParser()
    for name in ('phase2e', 'phase2h', 'inputs', 'out'):
        p.add_argument('--' + name, type=pathlib.Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    for key in list(os.environ):
        if any(s in key for s in ('API_KEY', 'PASSWORD', 'ACCESS_TOKEN', 'WEBHOOK')):
            os.environ.pop(key, None)
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    original = socket.socket.connect

    def deny(*args, **kwargs):
        raise AssertionError('offline_replay_network_or_mail_forbidden')

    def connect(sock, address):
        if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
            return original(sock, address)
        return deny()

    socket.socket.connect = connect
    socket.create_connection = deny
    smtplib.SMTP = deny
    smtplib.SMTP_SSL = deny
    import litellm
    import markdown2
    import pandas as pd
    litellm.completion = deny
    litellm.acompletion = deny
    from src.analyzer import GeminiAnalyzer
    from src.notification import NotificationService
    from nvda_frozen_once import apply_supplied_news_metadata, render_native_report
    from authorized_once import canonical_sha, FIXED
    NotificationService.send = deny

    def load(path):
        return json.loads(path.read_text(encoding='utf-8'))

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    monitored = [a.phase2e, a.phase2h, a.inputs]
    def inventory():
        return {f'{i}/{f.relative_to(folder).as_posix()}': sha(f)
                for i, folder in enumerate(monitored) for f in folder.rglob('*') if f.is_file()}
    before = inventory()
    packet = load(a.inputs/'ORIGINAL_REQUEST_PACKET.json')
    assert canonical_sha(packet) == 'f7ca322b236ff4b993a081e33090740eb9891fa584f0abf33dbab0677cf88e3b'
    context = load(a.inputs/'ORIGINAL_ENHANCED_CONTEXT.json')[0]
    audit = load(a.inputs/'RESEARCH_MATERIAL_AUDIT.json')
    with patch.object(GeminiAnalyzer, '_init_litellm', return_value=None):
        analyzer = GeminiAnalyzer()
    analyzer._call_litellm = deny
    renderer = NotificationService()
    records = []
    for label, folder, expected in [
        ('2E', a.phase2e, 'a3a89aa016f9aac36c9d31b827f3dc4092edd76c98f025954a0bf993e5030af7'),
        ('2H', a.phase2h, '56e31c23a168f05585af62838779a44e6128ce41389c6954c3b9e10519eded2b'),
    ]:
        path = folder/'MODEL_RAW_TEXT.txt'
        assert sha(path) == expected
        raw = path.read_text(encoding='utf-8')
        parsed = analyzer._parse_response(raw, 'NVDA', '英伟达')
        assert parsed.success
        parsed.raw_response = raw
        parsed.market_snapshot = load(folder/'NATIVE_ANALYSIS_RESULT.json').get('market_snapshot')
        parsed.report_language = 'zh'
        apply_supplied_news_metadata(parsed, [context], audit if label == '2H' else {})
        complete, missing = analyzer._check_content_integrity(parsed)
        assert complete, (label, missing)
        disclosure = renderer._empty_news_disclosure(parsed, 'zh')
        assert (disclosure is None) is (label == '2H')
        for kind, md in [('DETAILED', renderer.generate_daily_report([parsed], report_date='2026-10-15')),
                         ('SHORT', render_native_report(parsed))]:
            (a.out/f'{label}_{kind}.md').write_text(md, encoding='utf-8')
            warning = '<p style="background:#fff3cd;padding:12px">历史真实响应离线回放，未通过发布验收。只补充程序新闻元数据，模型正文不修改；不是新提示词的生成结果。</p>'
            page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{max-width:1000px;margin:auto;padding:16px;font:16px/1.7 system-ui;overflow-wrap:anywhere}table{display:block;overflow:auto}td,th{border:1px solid #ddd;padding:6px}</style><body>' + warning + markdown2.markdown(md, safe_mode='escape', extras=['tables']) + '</body></html>'
            (a.out/f'{label}_{kind}.html').write_text(page, encoding='utf-8')
        shutil.copyfile(path, a.out/f'{label}_RAW_MODEL_TEXT.txt')
        records.append({'sample': label, 'raw_sha256': expected, 'native_parse_passed': True,
                        'native_structure_passed': complete, 'disclosure': disclosure,
                        'search_performed': parsed.search_performed,
                        'news_evidence_present': parsed.news_evidence_present,
                        'new_model_requests': 0, 'original_text_edited': False, 'publish_quality_passed': False})
    # Deterministic facts from the locked inputs, with a real 60-row window.
    context = copy.deepcopy(context)
    frame = pd.DataFrame(load(a.inputs/'NVDA_PREFILL_ROWS.json')).sort_values('date')
    for offset, name in ((0, 'today'), (1, 'yesterday')):
        context[name]['ma60'] = float(frame.close.iloc[:len(frame)-offset].tail(60).mean())
    facts = analyzer._format_computed_quote_facts(context)
    assert '低开' in facts and '本日收盘新下穿' in facts
    assert 'close 高于 MA60=' in facts
    assert '高开低走' in (a.phase2h/'MODEL_RAW_TEXT.txt').read_text(encoding='utf-8')
    (a.out/'COMPUTED_HISTORICAL_FACTS.txt').write_text(facts, encoding='utf-8')
    assert inventory() == before
    (a.out/'REPLAY_RESULT.json').write_text(json.dumps({
        'samples': records, 'historical_files_unchanged': True, 'historical_hashes': before,
        'old_live_controller_pin_unchanged': FIXED,
        'controller_mock_compatibility_only': True, 'new_paid_request_authorized': False,
        'paid_POSTs': 0, 'mail_sent': 0, 'external_network_denied': True,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS two historical native parses, structure checks and Markdown/HTML renders; original bytes unchanged; no model or mail.')


if __name__ == '__main__':
    main()
