"""Local clock backup for GitHub scheduling; dispatch only, never call a model/mail."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo


def target_session(now):
    """Only the morning after a completed US session, including Friday -> Saturday."""
    import exchange_calendars
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    if local.weekday() not in range(1, 6) or not 9 <= local.hour < 15:
        return None
    session = (local.date() - timedelta(days=1)).isoformat()
    calendar = exchange_calendars.get_calendar("XNYS")
    if not calendar.is_session(session):
        return None
    if calendar.session_close(session).to_pydatetime() >= now:
        return None
    return session


def gh_json(gh, arguments, *, missing_ok=False):
    result = subprocess.run([gh, *arguments], capture_output=True, timeout=60)
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise RuntimeError("github_response_unreadable_no_dispatch") from None
    if result.returncode:
        if missing_ok and isinstance(value, dict) and str(value.get("status")) == "404":
            return None
        raise RuntimeError("github_read_failed_no_dispatch")
    return value


def inspect(session, now, repository, workflow, gh):
    for kind, prefix in (("model", "DSA:consolidated-daily:v1:"),
                         ("mail", "DSA:daily-mail:v1:")):
        digest = hashlib.sha256((prefix + session).encode()).hexdigest()
        ref = "refs/tags/dsa-mvp-consumed-v1/batch/" + digest
        claim = gh_json(gh, ["api", f"repos/{repository}/git/ref/{ref[5:]}"],
                        missing_ok=True)
        if claim is not None:
            if not isinstance(claim, dict) or claim.get("ref") != ref:
                raise RuntimeError("github_claim_invalid_no_dispatch")
            return kind + "_reserved_no_retry"
    runs = gh_json(gh, ["run", "list", "--repo", repository, "--workflow", workflow,
                       "--limit", "30", "--json", "status,createdAt,databaseId"])
    if not isinstance(runs, list):
        raise RuntimeError("github_runs_invalid_no_dispatch")
    start = now.astimezone(ZoneInfo("Asia/Shanghai")).replace(
        hour=9, minute=0, second=0, microsecond=0)
    for run in runs:
        created = datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))
        if run["status"] != "completed" or created >= start:
            # Failed/unknown runs need diagnosis, not automatic paid retries.
            return "existing_run_no_retry"
    return "dispatch_needed"


def dispatch_receipt(dispatched):
    """Persist protocol facts, never raw CLI output or provider-controlled text."""
    output = dispatched.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    matches = re.findall(r"^HTTP/\S+ (\d{3})(?: .*)?$", output, re.MULTILINE)
    status = int(matches[0]) if len(matches) == 1 else None
    receipt = dict(status="dispatch_uncertain_no_retry", HTTP_status=status,
                   failure_code="dispatch_response_uncertain")
    if dispatched.returncode == 0 and status == 204:
        return dict(status="production_dispatched", HTTP_status=204)
    try:
        body = json.loads(output.split("\n\n", 1)[1])
    except (IndexError, ValueError):
        return receipt
    if (dispatched.returncode and status in {400, 401, 403, 404, 422, 429}
            and isinstance(body, dict) and str(body.get("status")) == str(status)):
        code = "github_dispatch_rejected"
        if status == 422 and body.get("message") == "Actions has been disabled for this repository.":
            code = "actions_disabled_for_repository"
        return dict(status="dispatch_rejected", HTTP_status=status, failure_code=code)
    return receipt


def dispatch_slot(args, session, now):
    """Keep every reservation; only a proven HTTP rejection permits one later retry."""
    first_failure = None
    for attempt in (1, 2):
        suffix = "" if attempt == 1 else "-2"
        marker = args.state_dir / (session + ".dispatch-attempt" + suffix + ".json")
        receipt_path = args.state_dir / (session + ".dispatch-result" + suffix + ".json")
        if not marker.exists():
            return marker, receipt_path, attempt, None
        if not receipt_path.exists():
            return None, None, attempt, dict(
                status="local_dispatch_already_reserved_no_retry", attempt=attempt)
        reservation = json.loads(marker.read_bytes())
        receipt = json.loads(receipt_path.read_bytes())
        if (receipt.get("session") != session or reservation.get("session") != session
                or receipt.get("checked_at") != reservation.get("checked_at")):
            raise ValueError("dispatch_receipt_reservation_mismatch")
        first_failure = dict(status="local_dispatch_already_reserved_no_retry",
                             previous_dispatch=receipt, attempt=attempt)
        if receipt.get("status") != "dispatch_rejected":
            return None, None, attempt, first_failure
        elapsed = now - datetime.fromisoformat(receipt["checked_at"])
        if elapsed < timedelta(minutes=20):
            return None, None, attempt, dict(first_failure, status="dispatch_rejected_wait")
    return None, None, 2, dict(first_failure, status="dispatch_rejected_retry_limit")


def execute(args, now):
    session = target_session(now)
    result = dict(checked_at=now.isoformat(), session=session, model_POSTs=0,
                  SMTP_attempts=0, dry_run=args.dry_run)
    if session is None:
        return dict(result, status="outside_delivery_window_or_holiday")
    marker, receipt_path, attempt, stopped = dispatch_slot(args, session, now)
    if stopped:
        return dict(result, **stopped)
    status = inspect(session, now, args.repository, args.workflow, args.gh)
    if status != "dispatch_needed" or args.dry_run:
        return dict(result, status=status)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    # Reserve before dispatch: a timeout may still have created a remote run.
    with marker.open("x", encoding="utf-8") as stream:
        json.dump(dict(result, status="dispatch_reserved_may_be_sent"), stream)
    dispatched = subprocess.run(
        [args.gh, "api", "--include", "--method", "POST",
         f"repos/{args.repository}/actions/workflows/{args.workflow}/dispatches",
         "--input", "-"],
        input=json.dumps(dict(ref="main", inputs=dict(operation="run_paid_daily"))).encode(),
        capture_output=True, timeout=60)
    receipt = dict(result, **dispatch_receipt(dispatched), attempt=attempt)
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--gh", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    try:
        result = execute(args, now)
    except Exception as error:
        result = dict(checked_at=now.isoformat(), status="stopped_no_retry",
                      reason=type(error).__name__ + ":" + str(error),
                      model_POSTs=0, SMTP_attempts=0)
        args.state_dir.mkdir(parents=True, exist_ok=True)
        (args.state_dir / "latest.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        raise
    args.state_dir.mkdir(parents=True, exist_ok=True)
    (args.state_dir / "latest.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    if result["status"] in {"dispatch_rejected", "dispatch_uncertain_no_retry",
                            "dispatch_rejected_wait", "dispatch_rejected_retry_limit"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
