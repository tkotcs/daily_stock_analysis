"""Only the new free hosted path; never dispatch Actions or contact sources."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from prepare_aapl_candidate import check_comparison

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('live,owner,branch,selected', [
    (False, True, 'review/phase2t-hosted-preflight', True),
    (True, True, 'review/phase2t-hosted-preflight', False),
    (False, False, 'review/phase2t-hosted-preflight', False),
    (False, True, 'main', False),
    (False, True, 'deploy/phase2h-request-preparation', False),
])
def test_free_selector_is_exact_and_has_no_secret_or_environment(live, owner, branch, selected):
    workflow = yaml.load((ROOT / '.github/workflows/04-nvda-free-preflight.yml').read_text('utf-8'),
                         Loader=yaml.BaseLoader)
    job = workflow['jobs']['aapl_free_prepare']
    inputs = SimpleNamespace(execute_live=live, mvp_three=False, comparison_modes=False,
                             request_sha256='AAPL_NEW_FREE_PREP_20261020')
    github = SimpleNamespace(actor='owner' if owner else 'other', repository_owner='owner',
                             ref='refs/heads/' + branch)
    expression = job['if'].removeprefix('${{').removesuffix('}}').strip().replace('&&', 'and').replace('!inputs.', 'not inputs.')
    assert bool(eval(expression, {'__builtins__': {}}, dict(inputs=inputs, github=github))) == selected
    assert 'secrets.' not in str(job) and 'environment' not in job
    assert job['permissions'] == {'contents': 'read'}
    assert all('execute-authorized' not in step.get('run', '') for step in job['steps'])
    capture = next(step['run'] for step in job['steps'] if step.get('name', '').startswith('Only AAPL'))
    assert '--only AAPL' in capture and '--research-data' in capture
    assert workflow['jobs']['single_mode_watchlist']['with']['bundle_path'].endswith('bf7c3b89')


def test_candidate_comparison_rejects_missing_or_ambiguous_actual_prompt():
    before = dict(financial_evidence={'source': 'SYNTHETIC'}, fundamental_context={'status': 'failed'}, today={'close': 100})
    context = copy.deepcopy(before)
    text = ('净利润（供应商字段，归母归属未独立核验） derived_from_ytd_difference direct_quarter '
            '116996 82627 2026-06-27 2026-03-28 不是近三日新闻')
    packet = dict(messages=[dict(content=text)])
    check_comparison(context, before, packet)
    packet['messages'][0]['content'] += '\n| 归母净利润 | 1 |'
    with pytest.raises(ValueError, match='ambiguous_vendor_income_label'):
        check_comparison(context, before, packet)
    packet['messages'][0]['content'] = text.replace('82627', '')
    with pytest.raises(ValueError, match='content_missing'):
        check_comparison(context, before, packet)
