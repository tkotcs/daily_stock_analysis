# Manual watchlist: one mode per batch

The independent profile `manual_watchlist_mode_v1` uses business commit
`577624ad8459871630c690e5760ae504ac6f2b9f`. It does not change `mvp_manual_v2`
(business `68b85e7`) or the historical six-request comparison. Existing consumed
requests and approvals must never be reused. Each new batch needs its own
reviewed material, hash, authorization and user Environment approval.

## Prepare, without a model call

Use the existing native free capture on the pinned business checkout when a new
batch is actually requested. Do not rerun it merely to repeat migration checks.
From the controller directory, using the local project interpreter:

```powershell
python .github/scripts/mvp_three.py --source ../dsa-mode-business-577 --out ../../work/new-capture --universe watchlist35
```

Optional reviewed issuer releases use the existing `--research-data` input.
Identity or source failures remain failures; do not silently substitute ADR or
ordinary-share data. ETF financial fields may be not applicable. A failed capture
is not eligible for a paid packet. Inspect the source/period/currency audit before
authorizing a batch. Missing news or historical paths remain unknown.

Save a current official pricing HTML snapshot separately, then prepare exactly
one selected mode from the fresh capture:

```powershell
python .github/scripts/watchlist_mode.py --source ../dsa-mode-business-577 --data ../../work/new-capture --pricing ../../work/current-official-pricing.html --out .github/frozen/manual-watchlist-new --mode thinking
```

`--mode nonthinking` is the default: thinking disabled, output limit 16384.
`--mode thinking` selects thinking enabled, reasoning effort high, output limit
32768. One packet per symbol, not two. The optional `--only NVDA,MU,QQQ` selects
an explicit ordered subset for a separately authorized batch. Never use old
`FROZEN_REQUESTS` or extend historical timestamps to prepare a new batch.

The preparer preserves native research messages and market context, including deterministic
price/MA roles, actual two-day crossing events, volume denominators, and financial
period/source/currency. Financial table rows receive field-specific period,
source, estimation and verification labels from the saved audit. TTM/unknown and
revenue-times-margin estimates are not labeled as quarterly reported figures.
Reviewed official packet values are distinguished from the original Yahoo audit;
without the original page independently revalidated in this batch they remain
explicitly unverified. ROE is not covered by the three financial amount fields.
The same provenance is saved in context and program-facts views. This changes
request/context hashes, never raw captures or their original expiry timestamps.
When financial and quote currencies differ and a nonzero quote-currency dividend
has no event-level evidence, financial amounts/ROE and dividend inputs are
quarantined as unavailable in both messages and context. No currency or receipt
ratio conversion is attempted. Raw provider evidence is retained outside the
model input. Technical facts remain usable; do not infer valuation or yield.
Apart from these labels, only mode parameters change. It checks the latest complete
session and the existing 24-hour/next-session-close expiry rule; no live request is
sent. It refuses to overwrite an output directory. New locks start with
`authorize_paid_POST=false`. Synthetic test bundles have `offline_only=true` and
cannot be authorized live.

## Execute only after new batch approval

The new workflow is `.github/workflows/05-manual-watchlist-mode.yml`.
Its triggers are manual `workflow_dispatch` and reuse through `workflow_call`;
`execute_live` defaults to false. The
default job runs only the new offline tests without model secrets.

When this new filename is not registered on the default branch, the already
registered `04-nvda-free-preflight.yml` dispatches it on the approved deploy ref.
Select `mvp_three=true`, `comparison_modes=false`, and
`mvp_universe=single_mode_watchlist`. This deployment entry selects nonthinking
and the separately reviewed `manual-watchlist-approved-bf7c3b89` bundle; it does
not select the old watchlist or consumed six-request comparison. The existing
`request_sha256` input passes the exact new batch hash. Both workflow defaults
remain free, and live work still waits for the same user Environment approval.
The caller and callee use distinct concurrency groups to avoid self-deadlock.
No change to main/default branch or to the historical profiles is needed.

For a separately approved real batch, publish the reviewed controller and new
bundle to the existing approved deploy branch. Select `mode`, `bundle_path`, the
exact `BATCH_SHA256.txt` value, and an explicit authorization reference containing
that hash. Set `execute_live=true` only for that authorized batch. The selected
mode must match the hashed lock; changing the UI mode cannot change packets.
Also supply `secret_upload_approval_reference`: a traceable message or record of
the user's existing authorization to store/use the repository Secret, never its
value. This input is required only for live execution; an empty reference stops
before the executor. A reference is an audit pointer, not proof or a new grant of
permission: verify the actual human record before dispatch. It does not replace
the separate hash-scoped paid-batch authorization or the Environment approval.
The existing `nvda-one-call-approval` Environment requires the user's own approval.
Repository/workflow enabling and publishing are separate steps not performed by
this development change. A local key does not bypass the protected GitHub entry.

