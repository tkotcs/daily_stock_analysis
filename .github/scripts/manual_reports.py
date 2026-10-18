"""Local readable views and usage totals; never modify model narrative."""
import html
import json
from decimal import Decimal


def page(title, body):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:auto;padding:20px;overflow-wrap:anywhere}pre{white-space:pre-wrap}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ccc;text-align:left}details{margin:12px 0}</style><body>' + body + '</body></html>'


def save_full_report(directory, symbol, model, context, computed_facts, simulated):
    label = '模拟模型输出，非真实研究' if simulated else '模型输出原文，仅排版，待人工审核'
    model_text = json.dumps(model, ensure_ascii=False, indent=2)
    sections = ['<h1>' + html.escape(symbol) + ' 完整模型字段</h1><p>' + label + '</p>']
    for field, value in model.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        sections.append('<section><h2>' + html.escape(field) + '</h2><pre>' + html.escape(text) + '</pre></section>')
    (directory / 'MODEL_ALL_FIELDS.html').write_text(page(symbol, ''.join(sections)), encoding='utf-8')
    (directory / 'MODEL_COMPLETE.html').write_text(page(symbol, '<h1>完整模型 JSON</h1><p>' + label + '</p><pre>' + html.escape(model_text) + '</pre>'), encoding='utf-8')
    facts = {'computed_quote_facts': computed_facts, 'fundamental_context': context.get('fundamental_context'), 'official_research': context.get('official_research')}
    (directory / 'PROGRAM_FACTS.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (directory / 'PROGRAM_FACTS.html').write_text(page(symbol, '<h1>程序事实与随附财务来源</h1><p>此部分不是模型输出；缺失信息不代表已经核实。</p><pre>' + html.escape(json.dumps(facts, ensure_ascii=False, indent=2, default=str)) + '</pre>'), encoding='utf-8')
    markdown = '# ' + symbol + ' 完整模型字段\n\n> ' + label + '\n\n'
    for field, value in model.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        markdown += '## ' + field + '\n\n' + '\n'.join('    ' + line for line in text.splitlines()) + '\n\n'
    (directory / 'MODEL_ALL_FIELDS.md').write_text(markdown, encoding='utf-8')


def record_outputs(row, directory, simulated):
    response_path = directory / 'RESPONSE_RESULT.json'
    if response_path.exists():
        response = json.loads(response_path.read_text('utf-8'))
        row['usage'] = response.get('usage')
        row['cost_estimate'] = response.get('cost_estimate')
        row['elapsed_seconds'] = response.get('elapsed_seconds')
    row['usage_source'] = 'synthetic_test_only' if simulated else 'supplier_response'
    names = ('REPORT.html', 'REPORT.md', 'MODEL_ALL_FIELDS.html', 'MODEL_ALL_FIELDS.md', 'MODEL_COMPLETE.html', 'MODEL_RAW_TEXT.txt', 'MODEL_REASONING_TEXT.txt', 'PROGRAM_FACTS.html', 'PROGRAM_FACTS.json', 'RESPONSE_RESULT.json')
    row['artifacts'] = {name: row['symbol'] + '/' + name for name in names if (directory / name).is_file()}


def summarize_usage(rows, simulated):
    total = dict(source='synthetic_test_only' if simulated else 'supplier_response', input_tokens=0, output_tokens=0, reported_reasoning_tokens=0, missing_reasoning_fields=0, missing_usage_requests=0, actual_paid_POSTs=sum(row.get('actual_paid_POSTs', 0) for row in rows), known_peak_subtotal_usd='0', known_off_peak_subtotal_usd='0', fee_is_supplier_bill=False, reasoning_already_in_output=True)
    peak, off_peak = Decimal('0'), Decimal('0')
    for row in rows:
        if not row.get('transport_attempts'):
            continue
        usage = row.get('usage') or {}
        cost = row.get('cost_estimate') or {}
        fields = [usage.get('prompt_tokens'), usage.get('completion_tokens')]
        if any(type(value) is not int or value < 0 for value in fields) or cost.get('status') != 'estimated_not_supplier_bill':
            total['missing_usage_requests'] += 1
            continue
        total['input_tokens'] += fields[0]
        total['output_tokens'] += fields[1]
        reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
        if reasoning is None:
            total['missing_reasoning_fields'] += 1
        else:
            total['reported_reasoning_tokens'] += reasoning
        peak += Decimal(cost['peak_usd'])
        off_peak += Decimal(cost['off_peak_usd'])
    total.update(known_peak_subtotal_usd=str(peak), known_off_peak_subtotal_usd=str(off_peak), complete=total['missing_usage_requests'] == 0, estimated_peak_usd=None if total['missing_usage_requests'] else str(peak), estimated_off_peak_usd=None if total['missing_usage_requests'] else str(off_peak))
    return total


def render_status_index(rows, mode, usage=None):
    simulated = mode == 'SIMULATED'
    body = '<h1>手动研究报告目录</h1><p>' + ('合成数据/模拟模型，不是真实行情或研究验收。' if simulated else '真实模型报告仍待人工审核，执行成功不等于研究正确。') + '</p>'
    if usage is not None:
        body += '<h2>批次用量与费用估算</h2><p>推理 Token 已含在输出中，不重复计费；费用不是供应商账单。缺失响应显示未知，不按零费用处理。</p><pre>' + html.escape(json.dumps(usage, ensure_ascii=False, indent=2)) + '</pre>'
    body += '<table><thead><tr><th>标的</th><th>模式</th><th>执行/审核</th><th>报告</th><th>输入/输出 Token</th></tr></thead><tbody>'
    labels = {'REPORT.html': '原版HTML', 'REPORT.md': '原版Markdown', 'MODEL_ALL_FIELDS.html': '完整模型字段', 'MODEL_ALL_FIELDS.md': '全字段Markdown', 'MODEL_COMPLETE.html': '模型JSON', 'MODEL_RAW_TEXT.txt': '模型原文', 'MODEL_REASONING_TEXT.txt': '推理原文', 'PROGRAM_FACTS.html': '程序事实/财务来源', 'RESPONSE_RESULT.json': '真实响应/Usage'}
    if simulated:
        labels['RESPONSE_RESULT.json'] = '模拟响应/Usage'
    for row in rows:
        symbol = row['symbol']
        artifacts = row.get('artifacts')
        if artifacts is None:
            artifacts = {name: symbol + '/' + name for name in ('REPORT.html', 'REPORT.md')} if row.get('execution_success') else {}
        links = ['<a href="' + html.escape(path, quote=True) + '">' + labels[name] + '</a>' for name, path in artifacts.items() if name in labels]
        links.append('<a href="' + html.escape(symbol + '/STATUS.json', quote=True) + '">状态</a>')
        state = '执行成功 / 待人工审核 / 未发布' if row.get('execution_success') else '执行失败 / 未发布：' + row.get('reason', row.get('status', ''))
        tokens = row.get('usage') or {}
        body += '<tr><td>' + html.escape(symbol) + '</td><td>' + html.escape(row.get('comparison_mode') or 'nonthinking') + '</td><td>' + html.escape(state) + '</td><td>' + ' · '.join(links) + '</td><td>' + html.escape(str(tokens.get('prompt_tokens', '未知')) + '/' + str(tokens.get('completion_tokens', '未知'))) + '</td></tr>'
    return page('DSA 手动报告目录', body + '</tbody></table>')
