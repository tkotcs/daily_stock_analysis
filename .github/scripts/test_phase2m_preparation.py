"""Free configuration boundaries; never loads a provider or uses credentials."""
import subprocess,sys
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[2]

def test_non_thinking_live_flag_is_rejected_before_source_or_output_access(tmp_path):
    destination=tmp_path/'must-not-exist'
    result=subprocess.run([sys.executable,str(ROOT/'.github/scripts/nvda_free_preflight.py'),
        '--source',str(tmp_path/'no-source'),'--out',str(destination),'--include-free-research',
        '--non-thinking','--execute-authorized'],capture_output=True,text=True)
    assert result.returncode==2
    assert 'non-thinking preparation is free-only' in result.stderr
    assert not destination.exists()

def test_non_thinking_configuration_has_one_official_deployment_and_no_key_value():
    config=yaml.safe_load((ROOT/'.github/phase2l-deepseek.yaml').read_text('utf-8'))
    assert len(config['model_list'])==1
    params=config['model_list'][0]['litellm_params']
    assert params=={'model':'deepseek/deepseek-flash','api_base':'https://api.deepseek.com',
        'api_key':'os.environ/DEEPSEEK_API_KEY','extra_body':{'thinking':{'type':'disabled'}}}
