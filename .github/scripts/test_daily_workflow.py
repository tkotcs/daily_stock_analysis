import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / '.github/workflows/06-daily-consolidated.yml.disabled'


def workflow():
    return yaml.load(PATH.read_text('utf-8'), Loader=yaml.BaseLoader)


@pytest.mark.parametrize('operation,ready,selected', [
    ('prepare', 'false', ['prepare']),
    ('generate', 'false', ['prepare']),
    ('generate', 'true', ['prepare', 'generate']),
    ('email', 'false', ['email']),
])
def test_only_requested_daily_stage_can_run(operation, ready, selected):
    spec = workflow()
    inputs = SimpleNamespace(operation=operation)
    github = SimpleNamespace(actor='owner', repository_owner='owner',
                             ref='refs/heads/deploy/phase2h-request-preparation')
    needs = SimpleNamespace(prepare=SimpleNamespace(outputs=SimpleNamespace(ready=ready)))
    enabled = []
    for name, job in spec['jobs'].items():
        expression = job['if'].removeprefix('${{').removesuffix('}}').strip().replace('&&', 'and')
        if eval(expression, {'__builtins__': {}}, dict(inputs=inputs, github=github, needs=needs)):
            enabled.append(name)
    assert enabled == selected


def test_disabled_template_has_no_invented_cron_and_keeps_secrets_out_of_scan():
    spec = workflow()
    assert 'schedule' not in spec['on']
    assert spec['on']['workflow_dispatch']['inputs']['operation']['default'] == 'prepare'
    assert 'secrets.' not in json.dumps(spec['jobs']['prepare'])
    assert 'daily_news.py' in json.dumps(spec['jobs']['prepare'])
    for name in ('generate', 'email'):
        assert spec['jobs'][name]['environment'] == 'nvda-one-call-approval'
    generation_commands = [step['run'] for step in spec['jobs']['generate']['steps'] if step.get('run')]
    assert sum('daily_briefing.py generate' in command for command in generation_commands) == 1
    email_commands = [step['run'] for step in spec['jobs']['email']['steps'] if step.get('run')]
    assert sum('daily_briefing_mail.py' in command for command in email_commands) == 1
    assert spec['concurrency']['cancel-in-progress'] == 'false'


def test_official_feed_configuration_is_limited_and_preserves_missing_coverage():
    feeds = json.loads((ROOT / '.github/research/daily-news-feeds.json').read_bytes())
    assert feeds['max_GETs_per_feed'] == 1 and feeds['max_items_per_symbol'] == 3
    assert [f['symbol'] for f in feeds['feeds']] == ['NVDA', 'MSFT', 'AAPL']
