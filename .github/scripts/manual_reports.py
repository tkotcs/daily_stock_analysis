"""Local readable views and usage totals; never modify model narrative."""
import html
import json
import re
from decimal import Decimal


def page(title, body):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:auto;padding:20px;overflow-wrap:anywhere}pre{white-space:pre-wrap}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ccc;text-align:left}details{margin:12px 0}</style><body>' + body + '</body></html>'


def quality_findings(model, context):
    findings = []
    today, yesterday = context.get('today') or {}, context.get('yesterday') or {}
    plan = ((model.get('dashboard') or {}).get('battle_plan') or {}).get('risk_plan') or {}
    scenario_ids = {str(item.get('id')) for item in plan.get('scenarios', []) if isinstance(item, dict) and item.get('id')}

    def add(path, original, category, evidence, recommendation):
        findings.append(dict(field_path=path, original_content=original, category=category, evidence=evidence, recommendation=recommendation))

    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, path + '.' + key if path else key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f'{path}[{index}]')
        elif isinstance(value, str):
            for match in re.finditer(r'MA(?:5|10|20|60)(?:\s*[<>]\s*MA(?:5|10|20|60))+', value, re.I):
                chain = match.group()
                before = re.split('[。；]', value[:match.start()])[-1]
                after = re.split('[。；]', value[match.end():])[0]
                if re.search(r'(?:必须|务必)(?:先)?(?:确认|满足|形成)\s*$', before):
                    continue
                # A directly awaited order or an open question about forming it
                # describes a future check, irrespective of the JSON field.
                # Stop at punctuation so a later current-state assertion is checked.
                if (re.search(r'(?:等待|待)(?:确认|形成|恢复|达到)?\s*$', before)
                        or re.search(r'(?:能否|是否)[^，,。；;！？!?]*(?:形成|恢复|达到)\s*$', before)):
                    continue
                if re.search('不满足|未满足|不成立|不符合|未形成|必要|条件|前提|要求|需|互斥|不将', before + after):
                    continue
                names = re.findall(r'MA(?:5|10|20|60)', chain, re.I)
                values = [today.get(name.lower()) for name in names]
                operators = re.findall('[<>]', chain)
                if all(type(number) in (int, float) for number in values) and any(not (left < right if operator == '<' else left > right) for left, operator, right in zip(values, operators, values[1:])):
                    add(path, value, 'MA_ORDER_CONTRADICTION', dict(claim=chain, actual={name: number for name, number in zip(names, values)}), '以程序数值排序为准；不修改原文，不将部分均线排列扩展为完整四线排列。')
            low = today.get('low')
            previous_low = yesterday.get('low')
            if type(low) in (int, float) and type(previous_low) in (int, float) and round(low, 2) != round(previous_low, 2):
                shown = f'{low:.2f}'
                if '前低' in value or '前日低点' in value or '前一交易日低点' in value:
                    if re.search(re.escape(shown) + r'.{0,12}(?:前低|前日低点|前一交易日低点)|(?:前低|前日低点|前一交易日低点).{0,12}' + re.escape(shown), value):
                        add(path, value, 'LOW_DATE_REFERENCE_REVIEW', dict(target_session=today.get('date'), target_low=low, previous_session=yesterday.get('date'), previous_low=previous_low), '此价为目标日低点；前日称谓不符，其他历史前低须另有历史证据，不能直接判定历史支撑不存在。')
            if path.startswith('dashboard.battle_plan.') and '.risk_plan.' not in path:
                references = set(re.findall(r'情景\s*([A-Z][A-Z0-9]*)(?![A-Z0-9])', value))
                missing = sorted(references - scenario_ids)
                if missing:
                    add(path, value, 'UNDEFINED_SCENARIO_REFERENCE', dict(referenced=sorted(references), defined=sorted(scenario_ids), missing=missing), '引用的情景必须存在；观望且无情景时，不展示这些文字为可执行交易计划。')
                elif not scenario_ids and re.search(r'risk_plan\s*情景', value):
                    add(path, value, 'EMPTY_SCENARIO_DEPENDENCY', dict(defined=[], risk_mode=plan.get('mode')), '此文字依赖未定义的结构化情景；仅作观察条件，不补造情景或声称计划可执行。')
                if re.search(r'risk_plan\s*中\s*防守观察条件', value) and not any(key in plan for key in ('risk_control', 'defensive_conditions')):
                    add(path, value, 'RISK_PLAN_REFERENCE_PATH_REVIEW', dict(risk_plan_keys=sorted(plan), alternative_path='dashboard.battle_plan.position_strategy.risk_control'), '核查引用路径；自由文本观察条件不等于risk_plan结构化字段，不自动迁移或补造。')
    walk(model, '')
    if model.get('action') == 'buy' or model.get('decision_type') == 'buy':
        add('action/decision_type/operation_advice', {key: model.get(key) for key in ('action', 'decision_type', 'operation_advice')}, 'CONDITIONAL_ENTRY_NOT_VERIFIED', dict(risk_mode=plan.get('mode'), scenario_ids=sorted(scenario_ids), trigger_evaluation='not_performed'), '仅显示条件性计划，非即时买入指令；模型自称触发不等于程序核验，未建立触发核验前保持未发布。')
    labels = {key: model.get(key) for key in ('action', 'decision_type', 'operation_advice')}
    normalized = [dict(buy='buy', sell='sell', watch='watch', hold='hold', 买入='buy', 卖出='sell', 观望='watch', 持有='hold').get(value) for value in labels.values() if isinstance(value, str)]
    known = {value for value in normalized if value}
    if ('buy' in known or 'sell' in known) and len(known) > 1:
        add('action/decision_type/operation_advice', labels, 'DECISION_LABEL_SCOPE_REVIEW', dict(normalized=normalized, risk_mode=plan.get('mode')), '决策标签不一致或对象范围不同，须人工对照持仓者/新增仓位语境；不自动选取买卖标签、不改原文。')
    return findings


