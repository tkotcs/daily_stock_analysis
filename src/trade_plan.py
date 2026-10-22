"""Arithmetic for explicit, hypothetical LONG plans; never infer prices from prose.

This is a report calculation, not price validation or an order/execution engine.
The original model narrative remains unchanged. Invalid plans fail closed.
"""
import math


def is_watch_plan(plan):
    """Explicit no-new-trade plans, including the saved zero/null legacy response."""
    if not isinstance(plan, dict) or type(plan.get('max_position_pct')) not in (int, float) or plan['max_position_pct'] != 0:
        return False
    scenarios = plan.get('scenarios')
    if plan.get('mode') == 'watch' and scenarios == []:
        return True
    return (plan.get('mode') in (None, 'watch') and isinstance(scenarios, list)
            and 0 < len(scenarios) <= 4 and all(isinstance(s, dict)
            and all(s.get(k) is None for k in ('entry', 'stop', 'target'))
            and type(s.get('position_pct')) in (int, float) and s['position_pct'] == 0
            and all(isinstance(s.get(k), str) and s[k].strip() for k in ('trigger', 'invalidation'))
            for s in scenarios))


def calculate_risk_plan(plan):
    """Return (calculated rows, maximum position, errors), without mutating plan."""
    if not isinstance(plan, dict):
        return [], None, ['missing_structured_risk_plan']

    def number(value, *, zero=False):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('numeric_value_required')
        if not math.isfinite(value) or value < 0 or (value == 0 and not zero):
            raise ValueError('invalid_numeric_value')
        return float(value)

    rows, errors = [], []
    try:
        cap = number(plan.get('max_position_pct'), zero=True)
        existing = plan.get('existing_position_cap_pct')
        if existing is not None and number(existing, zero=True) > 100:
            raise ValueError('invalid_existing_position_cap')
        if cap > 100:
            raise ValueError('position_over_100')
    except ValueError as exc:
        return [], None, [str(exc)]
    if is_watch_plan(plan):
        return [], 0, []
    if plan.get('mode') not in (None, 'trade'):
        return [], cap, ['invalid_trade_mode']
    scenarios = plan.get('scenarios')
    if not isinstance(scenarios, list) or not scenarios or len(scenarios) > 4:
        return [], cap, ['one_to_four_scenarios_required']
    for i, item in enumerate(scenarios):
        try:
            if not isinstance(item, dict):
                raise ValueError('scenario_object_required')
            entry, stop = number(item.get('entry')), number(item.get('stop'))
            position = number(item.get('position_pct'), zero=True)
            target = number(item['target']) if item.get('target') is not None else None
            if stop >= entry or (target is not None and target <= entry):
                raise ValueError('long_plan_requires_stop_below_entry_target_above')
            if position > cap:
                raise ValueError('position_exceeds_shared_cap')
            if not all(isinstance(item.get(k), str) and item[k].strip() for k in ('trigger', 'invalidation')):
                raise ValueError('trigger_and_invalidation_required')
            loss = (entry - stop) / entry * 100
            rr = (target - entry) / (entry - stop) if target is not None else None
            if not math.isfinite(loss) or (rr is not None and not math.isfinite(rr)):
                raise ValueError('nonfinite_calculation')
            rows.append(dict(entry=entry, stop=stop, target=target, position_pct=position,
                             loss_pct=loss, reward_risk=rr, trigger=item['trigger'],
                             invalidation=item['invalidation']))
        except (ValueError, OverflowError) as exc:
            errors.append(f'scenario_{i + 1}:{exc}')
    return ([] if errors else rows), cap, errors


def format_risk_plan(plan, *, english=False):
    """A single position source and computed arithmetic; no legacy prose parsing."""
    if plan is None:
        return ('No new trade plan supplied; watch only. Existing exposure is unknown.' if english else
                '未提供新增交易计划：按观望展示，不虚构入场/止损；现有持仓建议未核验。')
    rows, cap, errors = calculate_risk_plan(plan)
    if errors:
        return ('Risk plan unverified; do not use model arithmetic/position prose. ' if english else
                '风险计划未核验，不采用模型算术或仓位文案：') + ', '.join(errors)
    existing = plan.get('existing_position_cap_pct')
    holdings = (f'Existing-position cap: {existing:g}%.' if english else f'现有持仓上限：{existing:g}%。') if existing is not None else (
        'Existing-position cap not supplied; do not infer it from the new-exposure cap.' if english else
        '现有持仓上限未提供，不能由新增仓位上限推断；模型原文另行审阅。')
    if is_watch_plan(plan):
        return ('Watch only; new-position cap 0%; no invented entry/stop/target. ' if english else
                '观望：新增仓位上限0%，无新增交易情景，不虚构入场/止损/目标。') + holdings
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = [f'Python-calculated hypothetical long plan; shared position cap {cap:g}%.' if english else
             f'Python确定性计算的假设做多情景；统一仓位上限{cap:g}%（仅新增仓位）。',
             '| Entry | Stop | Target | Loss % | Reward/risk | Position % | Trigger | Invalidation |' if english else
             '| 入场 | 止损 | 目标 | 名义损失% | 收益风险比 | 仓位% | 触发 | 失效 |',
             '|---|---|---|---|---|---|---|---|']
    for row in rows:
        target = f"{row['target']:g}" if row['target'] is not None else 'N/A'
        rr = f"{row['reward_risk']:.3f}" if row['reward_risk'] is not None else 'N/A'
        lines.append(f"| {row['entry']:g} | {row['stop']:g} | {target} | {row['loss_pct']:.3f} | {rr} | {row['position_pct']:g} | {cell(row['trigger'])} | {cell(row['invalidation'])} |")
    lines.append('Program-generated scenario summary from risk_plan (not model prose):' if english else
                 '程序依据risk_plan生成的情景摘要（非模型原文）：')
    for index, row in enumerate(rows, 1):
        target = f"{row['target']:g}" if row['target'] is not None else 'N/A'
        rr = f"{row['reward_risk']:.3f}" if row['reward_risk'] is not None else 'N/A'
        lines.append((f"S{index}: hypothetical entry {row['entry']:g}, stop {row['stop']:g}, target {target}; "
                      f"nominal loss {row['loss_pct']:.3f}%, reward/risk {rr}." if english else
                      f"S{index}：假设入场{row['entry']:g}，止损{row['stop']:g}，目标{target}；"
                      f"名义损失{row['loss_pct']:.3f}%，收益风险比{rr}。"))
    lines.append('Assumptions, not verified target forecasts; excludes fees, gaps and slippage.' if english else
                 '情景参数来自模型假设，不是已证实的目标价；未计费用、跳空和滑点，不保证实际损失。')
    lines.append(holdings)
    return '\n'.join(lines)
