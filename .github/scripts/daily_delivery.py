"""Select a validated report or a deterministic failure notice; one shared mail claim."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import os

from daily_briefing import read, save, sha, source_check, trading_day_gate
from daily_execution_policy import execution_authority, require_mail_configuration


def optional(path):
    return read(path) if path.is_file() else {}


def notice_content(root, source):
    """No model text, stale market facts, arbitrary errors or private data in notices."""
    source_check(source)
    current = trading_day_gate(datetime.now(timezone.utc))
    calendar = read(root/'calendar.json')
    session_state = read(root/'SESSION_STATUS.json')
    session = calendar['completed_session']
    if (current.get('run') is not True or current['completed_session'] != session
            or calendar.get('run') is not True or session_state.get('run') is not True
            or session_state.get('session') != session):
        raise ValueError('current_unclaimed_trading_session_required')
    generated = optional(root/'daily-real/STATUS.json')
    if generated.get('status') == 'generated_daily_automatic_validated':
        raise ValueError('validated_report_must_use_normal_delivery')
    reason = generated.get('reason')
    message = ('模型供应商返回服务过载，本日未取得可发布正文。'
               if reason == 'upstream_overloaded_no_retry' else
               '模型生成或报告质量检查未通过，本日不发布未经验证的正文。'
               if generated else
               '行情采集或资料准备未通过，本日没有足够的已核验资料生成完整研报。')
    return (
        '# 美股日报运行通知\n\n'
        '> 本邮件是故障通知，不是完整研报，不包含投资建议。\n\n'
        '目标美国交易日：' + session + '。\n\n' + message + '\n\n'
        '今天的完整研报暂不可用；没有使用旧行情、模拟数据或未通过检查的模型内容替代。\n\n'
        '本通知不追加模型请求。后续正常交易日继续按北京时间09:00启动；'
        '本通知与正式研报共用每日邮件记录，避免重复发送。\n'
    ), session


def deliver_daily(root, source, out):
    from daily_briefing_mail import deliver
    authority = execution_authority(automatic=True)
    policy = read(Path(__file__).resolve().parents[1]/'research/daily-automatic-policy.json')
    if policy.get('degraded_service_notice') is not True:
        raise ValueError('daily_notice_authorization_required')
    require_mail_configuration()
    # Never convert an ambiguous SMTP result into a second delivery.
    if out.exists():
        raise ValueError('mail_state_exists_no_retry')
    generated = optional(root/'daily-real/STATUS.json')
    if generated.get('status') == 'generated_daily_automatic_validated':
        report = root/'daily-real/DAILY_REPORT.md'
        return deliver(report, source, out, sha(report.read_bytes()), send=True, automatic=True)
    content, session = notice_content(root, source)
    folder = root/'daily-notice'
    folder.mkdir(exist_ok=False)
    report = folder/'DAILY_REPORT.md'
    report.write_bytes(content.encode('utf-8'))
    digest = sha(report.read_bytes())
    save(folder/'STATUS.json', dict(status='daily_service_notice',
                                   program_validation_passed=True, report_sha256=digest))
    save(folder/'AUTHORIZATION_USED.json', dict(
        execution_authority=authority, run_id=os.environ['GITHUB_RUN_ID'],
        focus_symbol='DAILY_NOTICE', target_session=session))
    return deliver(report, source, out, digest, send=True, automatic=True, notice_root=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = deliver_daily(args.root, args.source, args.out)
    print(json.dumps(result))
    if result['status'] != 'delivered':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
