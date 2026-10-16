# Reviewed 16384 one-call controller (preparation only)

This review changes no analyzer, prompt, parser, trade calculator or notification
business code from `a1daaa302b3a72fb5694c9872ceecf2c4dc0b6e4`.

`authorized_once.LiveSession` now recognizes exactly one additional profile:
request SHA `08b09a31d1d08c4b1fa33bc92f850feb63709ace5c6f8fd43a63aa9bee82cdee`,
business commit `a1daaa302b3a72fb5694c9872ceecf2c4dc0b6e4`, target session
2026-10-15, analysis cutoff 2026-10-16T06:04:29.560325+00:00, max_tokens 16384,
disabled thinking and material deadline 2026-10-16T20:00:00+00:00. The existing
8192 legacy profile is unchanged. An arbitrary new hash cannot select the 16K
profile. Full canonical HTTP body equality is checked at the transport boundary.

The new profile also requires the new full SHA in its separately supplied
authorization reference; old Phase2P references do not qualify. Nothing in this
branch is a paid authorization. Frozen request/lock bytes were copied unchanged
into `.github/frozen/phase2r`. Derived CAPTURE_SUMMARY only bridges existing file
names; it is not a regenerated request. No key or Authorization header is stored.

Authorization expiry cannot extend material expiry. Latest completed XNYS session,
actual UTC time and conservative off-peak windows are checked before free account
GETs and again immediately before the atomic POST marker. Weekday UTC01–04 and
06–10 are blocked even on Chinese public holidays (safe, potentially over-strict).
Failure to prove calendar availability stops the call. No system date is changed;
test clocks are local offline fixtures and cannot be selected by the executable.

The frozen dispatcher sets LiteLLM `num_retries=0`; this control is not part of
the HTTP body. HTTPX transport retries remain zero, redirects remain forbidden,
sync/async share the existing single-attempt guard, and no Router/fallback or
recovery helper is used. Timeout or unknown result stops; no retry or rerun.
The guard itself is unchanged. Reservations are estimates, not supplier caps or
cross-Runner monthly budget enforcement. Costs now use the selected profile's
16384 output ceiling, not the legacy 8192 number.

For this profile, original JSON parsing and native integrity checks are followed
by the existing pure risk-plan calculator. Missing/invalid/null risk_plan means
quality NO-GO: retain raw HTTP/text/usage/parsed JSON and diagnostics, but skip
Markdown generation and send nothing. A valid plan is only eligible for a local
review report; full factual review is still required and `published=false`.
This is a small controller gate, not a new research/validation platform.

Run only related tests, using fake credentials and simulated HTTP transports:

```powershell
python -m pytest .github/scripts/test_phase2s_once.py .github/scripts/test_authorized_once.py .github/scripts/test_nvda_frozen_once.py -q
```

Synthetic SSE usage must never be counted as actual supplier consumption. Do not
rerun the unaffected 348-test research suite for these controller-only changes.
The prepared manual workflow requires execute_live=false by default, a separate
new hash/fee authorization, the existing owner's Environment approval and exact
commit/material checks. No push, dispatch, approval or paid execution is part of
this preparation. Chinese delivery documents accompany this English code note.