def save_quality_review(directory, symbol, model, context, additional_findings=()):
    evidence_states = {
        'MA_ORDER_CONTRADICTION': 'CONFIRMED_CONTRADICTION',
        'UNDEFINED_SCENARIO_REFERENCE': 'CONFIRMED_CONTRADICTION',
        'EMPTY_SCENARIO_DEPENDENCY': 'CONFIRMED_CONTRADICTION',
        'CASH_CONVERSION_INTERPRETATION': 'CONFIRMED_CONTRADICTION',
        'BLOCKED_PERIOD_MAPPING': 'SOURCE_BLOCKER',
        'CONDITIONAL_ENTRY_NOT_VERIFIED': 'INTERPRETATION_LIMITATION',
        'ESTIMATE_NOT_REPORTED_QUARTERLY_INCOME': 'INTERPRETATION_LIMITATION',
    }
    findings = []
    for origin, items in (('automatic_narrow_rule', quality_findings(model, context)), ('operator_supplied_review', additional_findings)):
        for item in items:
            findings.append(dict(item, discovery_origin=origin, evidence_status=evidence_states.get(item.get('category'), 'REVIEW_CANDIDATE')))
    today = context.get('today') or {}
    averages = sorted(((name.upper(), today[name]) for name in ('ma5', 'ma10', 'ma20', 'ma60') if type(today.get(name)) in (int, float)), key=lambda item: item[1])
    review = dict(symbol=symbol, published=False, quality_accepted=False, scope='narrow_deterministic_checks_plus_explicit_review_findings_not_exhaustive', action_display='条件性计划/未核实触发，非即时指令', authoritative_ma_order=averages, evidence_status_counts={status: sum(item['evidence_status'] == status for item in findings) for status in ('CONFIRMED_CONTRADICTION', 'REVIEW_CANDIDATE', 'SOURCE_BLOCKER', 'INTERPRETATION_LIMITATION')}, findings=findings)
    text = json.dumps(review, ensure_ascii=False, indent=2)
    (directory / 'QA_FINDINGS.json').write_text(text, encoding='utf-8')
    markdown = '# ' + symbol + ' 独立质量审核\n\n> 未发布。原始模型文字不变；检查无发现不等于事实全部正确。此页不是新模型研究或新Usage。\n\n'
    markdown += '均线数值升序（相等值不代表严格小于）：' + '，'.join(f'{name}={value:g}' for name, value in averages) + '\n\n'
    markdown += '日线OHLCV不能证明尾盘路径、主动买卖方向或抛压是否出尽。财务解释只在期间、币种、来源及非估算口径均有证据时成立。\n\n'
    session_rows = []
    for bar in (context.get('today') or {}, context.get('yesterday') or {}):
        if bar.get('date') and all(type(bar.get(key)) in (int, float) for key in ('high', 'low')):
            session_rows.append(f"| {bar['date']} | {bar['high']:.2f} | {bar['low']:.2f} |")
    if session_rows:
        markdown += '日线日期对照（引用高低点时请写具体日期；不推定其他历史高低点或支撑有效性）：\n\n'
        markdown += '| 交易日 | 最高 | 最低 |\n|---|---:|---:|\n' + '\n'.join(session_rows) + '\n\n'
    markdown += '```json\n' + text + '\n```\n'
    (directory / 'QUALITY_REVIEW.md').write_text(markdown, encoding='utf-8')
    (directory / 'QUALITY_REVIEW.html').write_text(page(symbol + ' 独立质量审核', '<h1>独立审核，不改写模型原文</h1><p>未发布；条件性计划并非即时指令。检查无发现不等于事实全部正确。</p><pre>' + html.escape(markdown) + '</pre>'), encoding='utf-8')
    return review


