from pathlib import Path
import subprocess
import sys


def test_offline_probe_requires_local_fixture_before_start(tmp_path):
    script = Path(__file__).with_name('mvp_three.py')
    output = tmp_path / 'must_not_exist'
    result = subprocess.run([sys.executable, '-I', str(script), '--source', str(tmp_path), '--out', str(output), '--offline-prompt-only'], capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert '--offline-prompt-only requires --offline-data' in result.stderr
    assert not output.exists()
