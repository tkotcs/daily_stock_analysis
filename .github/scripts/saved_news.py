"""Attach saved evidence to native news artifacts without fetching or analysis."""
import copy
from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
from urllib.parse import urlsplit


def attach_saved_news_context(artifacts, packet, asof):
    if not isinstance(asof, datetime) or asof.utcoffset() is None:
        raise ValueError('news_cutoff_timezone_required')
    if not isinstance(packet, dict) or not isinstance(packet.get(artifacts.code, []), list):
        raise ValueError('news_packet_symbol_list_required')
    accepted, rejected = [], []
    if artifacts.code not in packet:
        rejected.append(dict(index=None, reason='ticker_entry_missing'))
    for index, item in enumerate(packet.get(artifacts.code, [])):
        try:
            if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key].strip() for key in ('source', 'url', 'title', 'published_at', 'fetched_at')):
                raise ValueError('news_required_metadata_missing')
            url = urlsplit(item['url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('news_https_source_required')
            published, fetched = (datetime.fromisoformat(item[key]) for key in ('published_at', 'fetched_at'))
            if published.utcoffset() is None or fetched.utcoffset() is None:
                raise ValueError('news_timestamp_timezone_required')
            if not asof - timedelta(days=3) <= published <= asof or not published <= fetched <= asof:
                raise ValueError('news_outside_cutoff_window')
            kind, text = item.get('content_kind'), item.get('text')
            if kind not in ('metadata_only', 'full_text', 'summary'):
                raise ValueError('news_content_kind_required')
            if kind == 'metadata_only' and text not in (None, ''):
                raise ValueError('news_metadata_must_not_claim_text')
            if kind in ('full_text', 'summary') and (not isinstance(text, str) or not text.strip()):
                raise ValueError('news_full_text_missing')
            if kind == 'summary' and item.get('summary_origin') != 'operator_paraphrase':
                raise ValueError('news_operator_summary_origin_required')
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest() if kind in ('full_text', 'summary') else None
            if item.get('content_sha256') not in (None, digest):
                raise ValueError('news_saved_text_sha256_mismatch')
            accepted.append(dict(item, content_sha256=digest))
        except (ValueError, TypeError) as error:
            rejected.append(dict(index=index, reason=str(error)))
    enhanced = copy.deepcopy(artifacts.enhanced_context)
    note = '已提供独立保存的新闻证据；综合新闻搜索未执行，不能据此排除其他事件。' if accepted else '没有可用的截止前新闻证据；综合新闻搜索未执行，事件风险未知。'
    enhanced.update(news_evidence_present=bool(accepted or artifacts.news_context), news_result_count=None, news_source_note=note)
    enhanced['saved_news_audit'] = dict(asof=asof.isoformat(), ticker_entry_present=artifacts.code in packet, source_scope='supplied_saved_evidence_not_search', accepted=accepted, rejected=rejected, search_performed=False, text_hash_scope='UTF8_saved_text_not_original_HTTP_bytes')
    sections = ['既有随附上下文（不计作本包近三日新闻）：\n' + artifacts.news_context] if artifacts.news_context else []
    if accepted or sections:
        sections.append(note)
    for item in accepted:
        if item['content_kind'] == 'full_text':
            content = f"已保存正文（未独立事实核验）：\n{item['text']}"
        elif item['content_kind'] == 'summary':
            content = f"已保存人工摘要（不是新闻全文，不自动视为发行人确认；媒体发布时间不等于事件生效日）：\n{item['text']}"
        else:
            content = '仅提供标题与元数据，未提供新闻全文，不推断未给出的细节。'
        sections.append(f"来源：{item['source']}\n标题：{item['title']}\n原始链接：{item['url']}\n发布时间：{item['published_at']}\n采集时间：{item['fetched_at']}\n内容类型：{item['content_kind']}\n" + content)
    return replace(artifacts, enhanced_context=enhanced, news_context='\n\n'.join(sections) or None, news_result_count=None)


def apply_saved_news_metadata(parsed, context):
    if 'saved_news_audit' in context:
        parsed.search_performed = False
        parsed.news_result_count = None
        parsed.news_evidence_present = context.get('news_evidence_present', False)
        parsed.news_source_note = context['news_source_note']
        parsed.data_sources = context['news_source_note'] + ('；' + parsed.data_sources if parsed.data_sources else '')
    return parsed


def saved_news_status(context):
    if 'saved_news_audit' not in context:
        return 'not_configured'
    return 'saved_evidence_attached_not_searched' if context['saved_news_audit']['accepted'] else 'saved_evidence_empty_or_rejected_not_searched'
