from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest

import daily_schedule_watchdog as watchdog


NOW = datetime(2026, 10, 22, 1, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("stamp,expected", [
    (NOW, "2026-10-21"),
    (datetime(2026, 10, 24, 1, tzinfo=timezone.utc), "2026-10-23"),
    (datetime(2026, 10, 26, 1, tzinfo=timezone.utc), None),
    (datetime(2026, 12, 26, 1, tzinfo=timezone.utc), None),
    (datetime(2026, 10, 22, 0, 59, tzinfo=timezone.utc), None),
    (datetime(2026, 10, 22, 7, tzinfo=timezone.utc), None),
])
def test_delivery_window_and_calendar(stamp, expected):
    assert watchdog.target_session(stamp) == expected


def test_only_explicit_404_allows_missing():
    with patch.object(watchdog.subprocess, "run") as run:
        run.return_value = SimpleNamespace(returncode=1, stdout=b'{"status":"404"}')
        assert watchdog.gh_json("gh", [], missing_ok=True) is None
        for body in [b'{"status":"403"}', b"timeout", b"{}"]:
            run.return_value.stdout = body
            with pytest.raises(RuntimeError):
                watchdog.gh_json("gh", [], missing_ok=True)


def test_existing_run_including_failure_stops():
    with patch.object(watchdog, "gh_json", side_effect=[
        None, None, [dict(status="completed", createdAt=NOW.isoformat())]
    ]):
        assert watchdog.inspect("2026-10-21", NOW, "o/r", "w", "gh") == "existing_run_no_retry"


def test_reservation_survives_ambiguous_dispatch(tmp_path):
    args = SimpleNamespace(state_dir=tmp_path, dry_run=False,
                           repository="o/r", workflow="w", gh="gh")
    with patch.object(watchdog, "inspect", return_value="dispatch_needed"), \
            patch.object(watchdog.subprocess, "run", side_effect=TimeoutError):
        with pytest.raises(TimeoutError):
            watchdog.execute(args, NOW)
        assert watchdog.execute(args, NOW)["status"] == "local_dispatch_already_reserved_no_retry"


def test_dry_run_cannot_dispatch(tmp_path):
    args = SimpleNamespace(state_dir=tmp_path, dry_run=True,
                           repository="o/r", workflow="w", gh="gh")
    with patch.object(watchdog, "inspect", return_value="dispatch_needed"), \
            patch.object(watchdog.subprocess, "run") as run:
        assert watchdog.execute(args, NOW)["status"] == "dispatch_needed"
        run.assert_not_called()
        assert not list(tmp_path.iterdir())


def test_model_claim_stops_before_runs():
    import hashlib
    digest = hashlib.sha256(b"DSA:consolidated-daily:v1:2026-10-21").hexdigest()
    with patch.object(watchdog, "gh_json", return_value={
        "ref": "refs/tags/dsa-mvp-consumed-v1/batch/" + digest
    }) as read:
        assert watchdog.inspect("2026-10-21", NOW, "o/r", "w", "gh") == "model_reserved_no_retry"
        assert read.call_count == 1


def response(status=422, message="Actions has been disabled for this repository.",
             returncode=1):
    payload = json.dumps(dict(status=str(status), message=message))
    return SimpleNamespace(returncode=returncode, stdout=(
        f"HTTP/2.0 {status} Response\r\nX-Github-Request-Id: example\r\n\r\n"
        + payload).encode(), stderr=b"must not be persisted")


def test_disabled_actions_is_a_redacted_definitive_rejection():
    receipt = watchdog.dispatch_receipt(response())
    assert receipt == dict(status="dispatch_rejected", HTTP_status=422,
                           failure_code="actions_disabled_for_repository")
    assert "must not" not in json.dumps(receipt)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429])
def test_known_client_rejections_are_distinguished_from_uncertain_dispatch(status):
    assert watchdog.dispatch_receipt(response(status))["status"] == "dispatch_rejected"


