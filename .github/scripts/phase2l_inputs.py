"""Small deterministic input correction for the independent NVDA preparation entry."""
import copy


def correct_inputs(packet, context):
    packet, context = copy.deepcopy(packet), copy.deepcopy(context)
    today, yesterday = context['today'], context['yesterday']
    bullish = all(isinstance(today.get(k), (int, float)) for k in ('ma5','ma10','ma20')) and today['ma5'] > today['ma10'] > today['ma20']
    reasons = context.get('trend_analysis', {}).get('signal_reasons', [])
    removed = [r for r in reasons if not bullish and ('多头排列' in r or '持续上涨' in r)]
    context.setdefault('trend_analysis', {})['signal_reasons'] = [r for r in reasons if r not in removed]
    for message in packet['messages']:
        if message['role'] != 'user': continue
        for reason in removed:
            message['content'] = message['content'].replace(reason, '均线未形成MA5>MA10>MA20多头排列；不得据此声称持续上涨')
        ratio = today['volume'] / yesterday['volume'] if yesterday.get('volume') else None
        message['content'] += ('\n\n独立准备入口的口径澄清（不改变任何行情或必需JSON字段）：\n'
            f"当日成交量/前一交易日成交量={ratio:.4f}，约{ratio:.1f}倍；这不是均量量比。"
            f"原版volume_ratio={today.get('volume_ratio')}，仍按原版近5个历史交易日成交均量基准展示，不能以昨日倍数覆盖该字段。\n"
            '每组策略分别写明入场E、止损S、适用触发条件和(E-S)/E×100%的名义损失；不得把某组的止损或损失百分比套到另一组。未指定入场或止损时不声称损失上限。\n'
            '均线位置不等于新发生穿越；未来新下穿必须从先前位于上方开始。保持USD报价、官方财务期间与Yahoo口径区别、RSS仅标题且综合搜索未执行的限制。\n'
            '保留所有必需字段。同一事实无需在多个长段落完整复述，可简洁引用前述数值；策略价是条件性方案，不是已证实历史支撑。')
    return packet, context, {'removed_contradictory_reasons':removed, 'bullish_alignment':bullish,
        'previous_day_volume_multiple':ratio, 'original_volume_ratio':today.get('volume_ratio'),
        'source_prices_unchanged':today==context['today']}