For 35 symbols the request cap is 35, one per symbol. Existing reservation checks
use USD 0.03 per nonthinking request / 0.06 per thinking request, totaling USD 1.05
or 2.10 respectively. These are conservative **authorization reservations**, not
expected bills or provider-enforced spending limits. Oversized inputs are refused
when their existing byte allowance estimate exceeds the reservation. Actual costs
come from saved supplier usage and verified pricing; future prices/lengths may
differ. No fallback, automatic retry, Gmail or cron is enabled.

## Read downloaded artifacts

Open the root `index.html` in the downloaded artifact directory. Relative links
work locally without a server. Each symbol has:

- `STATUS.json`: execution outcome, request identity, attempts, review state,
  usage, cost estimate and available artifact paths; failures retain their own row.
- `REPORT.md` / `REPORT.html`: original DSA selected report, containing program
  facts and model sections, labeled as such.
- `MODEL_ALL_FIELDS.md` / `.html`: every parsed model field with no truncation or
  narrative correction; HTML escapes untrusted content.
- `MODEL_RAW_TEXT.txt`: original reconstructed model content; `MODEL_COMPLETE.html`
  displays the complete parsed JSON. `MODEL_REASONING_TEXT.txt` holds any returned
  reasoning separately. Neither is a publication approval.
- `PROGRAM_FACTS.json` / `.html`: the pinned native deterministic quote facts and
  supplied financial context/source metadata, explicitly separate from model text.
- `RESPONSE_RESULT.json` and raw SSE bytes: supplier usage, stop/truncation result,
  latency and existing cost estimates, retained even if parsing fails.

`BATCH_RESULT.json` adds `usage_summary`. Output tokens already include reasoning;
reasoning is never charged twice. Missing reasoning metadata is counted, not
invented as a reported zero. Missing responses/usage after attempted transport
make the full cost estimate unknown; the known subtotal remains separately
available. Both peak and off-peak estimates are labeled, not presented as bills.
Simulation usage is explicitly `synthetic_test_only`, with zero actual paid POSTs.

The executor keeps all original raw evidence and marks all reports unpublished.
A watch-only plan remains valid; risk-plan errors remain visible in per-symbol
checks and require human review. No new broad quality scoring or prompt framework
is introduced. Native input facts do not guarantee that a model follows them.

## Narrow verification and rollback

### Independent review sidecars

New reports include `QUALITY_REVIEW.md` / `.html` and `QA_FINDINGS.json`, linked
from the batch index and full-field view. These are separate from the unchanged
model narrative and do not grant publication approval. Narrow deterministic
checks compare explicit MA ordering with native values, flag target-day lows
called previous lows, detect undefined scenario references, and label buy actions
as conditional plans without a trusted trigger evaluation. A historical support
reference requires evidence; a review flag does not prove no earlier support exists.

Historical artifacts must not be rewritten. Call `save_quality_review` into a new
review directory with the original parsed model and frozen context; explicit
human-reviewed findings may be appended with their exact field paths and evidence.
Financial period mapping or plausibility findings isolate financial conclusions,
not valid technical facts. An unusual profit margin alone is not proof of error.
Missing source headers remain unresolved, not silently repaired or called verified.
Daily OHLCV cannot prove intraday paths or whether selling pressure is exhausted.
These checks are deliberately limited: no findings does not mean research acceptance.

```powershell
python -m pytest .github/scripts/test_manual_quality.py -q
```

This test target is offline and does not rerun historical analysis or model calls.
Removing the sidecar helper and its report/index links rolls back this display-only
review layer. Keep all original response bytes and remote consumed records.

```powershell
python -m pytest .github/scripts/test_watchlist_mode.py -q
```

Set `DSA_FIXED_SOURCE` to the pinned `577624a` checkout and both tokenizer cache
variables to the prepared local cache before testing. Tests use fresh synthetic
fixtures, an external-network-denied worker, two three-symbol mode runs with one
injected failure, long output, usage totals, and 35-symbol packet metadata.
They do not execute the old 35-symbol pipeline or regenerate consumed requests.

Rollback removes the new workflow/profile helpers and reverts the executor and
session changes together; keep historical artifacts and all remote consumed refs.
No Chinese counterpart existed for this new topic; local delivery notes explain
the same entry in Chinese. The upstream bilingual README is unchanged.
