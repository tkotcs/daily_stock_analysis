"""Read the permanent session claim before capture; never release or retry it."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from deepseek_post_guard import GuardStop
from remote_execution_claim import GitHubAPI


def check_session(session, api):
    from datetime import date
    if date.fromisoformat(session).isoformat() != session:
        raise ValueError('invalid_session_date')
    for prefix in ('DSA:consolidated-daily:v1:', 'DSA:daily-mail:v1:'):
        digest = hashlib.sha256((prefix + session).encode()).hexdigest()
        ref = 'tags/dsa-mvp-consumed-v1/batch/' + digest
        try:
            existing = api('GET', 'ref/' + ref)
        except GuardStop as error:
            if str(error) != 'remote_claim_HTTP_404_no_retry':
                raise
            continue
        if existing.get('ref') != 'refs/' + ref:
            raise ValueError('session_claim_response_invalid')
        return dict(run=False, status='session_reserved_may_be_consumed_no_retry',
                    session=session)
    return dict(run=True, status='session_unclaimed', session=session)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    state = dict(run=True, status='free_preparation', session=args.session)
    try:
        if os.environ.get('AUTOMATIC_RUN') == 'true':
            from daily_execution_policy import execution_authority
            execution_authority(automatic=True)
            state = check_session(args.session, GitHubAPI(
                os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN']))
    except (Exception, GuardStop):
        state.update(run=False, status='session_check_failed_no_POST')
        raise
    finally:
        args.out.write_text(json.dumps(state, indent=2), encoding='utf-8')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('run=' + str(state['run']).lower() + '\n')


if __name__ == '__main__':
    main()
