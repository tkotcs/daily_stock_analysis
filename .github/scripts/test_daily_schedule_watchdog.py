from datetime import datetime, timezone
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
