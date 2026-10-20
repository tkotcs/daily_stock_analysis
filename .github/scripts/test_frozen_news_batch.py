import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
import yaml

from manual_responses_once import load_bundle
from manual_responses_candidate import canonical

ROOT = Path(__file__).resolve().parents[2]
NEW = 'f1f3e8dbc009e1eb0798bb397147c511cf5f8904f6ef64d7acb365bd26e908c4'
OLD = '3e23087e93c3ad203e1d2ef7ced882261b9c45872fc34d8a37740a4b79ee5223'
FOLDER = ROOT / '.github/frozen/sol-aapl-news-20261020'


def test_real_news_batch_accepts_two_articles_without_claiming_two_sources():
    lock, request, context, profile = load_bundle(FOLDER, NEW)
    old, old_request, old_context, _ = load_bundle(ROOT / '.github/frozen/sol-aapl-20261020', OLD)
    assert lock['request_sha256'] != old['request_sha256']
    assert lock['analysis_asof'] == old['analysis_asof']
    assert lock['material_expires_at'] == old['material_expires_at']
    assert context['today'] == old_context['today']
    assert context['fundamental_context'] == old_context['fundamental_context']
    rows = context['saved_news_audit']['accepted']
    assert len(rows) == 2 and len({r['publisher'] for r in rows}) == 1
    assert {r['content_kind'] for r in rows} == {'summary'}
    text = '\n'.join(m['content'] for m in request['input'])
    assert '无法确认' in text and '传闻或预期' in text
    assert '本次未提供可用新闻证据' not in text and '不是新闻全文' in text
    assert '综合新闻搜索未执行' in text and '| 2026-10-19 |' in text
    assert profile['proposed_reservation_CNY'] == '0.05'


def test_hash_guard_rejects_a_changed_news_packet(tmp_path):
    target = tmp_path / 'bundle'
    shutil.copytree(FOLDER, target)
    with (target / 'NEWS_PACKET.json').open('ab') as handle:
        handle.write(b' ')
    with pytest.raises(ValueError, match='news_packet_hash_mismatch'):
        load_bundle(target, NEW)


def test_rebound_bad_summary_hash_cannot_pass_structural_preflight(tmp_path):
    target = tmp_path / 'bundle'
    shutil.copytree(FOLDER, target)
    packet = json.loads((target / 'NEWS_PACKET.json').read_text('utf-8'))
    context = json.loads((target / 'CONTEXT.json').read_text('utf-8'))
    lock = json.loads((target / 'RESPONSES_LOCK.json').read_text('utf-8'))
    packet['AAPL'][0]['content_sha256'] = '0' * 64
    context['saved_news_audit']['accepted'] = packet['AAPL']
    for name, value, field in [('NEWS_PACKET.json', packet, 'news_packet_sha256'),
                                ('CONTEXT.json', context, 'context_sha256')]:
        raw = canonical(value)
        (target / name).write_bytes(raw)
        lock[field] = hashlib.sha256(raw).hexdigest()
    raw = canonical(lock)
    (target / 'RESPONSES_LOCK.json').write_bytes(raw)
    with pytest.raises(ValueError, match='summary_hash_or_origin'):
        load_bundle(target, hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('digest', [NEW, OLD])
def test_each_Sol_hash_selects_its_own_bundle_and_skips_legacy(digest):
    workflow = yaml.load((ROOT / '.github/workflows/04-nvda-free-preflight.yml').read_text('utf-8'), Loader=yaml.BaseLoader)
    inputs = SimpleNamespace(execute_live=True, mvp_three=True, comparison_modes=False,
                             mvp_universe='single_mode_watchlist', request_sha256=digest)
    github = SimpleNamespace(actor='owner', repository_owner='owner',
                             ref='refs/heads/deploy/phase2h-request-preparation')
    selected = []
    for name, job in workflow['jobs'].items():
        expression = job['if'].removeprefix('${{').removesuffix('}}').strip().replace('&&', 'and').replace('||', 'or').replace('!inputs.', 'not inputs.')
        if eval(expression, {'__builtins__': {}}, dict(inputs=inputs, github=github)):
            selected.append(name)
    assert selected == ['sol_aapl_paid']
    job = workflow['jobs']['sol_aapl_paid']
    expression = job['env']['SOL_BUNDLE'].removeprefix('${{').removesuffix('}}').strip().replace('&&', 'and').replace('||', 'or')
    bundle = eval(expression, {'__builtins__': {}}, dict(inputs=inputs))
    assert bundle == ('.github/frozen/sol-aapl-news-20261020' if digest == NEW else '.github/frozen/sol-aapl-20261020')
    assert job['environment'] == 'nvda-one-call-approval'
