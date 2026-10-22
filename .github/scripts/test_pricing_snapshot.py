from pathlib import Path
import hashlib
import pytest
from authorized_once import pricing_text_sha,verify_pricing_snapshot
from deepseek_post_guard import GuardStop
RAW=(Path(__file__).resolve().parents[1]/'frozen/mvp-three-v3/OFFICIAL_PRICING.html').read_bytes()
SHA=hashlib.sha256(RAW).hexdigest()
TEXT=pricing_text_sha(RAW)

def test_exact_snapshot():
    assert verify_pricing_snapshot(RAW,SHA)['peak']['output']=='1.20'

def test_build_asset_change_with_trusted_baseline():
    changed=RAW.replace(b'runtime~main.',b'runtime~newbuild.')
    assert changed!=RAW
    assert verify_pricing_snapshot(changed,SHA,TEXT)

def test_legacy_no_baseline_rejects_build_change():
    with pytest.raises(GuardStop,match='pricing_snapshot_changed'):
        verify_pricing_snapshot(RAW+b'<!-- build -->',SHA)

@pytest.mark.parametrize('old,new',[(b'$0.003',b'$0.004'),(b'DeepSeek-V4.1-Flash',b'DeepSeek-Other'),(b'</body>',b'Changed billing terms</body>')])
def test_any_tariff_model_or_text_change_rejected(old,new):
    changed=RAW.replace(old,new)
    assert changed!=RAW
    with pytest.raises(GuardStop):verify_pricing_snapshot(changed,SHA,TEXT)

def test_untrusted_text_baseline_rejected():
    with pytest.raises(GuardStop):verify_pricing_snapshot(RAW+b'<!-- build -->',SHA,'invalid')
