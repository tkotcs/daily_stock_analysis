"""Only the changed manual batch profile; fake GETs, no model transport."""
import copy,hashlib
import pytest
from test_phase2s_once import controlled,Clock,BODY,KEY
import authorized_once as ao
from deepseek_post_guard import GuardStop


@pytest.fixture
def batch(controlled):
    body=copy.deepcopy(BODY);body['messages'][1]['content']+=' OFFLINE MVP PROFILE TEST'
    sha=ao.canonical_sha(body)
    controlled.auth.update(test_profile='mvp_three_v1',symbol='NVDA',batch_sha256='b'*64,
        request_sha256=sha,authorization_reference='OFFLINE '+('b'*64)+' '+sha,
        material_expires_at=ao.REVIEWED_16K_DEADLINE,allow_peak_test=True)
    return controlled,body


def session(c):return ao.LiveSession(c.root,c.auth,KEY,c.auth['run_id'],c.get)


def test_batch_16k_accepted_with_fake_GETs(batch):
    c,body=batch;s=session(c);s.approve(body)
    assert s.max_tokens==16384 and len(c.calls)==3


@pytest.mark.parametrize('field,value',[
    ('symbol','AAPL'),('batch_sha256','invalid'),('request_sha256','invalid'),
    ('authorization_reference','old consumed approval'),('fixed_commit',ao.FIXED),
    ('material_expires_at','2026-10-16T20:01:00+00:00'),('analysis_asof','2026-10-17T06:00:00+00:00')])
def test_unapproved_profile_rejected_before_GET(batch,field,value):
    c,_=batch;c.auth[field]=value
    with pytest.raises(GuardStop):session(c)
    assert not c.calls


def test_body_mutation_rejected_before_GET(batch):
    c,body=batch;body['max_tokens']=8192
    with pytest.raises(GuardStop,match='request_hash_mismatch'):session(c).approve(body)
    assert not c.calls


def test_expired_material_rejected(batch):
    c,_=batch;s=session(c);Clock.current=Clock.current.replace(hour=20)
    with pytest.raises(GuardStop,match='EXPIRED'):s.check_material()
    assert not c.calls


def test_peak_requires_explicit_test_permission(batch):
    c,_=batch;Clock.current=Clock.current.replace(hour=7);c.auth['allow_peak_test']=False
    with pytest.raises(GuardStop,match='peak_window_no_POST'):session(c)
    c.auth['allow_peak_test']=True;assert session(c).max_tokens==16384