@pytest.mark.parametrize("result", [
    SimpleNamespace(returncode=1, stdout=b"", stderr=b"HTTP 422"),
    SimpleNamespace(returncode=1, stdout=b"HTTP/2.0 422 Error\n\n{}", stderr=b""),
    response(500),
    response(502),
    response(200, returncode=0),
    response(422, returncode=0),
])
def test_ambiguous_or_server_failure_cannot_authorize_retry(result):
    assert watchdog.dispatch_receipt(result)["status"] == "dispatch_uncertain_no_retry"


def test_no_content_is_success():
    result = SimpleNamespace(returncode=0, stdout=b"HTTP/2.0 204 No Content\n\n")
    assert watchdog.dispatch_receipt(result) == dict(
        status="production_dispatched", HTTP_status=204)


def test_rejected_attempt_rechecks_remote_and_retries_once_without_deleting(tmp_path):
    args = SimpleNamespace(state_dir=tmp_path, dry_run=False,
                           repository="o/r", workflow="w", gh="gh")
    with patch.object(watchdog, "inspect", return_value="dispatch_needed") as inspect, \
            patch.object(watchdog.subprocess, "run", return_value=response()) as run:
        first = watchdog.execute(args, NOW)
        marker = tmp_path / "2026-10-21.dispatch-attempt.json"
        original = marker.read_bytes()
        assert first["failure_code"] == "actions_disabled_for_repository"
        assert watchdog.execute(args, NOW + timedelta(minutes=19))["status"] == "dispatch_rejected_wait"
        assert run.call_count == inspect.call_count == 1
        second = watchdog.execute(args, NOW + timedelta(minutes=20))
        assert second["attempt"] == 2
        assert run.call_count == inspect.call_count == 2
        assert watchdog.execute(args, NOW + timedelta(minutes=40))["status"] == "dispatch_rejected_retry_limit"
        assert run.call_count == 2
        assert marker.read_bytes() == original
        assert len(list(tmp_path.iterdir())) == 4
        command = run.call_args.args[0]
        assert command[1:5] == ["api", "--include", "--method", "POST"]
        assert json.loads(run.call_args.kwargs["input"])["inputs"] == {"operation": "run_paid_daily"}


@pytest.mark.parametrize("remote_status", [
    "model_reserved_no_retry", "mail_reserved_no_retry", "existing_run_no_retry",
])
def test_rejected_retry_is_still_blocked_by_remote_claim_or_run(tmp_path, remote_status):
    args = SimpleNamespace(state_dir=tmp_path, dry_run=False,
                           repository="o/r", workflow="w", gh="gh")
    with patch.object(watchdog, "inspect", side_effect=["dispatch_needed", remote_status]), \
            patch.object(watchdog.subprocess, "run", return_value=response()) as run:
        watchdog.execute(args, NOW)
        assert watchdog.execute(args, NOW + timedelta(minutes=20))["status"] == remote_status
        assert run.call_count == 1


def test_success_and_unknown_result_never_retry(tmp_path):
    for dispatched in [response(204, returncode=0), response(500)]:
        state = tmp_path / str(dispatched.returncode)
        args = SimpleNamespace(state_dir=state, dry_run=False,
                               repository="o/r", workflow="w", gh="gh")
        with patch.object(watchdog, "inspect", return_value="dispatch_needed"), \
                patch.object(watchdog.subprocess, "run", return_value=dispatched) as run:
            watchdog.execute(args, NOW)
            result = watchdog.execute(args, NOW + timedelta(minutes=20))
            assert result["status"] == "local_dispatch_already_reserved_no_retry"
            assert result["previous_dispatch"]["HTTP_status"] in {204, 500}
            assert run.call_count == 1


def test_dry_run_cannot_create_a_second_reservation(tmp_path):
    args = SimpleNamespace(state_dir=tmp_path, dry_run=False,
                           repository="o/r", workflow="w", gh="gh")
    with patch.object(watchdog, "inspect", return_value="dispatch_needed"), \
            patch.object(watchdog.subprocess, "run", return_value=response()) as run:
        watchdog.execute(args, NOW)
        args.dry_run = True
        assert watchdog.execute(args, NOW + timedelta(minutes=20))["status"] == "dispatch_needed"
        assert run.call_count == 1
        assert len(list(tmp_path.iterdir())) == 2
