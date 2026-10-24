"""Send a full report or surviving source-backed content using one shared mail claim."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import os

from daily_briefing import (
    read, save, sha, source_check, trading_day_gate, aware, load_capture,
    load_live_bundle, SECTIONS, news_references,
)
from daily_execution_policy import execution_authority, require_mail_configuration


def optional(path):
    return read(path) if path.is_file() else {}


def surviving_model(root, session, now):
    """Filter complete, bound output by section/field; never salvage a failed stream."""
    generated = optional(root/'daily-real/STATUS.json')
    allowed = {
        'automatic_confirmed_quality_blocker_no_mail_no_retry',
        'daily_sections_missing_or_out_of_order', 'daily_text_or_citation_invalid',
        'focused_native_core_fields_missing', 'focused_risk_plan_invalid',
    }
    if generated.get('reason') not in allowed or generated.get('actual_model_POST_attempts') != 1:
        return [], []
    try:
        bundle = root/'daily-ready'
        digest = sha((bundle/'DAILY_LOCK.json').read_bytes())
        lock, _, context, _, facts, contexts = load_live_bundle(bundle, digest)
        from manual_responses_once import check_time
        check_time(lock)
        auth = read(root/'daily-real/AUTHORIZATION_USED.json')
        if (auth.get('batch_sha256') != digest or lock['target_session'] != session
                or auth.get('target_session') != session
                or auth.get('run_id') != os.environ.get('GITHUB_RUN_ID')
                or auth.get('execution_authority') != execution_authority(automatic=True)):
            raise ValueError('partial_model_binding_required')
        model = read(root/'daily-real/PARSED_MODEL_JSON.json')
        from manual_responses_once import completed_response
        response, text = completed_response((root/'daily-real/RAW_RESPONSE_BODY.bin').read_bytes())
        from src.analyzer import GeminiAnalyzer
        _, original_model = object.__new__(GeminiAnalyzer)._extract_analysis_json_object(text)
        if (response.get('model') != lock['model'] or model != original_model):
            raise ValueError('partial_complete_response_required')
        if model.get('focus_symbol') != lock['focus_symbol']:
            raise ValueError('partial_focus_mismatch')
        from manual_reports import quality_findings
        findings = quality_findings(model, context)
        blocked = [f['field_path'] for f in findings]
        # Any additional source blocker in the native review invalidates its unit too.
        review = optional(root/'daily-real/focus/QA_FINDINGS.json')
        blocked.extend(f['field_path'] for f in review.get('findings', []))
        def clean(path):
            return not any(path == p or p.startswith(path+'.') or p.startswith(path+'[')
                           or path.startswith(p+'.') for p in blocked)
        kept, removed = [], list(blocked)
        known = {'context:'+row['symbol'] for row in facts['rows']}
        # Expiration can change numbered news IDs. Never rebind an old citation.
        refs = {ref: entry for ref, entry in news_references(contexts, now).items()
                if facts.get('news_references', {}).get(ref) == entry}
        known.update(refs)
        sections = model.get('daily_sections')
        if isinstance(sections, list):
            for index, section in enumerate(sections):
                path = f'daily_sections[{index}]'
                if not isinstance(section, dict):
                    removed.append(path)
                    continue
                text, sources = section.get('text'), section.get('sources')
                if (section.get('title') not in SECTIONS or not isinstance(text, str) or not text.strip()
                        or not isinstance(sources, list)
                        or any(not isinstance(s, str) or s not in known for s in sources)
                        or (not sources and section['title'] != '今天学一个投资概念')
                        or not clean(path)):
                    removed.append(path)
                    continue
                labels = []
                for ref in sources:
                    if ref.startswith('context:'):
                        labels.append(ref.split(':', 1)[1]+'已校验日线')
                    else:
                        entry = refs[ref]
                        labels.append(link(entry['title'], entry['url']))
                kept.append((section['title'], text + (
                    '\n\n资料引用：'+'；'.join(labels) if labels else '')))
        for field in ('analysis_summary', 'trend_analysis', 'technical_analysis', 'ma_analysis',
                      'volume_analysis', 'fundamental_analysis', 'news_summary', 'risk_warning'):
            text = model.get(field)
            if isinstance(text, str) and text.strip() and clean(field):
                kept.append((lock['focus_symbol']+'研究补充 · '+field, text))
            elif text:
                removed.append(field)
        return kept, sorted(set(removed))
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        return [], ['model_binding_or_validation_unavailable']


def plain(value):
    return str(value).replace('\n', ' ').replace('\r', ' ').replace('|', r'\|')


def link(title, url):
    import html
    title = html.escape(plain(title)).replace('[', r'\[').replace(']', r'\]')
    return '['+title+'](<'+url.replace('<', '%3C').replace('>', '%3E')+'>)'


def partial_content(root, session, now):
    """Recheck sources, omit individual bad rows/units, retain useful content."""
    from daily_news import saved_feed_items
    rows, omitted = [], []
    data = root/'daily-capture'
    if (data/'RESULTS.json').is_file():
        try:
            capture = read(data/'RESULTS.json')
            if capture.get('mode') != 'LIVE_FREE_DATA_MOCK_MODEL':
                raise ValueError('live_capture_required')
            rows, _, omitted, _ = load_capture(data, session, now)
            rows = [r for r in rows
                    if now.timestamp()-86400 <= aware(r['source_fetched_at']).timestamp()
                    and not r.get('identity_limit')]
        except (ValueError, KeyError, TypeError, OSError):
            rows, omitted = [], []
    try:
        news, missing_feeds = saved_feed_items(root/'daily-news', now)
    except (ValueError, KeyError, TypeError, OSError):
        news, missing_feeds = [], ['feed_evidence_unavailable']
    sections, removed = surviving_model(root, session, now)
    audit = dict(valid_rows=len(rows), headlines=len(news), retained_model_units=len(sections),
                 omitted_model_units=removed, omitted_feed_symbols=missing_feeds,
                 natural_language_fully_verified=False, new_model_POSTs=0)
    if not rows and not news and not sections:
        return None, audit
    text = '# 美股晨报｜'+session+'（可用内容版）\n\n'
    text += ('> 部分数据或生成内容未通过检查，已剔除对应部分；以下保留可用资料。'
             '历史收盘不是实时报价，观察线和模型解释不构成交易指令。\n\n')
    if rows:
        text += '## 可用标的行情与技术观察\n\n'
        text += '| 标的 | 收盘USD | 涨跌% | MA5 / MA10 / MA20 / MA60 | 原采集时间 |\n'
        text += '|---|---:|---:|---|---|\n'
        for row in rows:
            text += ('| '+row['symbol']+f" | {row['close']:.2f} | {row['pct_chg']:+.2f} | "+
                     ' / '.join(f"{row['ma'][k]:.2f}" for k in ('ma5','ma10','ma20','ma60'))+
                     ' | '+row['source_fetched_at']+' |\n')
        text += '\n以上来自本次Yahoo原生采集与程序计算；未通过日期、数值或身份检查的标的不列数值。\n\n'
    if news:
        text += '## 公司官网动态\n\n'
        for item in news:
            text += ('- **'+item['symbol']+'** '+link(item['title'], item['url'])+
                     '；来源：'+plain(item['source'])+'；发布：'+item['published_at']+
                     '；采集：'+item['fetched_at']+'。\n')
        text += '\n仅官网标题元数据，未提供全文；有限订阅范围不代表完整新闻覆盖，不据此推断订单或利润。\n\n'
    if sections:
        text += ('## 保留的模型解读\n\n'
                 '以下为完整响应中保留的段落，已剔除规则发现问题的内容；'
                 '窄范围检查不等于自然语言事实已全面核验。未展示交易执行计划。\n\n')
        for title, body in sections:
            text += '### '+title+'\n\n'+body+'\n\n'
    text += ('## 今天学一个投资概念：数据缺口与投资风险\n\n'
             '某项报价或新闻缺失，说明这次资料覆盖不足，不能推断公司没有变化或没有风险。'
             '比较估值和盈利时应对齐交易日、报告期间与币种；'
             '单日价格变化也不能单独证明资金流向或基本面改变。\n\n')
    text += (f'本次保留{len(rows)}只有效行情、{len(news)}条官网标题、{len(sections)}段模型解读。'
             '其余内容已省略；本版不追加模型请求。后续交易日由云端自动采集、筛选并发送。\n')
    return text, audit


def notice_content(root, source):
    """No model text, stale market facts, arbitrary errors or private data in notices."""
    source_check(source)
    current = trading_day_gate(datetime.now(timezone.utc))
    calendar = read(root/'calendar.json')
    session_state = read(root/'SESSION_STATUS.json')
    session = calendar['completed_session']
    if (current.get('run') is not True or current['completed_session'] != session
            or calendar.get('run') is not True or session_state.get('run') is not True
            or session_state.get('session') != session):
        raise ValueError('current_unclaimed_trading_session_required')
    generated = optional(root/'daily-real/STATUS.json')
    if generated.get('status') == 'generated_daily_automatic_validated':
        raise ValueError('validated_report_must_use_normal_delivery')
    # Freeze the recheck cutoff for byte-identical validation immediately before SMTP.
    # Capture happens after calendar; use a bound delivery cutoff once saved.
    cutoff_file = root/'daily-notice/CUTOFF.json'
    if cutoff_file.is_file():
        cutoff = aware(read(cutoff_file)['at'])
    else:
        cutoff = datetime.now(timezone.utc)
    if not cutoff <= datetime.now(timezone.utc) or (datetime.now(timezone.utc)-cutoff).total_seconds() > 86400:
        raise ValueError('partial_delivery_cutoff_invalid')
    partial, _ = partial_content(root, session, cutoff)
    if partial:
        return partial, session
    reason = generated.get('reason')
    message = ('模型供应商返回服务过载，本日未取得可发布正文。'
               if reason == 'upstream_overloaded_no_retry' else
               '模型生成或报告质量检查未通过，本日不发布未经验证的正文。'
               if generated else
               '行情采集或资料准备未通过，本日没有足够的已核验资料生成完整研报。')
    return (
        '# 美股日报运行通知\n\n'
        '> 本邮件是故障通知，不是完整研报，不包含投资建议。\n\n'
        '目标美国交易日：' + session + '。\n\n' + message + '\n\n'
        '今天的完整研报暂不可用；没有使用旧行情、模拟数据或未通过检查的模型内容替代。\n\n'
        '本通知不追加模型请求。后续正常交易日继续按北京时间09:00启动；'
        '本通知与正式研报共用每日邮件记录，避免重复发送。\n'
    ), session


def deliver_daily(root, source, out):
    from daily_briefing_mail import deliver
    authority = execution_authority(automatic=True)
    policy = read(Path(__file__).resolve().parents[1]/'research/daily-automatic-policy.json')
    if policy.get('degraded_service_notice') is not True:
        raise ValueError('daily_notice_authorization_required')
    require_mail_configuration()
    # Never convert an ambiguous SMTP result into a second delivery.
    if out.exists():
        raise ValueError('mail_state_exists_no_retry')
    generated = optional(root/'daily-real/STATUS.json')
    if generated.get('status') == 'generated_daily_automatic_validated':
        report = root/'daily-real/DAILY_REPORT.md'
        return deliver(report, source, out, sha(report.read_bytes()), send=True, automatic=True)
    folder = root/'daily-notice'
    folder.mkdir(exist_ok=False)
    save(folder/'CUTOFF.json', dict(at=datetime.now(timezone.utc).isoformat()))
    content, session = notice_content(root, source)
    report = folder/'DAILY_REPORT.md'
    report.write_bytes(content.encode('utf-8'))
    _, audit = partial_content(root, session, aware(read(folder/'CUTOFF.json')['at']))
    save(folder/'FILTER_AUDIT.json', audit)
    import markdown2
    from manual_reports import page
    (folder/'DAILY_REPORT.html').write_text(page('美股晨报', markdown2.markdown(
        content, extras=['tables'], safe_mode='escape')), encoding='utf-8')
    digest = sha(report.read_bytes())
    save(folder/'STATUS.json', dict(status='daily_service_notice',
                                   program_validation_passed=True, report_sha256=digest))
    save(folder/'AUTHORIZATION_USED.json', dict(
        execution_authority=authority, run_id=os.environ['GITHUB_RUN_ID'],
        focus_symbol='DAILY_NOTICE', target_session=session))
    return deliver(report, source, out, digest, send=True, automatic=True, notice_root=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = deliver_daily(args.root, args.source, args.out)
    print(json.dumps(result))
    if result['status'] != 'delivered':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
