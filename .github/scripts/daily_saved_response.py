"""Deliver one hash-pinned completed response after a QA bug fix; no model transport."""
import argparse
import json
import os
from pathlib import Path

from daily_briefing import (
    finish_report, load_live_bundle, read, save, sha, source_check,
)
from daily_execution_policy import execution_authority, require_mail_configuration
from manual_responses_once import completed_response

MANIFEST=Path(__file__).resolve().parents[1]/'research/daily-saved-response-recovery.json'


def verified_inputs(folder):
    manifest=read(MANIFEST)
    bundle=folder/'daily-ready'
    generated=folder/'daily-real'
    checks={
        bundle/'DAILY_LOCK.json':manifest['batch_sha256'],
        generated/'RAW_RESPONSE_BODY.bin':manifest['raw_response_sha256'],
        generated/'STATUS.json':manifest['source_status_sha256'],
        generated/'AUTHORIZATION_USED.json':manifest['source_authorization_sha256'],
    }
    for path,digest in checks.items():
        if sha(path.read_bytes())!=digest:
            raise ValueError('saved_response_pinned_evidence_changed')
    status=read(generated/'STATUS.json')
    auth=read(generated/'AUTHORIZATION_USED.json')
    if (status.get('HTTP_status')!=200 or status.get('actual_model_POST_attempts')!=1
            or status.get('reason')!='automatic_confirmed_quality_blocker_no_mail_no_retry'
            or status.get('run_id')!=manifest['source_run_id']
            or auth.get('run_id')!=manifest['source_run_id']
            or auth.get('batch_sha256')!=manifest['batch_sha256']
            or (folder/'mail-result/MAIL_ATTEMPT.json').exists()):
        raise ValueError('saved_response_not_eligible_no_POST')
    lock,request,context,profile,facts,contexts=load_live_bundle(bundle,manifest['batch_sha256'])
    response,text=completed_response((generated/'RAW_RESPONSE_BODY.bin').read_bytes())
    if response.get('model')!=request['model']:
        raise ValueError('saved_response_model_mismatch')
    return manifest,lock,context,facts,contexts,text,auth


def recover(folder,source,out):
    out.mkdir(parents=True,exist_ok=False)
    result=dict(status='saved_response_validation_failed',actual_model_POST_attempts=0,
                automatic_retry=False,fallback=False,run_id=os.environ.get('GITHUB_RUN_ID'))
    try:
        authority=execution_authority(automatic=True,saved_response=True)
        event=read(Path(os.environ['GITHUB_EVENT_PATH']))
        policy=read(Path(__file__).resolve().parents[1]/'research/daily-automatic-policy.json')
        if (os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
                or event.get('inputs',{}).get('operation')!=policy['saved_response_operation']):
            raise ValueError('saved_response_explicit_operation_required')
        require_mail_configuration()
        source_check(source)
        manifest,lock,context,facts,contexts,text,auth=verified_inputs(folder)
        if auth.get('execution_authority')!=authority:
            raise ValueError('saved_response_authority_changed')
        from remote_execution_claim import GitHubAPI
        api=GitHubAPI(os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_TOKEN'])
        ref=api('GET','ref/tags/dsa-mvp-consumed-v1/batch/'+auth['session_claim_sha256'])
        tag=api('GET','tags/'+ref['object']['sha'])
        owner=json.loads(tag['message'])
        if (owner.get('run_id')!=manifest['source_run_id']
                or owner.get('workflow_commit')!=manifest['source_workflow_commit']
                or tag['object']['sha']!=manifest['source_workflow_commit']):
            raise ValueError('saved_response_original_claim_owner_required')
        for name in ('DAILY_LOCK.json','DAILY_FACTS.json','FOCUS_CONTEXT.json','PROFILE.json'):
            (out/name).write_bytes((folder/'daily-real'/name).read_bytes())
        new_auth=dict(auth,run_id=os.environ['GITHUB_RUN_ID'],
                      recovered_from_run=manifest['source_run_id'],
                      original_response_sha256=manifest['raw_response_sha256'],
                      recovery_basis='unchanged_response_revalidated_after_QA_bug_fix_no_model_POST')
        save(out/'AUTHORIZATION_USED.json',new_auth)
        save(out/'SAVED_RESPONSE_PROVENANCE.json',manifest)
        result['source_run_model_POST_attempts']=1
        finish_report(out,lock,context,facts,contexts,text,result,
                      lambda name,value:save(out/name,value),automatic=True)
    except BaseException as error:
        result.update(reason=str(error) if type(error) is ValueError else type(error).__name__)
    finally:
        save(out/'STATUS.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('folder','source','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=recover(args.folder,args.source,args.out)
    print(json.dumps(result))
    if result['status']!='generated_daily_automatic_validated':
        raise SystemExit(1)


if __name__=='__main__':
    main()
