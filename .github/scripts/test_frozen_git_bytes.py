"""Exercise Git normalization and archive bytes, rather than only the worktree."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

from manual_responses_once import load_bundle

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = Path('.github/frozen/sol-aapl-news-20261020')
BATCH = 'f1f3e8dbc009e1eb0798bb397147c511cf5f8904f6ef64d7acb365bd26e908c4'


@pytest.mark.parametrize('autocrlf', ['true', 'false'])
def test_git_archive_preserves_reviewed_bundle_bytes(tmp_path, autocrlf):
    repository = tmp_path / 'repository'
    repository.mkdir()
    shutil.copyfile(ROOT / '.gitattributes', repository / '.gitattributes')
    shutil.copytree(ROOT / BUNDLE, repository / BUNDLE)

    def git(*args):
        return subprocess.check_output(['git', '-C', str(repository), *args],
                                       stderr=subprocess.PIPE)

    git('init', '-q')
    git('config', 'core.autocrlf', autocrlf)
    git('add', '.')
    for original in (repository / BUNDLE).iterdir():
        name = (BUNDLE / original.name).as_posix()
        assert git('show', ':' + name) == original.read_bytes(), name
    tree = git('write-tree').decode().strip()
    # The producer may run on Windows; the consumer is the Linux Actions runner.
    git('config', 'core.autocrlf', 'false')
    archive = git('archive', '--format=tar', tree)
    exported = tmp_path / 'exported'
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        # Read only the expected regular bundle files; do not extract arbitrary paths.
        for original in (repository / BUNDLE).iterdir():
            name = BUNDLE / original.name
            member = stream.getmember(name.as_posix())
            assert member.isfile()
            target = exported / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(stream.extractfile(member).read())
            assert target.read_bytes() == original.read_bytes(), name
    lock, _, _, _ = load_bundle(exported / BUNDLE, BATCH)
    news = (exported / BUNDLE / 'NEWS_PACKET.json').read_bytes()
    assert hashlib.sha256(news).hexdigest() == lock['news_packet_sha256']
    assert len(json.loads(news)['AAPL']) == 2
