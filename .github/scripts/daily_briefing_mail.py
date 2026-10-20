"""Deliver one reviewed consolidated report through the existing native email sender."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from daily_briefing import read, save, sha, source_check


def deliver(report, source, out, review_reference, *, send=False,automatic=False):
    out.mkdir(parents=True, exist_ok=False)
    result = dict(status='mail_preview_only', mail_attempts=0, automatic_retry=False,
                  model_POSTs=0, recipients_or_credentials_exported=False)
    try:
        content = report.read_bytes()
        digest = sha(content)
        result['report_sha256'] = digest
        status = read(report.parent / 'STATUS.json')
        expected_status='generated_daily_automatic_validated' if automatic else 'generated_daily_preview_requires_review'
        if status.get('status') != expected_status:
            raise ValueError('successful_generated_daily_report_required')
        authorization = read(report.parent / 'AUTHORIZATION_USED.json')
        if not send:
            return result
        if digest not in review_reference:
            raise ValueError('exact_report_hash_review_required_before_mail')
        if automatic and review_reference!=digest:
            raise ValueError('exact_automatic_report_hash_required')
        from daily_execution_policy import execution_authority
        authority=execution_authority(automatic=automatic)
        if automatic:
            from manual_responses_once import check_time
            if (authorization.get('execution_authority')!=authority
                    or authorization.get('run_id')!=os.environ.get('GITHUB_RUN_ID')
                    or status.get('program_validation_passed') is not True
                    or status.get('report_sha256')!=digest):
                raise ValueError('automatic_current_run_validated_report_required')
            lock=read(report.parent/'DAILY_LOCK.json')
            if (lock.get('execution_policy_id')!=authority['policy_id']
                    or sha((report.parent/'DAILY_LOCK.json').read_bytes())!=authorization['batch_sha256']):
                raise ValueError('automatic_mail_lock_binding_required')
            check_time(lock)
        result['execution_authority']=authority
        sender, password, receivers = [os.environ.get(key, '').strip()
                                        for key in ('EMAIL_SENDER', 'EMAIL_PASSWORD', 'EMAIL_RECEIVERS')]
        if not sender or not password or not receivers:
            raise ValueError('email_Secrets_missing_no_mail')
        receiver_list = [value.strip() for value in receivers.split(',') if value.strip()]
        if (not receiver_list or '@' not in sender or any(c in sender for c in '\r\n')
                or any('@' not in value or any(c in value for c in '\r\n') for value in receiver_list)):
            raise ValueError('explicit_email_addresses_required_no_self_fallback')
        source_check(source)
        from remote_execution_claim import GitHubAPI, RemoteExecutionClaim
        focus = authorization['focus_symbol']
        session = authorization['target_session']
        claim = RemoteExecutionClaim(
            GitHubAPI(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN']),
            sha(('DSA:daily-mail:v1:' + session).encode()), os.environ['GITHUB_RUN_ID'],
            os.environ['GITHUB_SHA'], symbols=(focus,))
        save(out / 'MAIL_CLAIM.json', claim.reserve([dict(symbol=focus, request_sha256=digest)]))
        claim.before_send(focus, digest)
        # Saved before SMTP: an ambiguous delivery is never automatically repeated.
        save(out / 'MAIL_ATTEMPT.json', dict(state='reserved_may_be_delivered_no_retry',
                                           report_sha256=digest))
        result['mail_attempts'] = 1
        from src.notification_sender.email_sender import EmailSender
        config = SimpleNamespace(email_sender=sender, email_password=password,
                                 email_receivers=receiver_list,
                                 email_sender_name='美股科技投资与技术观察日报', stock_email_groups=[])
        delivered = EmailSender(config).send_to_email(
            content.decode('utf-8'), subject='美股科技投资与技术观察日报｜' + session,
            timeout_seconds=45)
        result['status'] = 'delivered' if delivered else 'mail_failed_or_unknown_no_retry'
    except BaseException as error:
        result.update(status='mail_failed_or_unknown_no_retry' if result['mail_attempts'] else 'blocked_before_mail',
                      reason=str(error) if type(error) is ValueError else type(error).__name__)
    finally:
        save(out / 'MAIL_STATUS.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'source', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--review-reference','--report-sha256', default='')
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--automatic',action='store_true')
    args = parser.parse_args()
    result = deliver(args.report, args.source, args.out, args.review_reference, send=args.send,
                     automatic=args.automatic)
    print(json.dumps(result))
    if result['status'] not in ('mail_preview_only', 'delivered'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
