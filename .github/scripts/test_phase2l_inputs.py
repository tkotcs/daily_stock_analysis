import copy
from pathlib import Path
import json
import pytest
from phase2l_inputs import correct_inputs
from authorized_once import canonical_sha

FIXTURES=Path(__file__).resolve().parents[1]/'fixtures/phase2l'

def test_precise_input_repair_keeps_prices_and_schema():
    packet=json.loads((FIXTURES/'ORIGINAL_REQUEST_PACKET.json').read_text('utf-8'))
    context=json.loads((FIXTURES/'ORIGINAL_ENHANCED_CONTEXT.json').read_text('utf-8'))[0]
    originals=copy.deepcopy((packet,context))
    new,ctx,changes=correct_inputs(packet,context)
    assert (packet,context)==originals
    assert ctx['today']==context['today'] and ctx['yesterday']==context['yesterday']
    assert ctx['fundamental_context']==context['fundamental_context']
    assert changes['removed_contradictory_reasons']==['✓ 多头排列，持续上涨']
    assert '✓ 多头排列，持续上涨' not in new['messages'][1]['content']
    assert new['messages'][0]==packet['messages'][0]
    assert 'volume_ratio=1.33' in new['messages'][1]['content']
    assert '1.3952' in new['messages'][1]['content']
    assert '(E-S)/E' in new['messages'][1]['content']
    assert canonical_sha(new)!=canonical_sha(packet)

def test_actual_bullish_reason_not_deleted():
    packet={'messages':[{'role':'user','content':'多头排列，持续上涨'}]}
    ctx={'today':{'ma5':3,'ma10':2,'ma20':1,'volume':20},'yesterday':{'volume':10},'trend_analysis':{'signal_reasons':['多头排列，持续上涨']}}
    _,result,changes=correct_inputs(packet,ctx)
    assert result['trend_analysis']['signal_reasons']==ctx['trend_analysis']['signal_reasons']
    assert not changes['removed_contradictory_reasons']

@pytest.mark.parametrize('text',['突破待确认','RSI中性','volume_ratio口径未变'])
def test_unrelated_evidence_not_silently_removed(text):
    packet={'messages':[{'role':'user','content':text}]}
    ctx={'today':{'ma5':1,'ma10':2,'ma20':3,'volume':20},'yesterday':{'volume':10},'trend_analysis':{'signal_reasons':[text]}}
    new,result,_=correct_inputs(packet,ctx)
    assert result['trend_analysis']['signal_reasons']==[text]
    assert new['messages'][0]['content'].startswith(text)

def test_native_volume_ratio_uses_previous_five_days_not_previous_day():
    import pandas as pd
    from data_provider.yfinance_fetcher import YfinanceFetcher
    frame=pd.DataFrame({'close':[10]*10,'volume':[10,10,10,10,10,10,10,10,20,30]})
    result=YfinanceFetcher()._calculate_indicators(frame)
    assert result.iloc[-1]['volume_ratio']==round(30/12,2)
    assert result.iloc[-1]['volume_ratio']!=30/20

def test_disabled_thinking_can_pass_fake_only_guard_preflight(tmp_path):
    from authorized_once import LiveSession, FIXED
    from test_authorized_once import BODY, PRICE
    import datetime, hashlib
    body={**BODY,'thinking':{'type':'disabled'}}
    auth={'authorize_paid_post':True,'authorization_reference':'OFFLINE_ONLY','secret_upload_approval_reference':'OFFLINE_ONLY','run_id':'offline','fixed_commit':FIXED,'request_sha256':canonical_sha(body),'pricing_sha256':hashlib.sha256(PRICE).hexdigest(),'reservation_usd':'.03','expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=1)).isoformat()}
    def get(url,key=None):
        if url.endswith('/models'):return b'{"data":[{"id":"deepseek-flash"}]}'
        if url.endswith('/balance'):return b'{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"1"}]}'
        return PRICE
    session=LiveSession(tmp_path,auth,'fake-only-key','offline',get)
    session.approve(body)
    assert (tmp_path/'POST_ATTEMPT.json').exists()
