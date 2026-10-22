"""Offline rendering of an existing paid response; no API request is possible."""
import argparse,dataclasses,hashlib,json,os,pathlib,smtplib,socket,sys,ipaddress

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True)
    p.add_argument('--evidence',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--rebuild-snapshot',action='store_true',help='Regenerate display only from frozen quotes; preserve raw model text.')
    a=p.parse_args()
    src=pathlib.Path(a.source).resolve();e=pathlib.Path(a.evidence).resolve()
    out=pathlib.Path(a.out).resolve();out.mkdir(exist_ok=False)
    def hashes():
        return {x.relative_to(e).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(e.rglob('*')) if x.is_file()}
    before=hashes()
    # Clear inherited credentials; do not load a user .env or initialize a client.
    for k in list(os.environ):
        if any(s in k for s in ('API_KEY','PASSWORD','WEBHOOK','ACCESS_TOKEN')):os.environ.pop(k,None)
    os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True',SCHEDULE_ENABLED='false',SINGLE_STOCK_NOTIFY='false',REPORT_LANGUAGE='zh')
    def deny(*args,**kwargs):raise RuntimeError('offline_replay_network_forbidden')
    original_connect=socket.socket.connect
    def connect(sock,address):
        if isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback:return original_connect(sock,address)
        raise RuntimeError('offline_replay_external_network_forbidden')
    socket.socket.connect=connect;socket.create_connection=deny
    smtplib.SMTP=deny;smtplib.SMTP_SSL=deny
    sys.path.insert(0,str(src))
    from src.analyzer import AnalysisResult,GeminiAnalyzer
    from src.notification import NotificationService
    from nvda_frozen_once import render_native_report
    NotificationService.send=deny
    raw=(e/'artifacts/MODEL_RAW_TEXT.txt').read_text(encoding='utf-8')
    # Parsing needs no initialized LLM client. It is the original upstream parser.
    analyzer=object.__new__(GeminiAnalyzer)
    parsed=analyzer._parse_response(raw,'NVDA','英伟达')
    assert parsed.success
    saved=json.loads((e/'artifacts/NATIVE_ANALYSIS_RESULT.json').read_text(encoding='utf-8'))
    allowed={f.name for f in dataclasses.fields(AnalysisResult)}
    result=AnalysisResult(**{k:v for k,v in saved.items() if k in allowed})
    assert parsed.dashboard==result.dashboard
    if a.rebuild_snapshot:
        context=json.loads((e/'input-evidence/ORIGINAL_ENHANCED_CONTEXT.json').read_text(encoding='utf-8'))[0]
        result.market_snapshot=analyzer._build_market_snapshot(context)
    report=render_native_report(result)
    assert 'NVDA' in report and '221.30' in report and len(report)>500
    (out/'NATIVE_NVDA_REPORT.md').write_text(report,encoding='utf-8')
    import markdown2
    body=markdown2.markdown(report,safe_mode='escape',extras=['tables'])
    (out/'NVDA_OFFLINE_PREVIEW.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NVDA离线回放审阅稿</title><style>body{font:16px/1.7 system-ui;max-width:960px;margin:24px auto;padding:16px;overflow-wrap:anywhere}table{display:block;overflow:auto;border-collapse:collapse}td,th{padding:8px;border:1px solid #ddd}.notice{padding:16px;background:#fff3cd}</style><body><div class="notice">Phase 2F断网回放：仅供审阅。行情日2026-10-14，页面正文时间为离线渲染时间。本报告来自已保存的真实响应，未经模型重写，已知事实问题尚未修正，不能发布；不是新增研究或新的实时行情。</div>'+body+'</body></html>',encoding='utf-8')
    after=hashes();assert before==after
    checks={'display_snapshot_regenerated':a.rebuild_snapshot,'model_text_unchanged':True,'new_model_requests':0,'network_connections_allowed':0,'mail_allowed':False,'raw_parser_success':parsed.success,'dashboard_equal_to_original_saved_parse':True,'native_renderer_success':True,'original_evidence_unchanged':before==after,'original_evidence_hashes':before,'source':str(src),'constructor':'NotificationService()','raw_model_text_sha256':hashlib.sha256(raw.encode()).hexdigest()}
    (out/'REPLAY_RESULT.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: native raw parsing + corrected native rendering; network denied; original evidence unchanged.')

if __name__=='__main__':main()
