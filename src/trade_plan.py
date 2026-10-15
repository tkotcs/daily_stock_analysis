"""Arithmetic for explicit, hypothetical LONG plans; never infer prices from prose.

This is a report calculation, not price validation or an order/execution engine.
The original model narrative remains unchanged. Invalid plans fail closed.
"""
import math


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
        if cap > 100:
            raise ValueError('position_over_100')
    except ValueError as exc:
        return [], None, [str(exc)]
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
    rows, cap, errors = calculate_risk_plan(plan)
    if errors:
        return ('Risk plan unverified; do not use model arithmetic/position prose. ' if english else
                '风险计划未核验，不采用模型算术或仓位文案：') + ', '.join(errors)
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = [f'Python-calculated hypothetical long plan; shared position cap {cap:g}%.' if english else
             f'Python确定性计算的假设做多情景；统一仓位上限{cap:g}%。',
             '| Entry | Stop | Target | Loss % | Reward/risk | Position % | Trigger | Invalidation |' if english else
             '| 入场 | 止损 | 目标 | 名义损失% | 收益风险比 | 仓位% | 触发 | 失效 |',
             '|---|---|---|---|---|---|---|---|']
    for row in rows:
        target = f"{row['target']:g}" if row['target'] is not None else 'N/A'
        rr = f"{row['reward_risk']:.3f}" if row['reward_risk'] is not None else 'N/A'
        lines.append(f"| {row['entry']:g} | {row['stop']:g} | {target} | {row['loss_pct']:.3f} | {rr} | {row['position_pct']:g} | {cell(row['trigger'])} | {cell(row['invalidation'])} |")
    lines.append('Assumptions, not verified target forecasts; excludes fees, gaps and slippage.' if english else
                 '情景参数来自模型假设，不是已证实的目标价；未计费用、跳空和滑点，不保证实际损失。')
    return '\n'.join(lines)
