"""The user's scheduled daily authorization; old manual approvals stay separate."""
import json
import os
from pathlib import Path

POLICY_PATH=Path(__file__).resolve().parents[1]/'research/daily-automatic-policy.json'


def execution_authority(*, automatic=False):
    if (os.environ.get('GITHUB_RUN_ATTEMPT')!='1'
            or not os.environ.get('GITHUB_REPOSITORY_OWNER')
            or os.environ.get('GITHUB_ACTOR')!=os.environ['GITHUB_REPOSITORY_OWNER']):
        raise ValueError('daily_owner_first_attempt_required')
    if not automatic:
        if os.environ.get('GITHUB_REF')!='refs/heads/deploy/phase2h-request-preparation':
            raise ValueError('daily_manual_deploy_required')
        return dict(mode='manual',human_review_required=True)
    policy=json.loads(POLICY_PATH.read_bytes())
    if (policy['max_model_POSTs_per_session']!=1 or policy['retry'] is not False
            or policy['fallback'] is not False or policy['auto_email'] is not True):
        raise ValueError('automatic_one_call_mail_policy_invalid')
    repository=os.environ.get('GITHUB_REPOSITORY','')
    branch='refs/heads/'+policy['default_branch']
    expected=repository+'/'+policy['workflow_path']+'@'+branch
    if (not repository.startswith(os.environ['GITHUB_REPOSITORY_OWNER']+'/')
            or os.environ.get('GITHUB_REF')!=branch
            or os.environ.get('GITHUB_WORKFLOW_REF')!=expected):
        raise ValueError('automatic_default_branch_workflow_required')
    event_path=Path(os.environ.get('GITHUB_EVENT_PATH',''))
    event=json.loads(event_path.read_bytes()) if event_path.is_file() else {}
    kind=os.environ.get('GITHUB_EVENT_NAME')
    if not (
        kind=='schedule' and event.get('schedule')==policy['cron_UTC']
        or kind=='workflow_dispatch' and
        (event.get('inputs') or {}).get('operation')==policy['manual_paid_operation']
    ):
        raise ValueError('automatic_schedule_or_explicit_paid_operation_required')
    return dict(mode='automatic',policy_id=policy['id'],human_review_required=False,
                authorization_basis=policy['user_instruction'],
                scheduled_local_time=policy['local_start_time'],timezone=policy['timezone'],
                max_model_POSTs=policy['max_model_POSTs_per_session'],
                reservation_CNY=policy['reservation_CNY'])


def require_mail_configuration():
    """Also called before the model POST, so incomplete mail setup cannot incur it."""
    values={key:os.environ.get(key,'').strip()
            for key in ('EMAIL_SENDER','EMAIL_PASSWORD','EMAIL_RECEIVERS')}
    missing=[key for key,value in values.items() if not value]
    if missing:
        raise ValueError('email_Secrets_missing_before_POST:'+','.join(missing))
    sender=values['EMAIL_SENDER']
    receivers=[value.strip() for value in values['EMAIL_RECEIVERS'].split(',') if value.strip()]
    if (not receivers or '@' not in sender or any(c in sender for c in '\r\n')
            or any('@' not in value or any(c in value for c in '\r\n') for value in receivers)):
        raise ValueError('explicit_email_addresses_required_before_POST')
    return values,receivers