def save_full_report(directory, symbol, model, context, computed_facts, simulated, additional_findings=()):
    save_quality_review(directory, symbol, model, context, additional_findings)
    label = '模拟模型输出，非真实研究' if simulated else '模型输出原文，仅排版，待人工审核'
    model_text = json.dumps(model, ensure_ascii=False, indent=2)
    sections = ['<h1>' + html.escape(symbol) + ' 完整模型字段</h1><p>' + label + '</p><p><a href="QUALITY_REVIEW.html">独立质量审核：条件性计划非即时指令</a></p>']
    for field, value in model.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        sections.append('<section><h2>' + html.escape(field) + '</h2><pre>' + html.escape(text) + '</pre></section>')
    (directory / 'MODEL_ALL_FIELDS.html').write_text(page(symbol, ''.join(sections)), encoding='utf-8')
    (directory / 'MODEL_COMPLETE.html').write_text(page(symbol, '<h1>完整模型 JSON</h1><p>' + label + '</p><pre>' + html.escape(model_text) + '</pre>'), encoding='utf-8')
    facts = {'computed_quote_facts': computed_facts, 'fundamental_context': context.get('fundamental_context'), 'official_research': context.get('official_research'), 'financial_field_provenance': context.get('financial_field_provenance'), 'financial_input_restriction': context.get('financial_input_restriction'), 'independent_financial_evidence': context.get('financial_evidence')}
    if 'saved_news_audit' in context:
        facts['saved_news_evidence'] = context['saved_news_audit']
    if 'dividend_announcement_audit' in context:
        facts['dividend_announcement_evidence'] = context['dividend_announcement_audit']
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
    names = ('REPORT.html', 'REPORT.md', 'MODEL_ALL_FIELDS.html', 'MODEL_ALL_FIELDS.md', 'MODEL_COMPLETE.html', 'MODEL_RAW_TEXT.txt', 'MODEL_REASONING_TEXT.txt', 'PROGRAM_FACTS.html', 'PROGRAM_FACTS.json', 'RESPONSE_RESULT.json', 'QUALITY_REVIEW.html', 'QUALITY_REVIEW.md', 'QA_FINDINGS.json')
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
    labels.update({'QUALITY_REVIEW.html': '独立质量审核', 'QUALITY_REVIEW.md': '审核Markdown', 'QA_FINDINGS.json': '问题证据JSON'})
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
