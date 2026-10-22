"""Rebound hashes must not hide a stale session or missing date table."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

from manual_responses_candidate import canonical
from manual_responses_once import load_bundle, main

ROOT = Path(__file__).resolve().parents[2]
BATCH = 'f1f3e8dbc009e1eb0798bb397147c511cf5f8904f6ef64d7acb365bd26e908c4'
FOLDER = ROOT / '.github/frozen/sol-aapl-news-20261020'


@pytest.mark.parametrize('mutation', ['context_date', 'bar_date', 'lock_date',
                                      'symbol', 'table_date', 'missing_table'])
def test_rebound_semantic_mismatch_blocks_sender_before_claim_or_POST(tmp_path, monkeypatch, mutation):
    bundle = tmp_path / 'bundle'
    shutil.copytree(FOLDER, bundle)
    lock, context, request = [json.loads((bundle / name).read_bytes()) for name in
                              ('RESPONSES_LOCK.json', 'CONTEXT.json', 'REQUEST.json')]
    if mutation == 'context_date':
        context['date'] = '2026-10-16'
    elif mutation == 'bar_date':
        context['today']['date'] = '2026-10-16'
    elif mutation == 'lock_date':
        lock['target_session'] = '2026-10-16'
    elif mutation == 'symbol':
        context['code'] = 'MSFT'
    else:
        user = next(m for m in request['input'] if m['role'] == 'user')
        if mutation == 'table_date':
            user['content'] = user['content'].replace('| 2026-10-19 |', '| 2026-10-18 |')
        else:
            user['content'] = user['content'].split('\n\n### Session date references')[0]
    # File hashes and lock digest are valid: this tests semantic binding, not corruption.
    for name, field, value in [('CONTEXT.json', 'context_sha256', context),
                                ('REQUEST.json', 'request_sha256', request)]:
        raw = canonical(value)
        (bundle / name).write_bytes(raw)
        lock[field] = hashlib.sha256(raw).hexdigest()
    raw = canonical(lock)
    (bundle / 'RESPONSES_LOCK.json').write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    key = 'SYNTHETIC-not-a-real-key'
    for name, value in dict(SEEKERX=key, GITHUB_RUN_ATTEMPT='1',
                            GITHUB_REF='refs/heads/deploy/phase2h-request-preparation',
                            GITHUB_ACTOR='owner', GITHUB_REPOSITORY_OWNER='owner',
                            APPROVAL_REF='synthetic approval ' + digest).items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    import subprocess
    import httpx
    import remote_execution_claim
    def forbidden(*args, **kwargs):
        pytest.fail('semantic mismatch must stop before source lookup, claim, or transport')
    monkeypatch.setattr(subprocess, 'check_output', forbidden)
    monkeypatch.setattr(httpx, 'Client', forbidden)
    monkeypatch.setattr(remote_execution_claim, 'RemoteExecutionClaim', forbidden)
    out = tmp_path / 'out'
    monkeypatch.setattr(sys, 'argv', ['sender', '--bundle', str(bundle), '--source', str(tmp_path),
                                    '--out', str(out), '--batch-sha', digest])
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 1
    status = json.loads((out / 'STATUS.json').read_bytes())
    assert status['actual_model_POST_attempts'] == 0 and status['status'] == 'blocked_before_POST'
    assert status['error_category'] == 'ValueError'
    assert 'session' in status['reason']
    assert not (out / 'REMOTE_CLAIM.json').exists() and not (out / 'POST_ATTEMPT.json').exists()


def test_correct_bundle_passes_strict_binding_and_legacy_is_read_only():
    lock, request, context, _ = load_bundle(FOLDER, BATCH, require_session_table=True)
    assert context['date'] == context['today']['date'] == lock['target_session']
    legacy = ROOT / '.github/frozen/sol-aapl-20261020'
    old_digest = hashlib.sha256((legacy / 'RESPONSES_LOCK.json').read_bytes()).hexdigest()
    load_bundle(legacy, old_digest)
    with pytest.raises(ValueError, match='session_reference_table_missing'):
        load_bundle(legacy, old_digest, require_session_table=True)
