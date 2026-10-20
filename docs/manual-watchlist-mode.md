# Manual watchlist: one mode per batch

The independent profile `manual_watchlist_mode_v1` uses business commit
`577624ad8459871630c690e5760ae504ac6f2b9f`. It does not change `mvp_manual_v2`
(business `68b85e7`) or the historical six-request comparison. Existing consumed
requests and approvals must never be reused. Each new batch needs its own
reviewed material, hash, authorization and user Environment approval.

## Selected next test: GPT-6.1 Sol Responses draft

The user changed the next quality test target to `gpt-6.1-sol` on 2026-10-20.
The existing DeepSeek snapshots remain historical records. The new reviewed
configuration is `.github/research/gpt-6.1-sol-review-profile.json`: Responses
wire format, high reasoning effort, 32768 total output tokens, standard service
tier, one POST at most, no retries or fallback, and a proposed CNY 0.05
reservation that is not an authorization.

`manual_responses_candidate.py` preserves the saved native messages as Responses
`input`. It removes the old vendor `thinking`, `max_tokens`, `temperature` and
`stream_options` fields, using `reasoning.effort` and `max_output_tokens` instead.
The output is a draft, with no sender, batch authorization or model call.
It retains source timestamps/expiry and verifies the source request/context
hashes. Expired source data is refused rather than refreshed.

The user's screenshot supersedes the rounded direct quote. Per category, the
draft uses the Sol-family reference: screenshot gateway CNY rate multiplied by
the target official USD rate and divided by the reference official USD rate.
For input, cached input and output respectively, 5.6 Sol's screenshot rates are
0.9996/0.09996/1.2495 CNY against official 4/0.4/20 USD. The official 6.1 Sol
standard rates are 2/0.10/10 USD. The resulting estimated CNY/1M rates are
0.4998/0.02499/0.62475, not a confirmed target gateway quote.

The Astra card gives a different scenario: 0.4004/0.02002/2.002 CNY for the same
target. These differences must remain visible: the shared 0.0357 badge does not
establish a common category tariff. If either scenario exceeds the proposed
reservation, the draft records the shortfall and blocks live use. Do not claim
a cache-write tariff from screenshots that do not contain it. No multiplier or
exchange rate is applied again.

Total output includes reasoning, which is not charged twice. The byte allowance
is not a tokenizer measurement or provider spending cap. A profile hash records
pricing separately from the request-body hash.

`RESEARCH_API_BASE` must identify the provider's upstream public HTTPS base.
The current desktop Q-Pilot localhost proxy is not a GitHub Runner endpoint.
The user-created live credential is named `SEEKERX` as a repository Secret;
draft preparation neither reads it nor uploads a local desktop credential.
Until the upstream connection is configured and a new exact batch is reviewed,
this profile cannot be dispatched for a live test. Existing Environment and
deploy-branch protections still apply.

### Reviewed single Responses test

The user selected the Sol-derived tariff for the next paid approval. The
`sol_aapl_paid` job in the registered 04 manual workflow selects only batch
`3e23087e93c3ad203e1d2ef7ced882261b9c45872fc34d8a37740a4b79ee5223`,
with `execute_live=true`, `mvp_three=true`, `comparison_modes=false` and
`mvp_universe=single_mode_watchlist`. Its material is
`.github/frozen/sol-aapl-20261020`. The legacy watchlist job explicitly excludes
this hash, preventing the consumed DeepSeek bundle from being selected.

This job retains `environment: nvda-one-call-approval`, repository-owner checks,
the existing deploy branch restriction, and a first-attempt-only requirement.
Only after human approval does `manual_responses_once.py` read `SEEKERX`.
It verifies the lock and each request/context/profile hash, endpoint, selected
Sol tariff, reservation, source commit, source expiry and latest complete market
session. The existing create-only protected remote claims reserve both the new
batch and request; reservations are never reused or released after ambiguity.

The sender makes one direct Responses POST using zero transport retries and
no redirects/fallback. Raw response bytes are retained with credential redaction.
Only a `response.completed` event with completed status supplies successful text;
failed, incomplete, missing or duplicate terminal events stop without retry.
Usage is saved as returned; cached input is a subset of total input, and
reasoning is not added to output a second time. Unknown usage stays unknown.
The CNY cost estimate uses the user-selected external tariff, not a supplier bill
or an enforceable spending cap.

The native JSON extractor and existing full-field/program-facts writer produce
unpublished previews; no integrity-repair generation, mail or notification is
invoked. Failure artifacts remain inspectable. A separate credential scan must
pass before artifact upload. This is a one-off test, not a global analyzer
provider migration or an automated research schedule.

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

### One AAPL hosted free preparation

The registered `04-nvda-free-preflight.yml` has a separate free selector:
`request_sha256=AAPL_NEW_FREE_PREP_20261020`, with `execute_live=false`,
`mvp_three=false`, and `comparison_modes=false`, on the existing
`review/phase2t-hosted-preflight` branch only. It requires repository-owner
dispatch. This selector is not a request hash or paid authorization.

The job has read-only contents permission, no model Secret and no Environment.
It captures only AAPL through the existing native free capture and fake model
transport, using the saved `aapl-independent-20261020.json` comparison packet.
After a successful fresh capture it downloads the official pricing page once,
uses the existing fail-closed pricing check, and freezes one nonthinking
candidate with `authorize_paid_POST=false`. It checks the actual frozen AAPL
messages for neutral vendor-income labels and preserved independent evidence.
Capture/pricing/check failures preserve artifacts and stop without a paid call.
Pricing uses the existing canonical `authorized_once.PRICING` URL, including
its trailing slash. `GuardStop` failures are recorded and re-raised; they never
leave a successful or authorized preparation status. A downloaded successful
capture may be prepared locally while still fresh, without repeating capture.

The candidate is an artifact for review, not a runnable paid authorization or an
Environment approval request. Existing deploy entry points and historical
bundles remain unchanged. A new live batch still needs its exact hash, current
expiry, scoped authorization and the user's own Environment approval.


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

Each finding has `discovery_origin` (`automatic_narrow_rule` or
`operator_supplied_review`) and an `evidence_status`: `CONFIRMED_CONTRADICTION`,
`REVIEW_CANDIDATE`, `SOURCE_BLOCKER`, or `INTERPRETATION_LIMITATION`. Unknown
categories default to review candidates, never confirmed errors. Status counts
count field-level records, not independent errors or a research quality score.
An unusual financial ratio remains a candidate, not proof of a false number.
No status changes `published=false` or `quality_accepted=false`.

The normal rendering entry `save_full_report(..., additional_findings=reviews)`
accepts operator-reviewed field-path/original-content/evidence/recommendation
records and passes them only to the sidecar. This is an in-process review hook,
not model-generated evidence, a POST authorization, or an automatic financial
source verifier. The operator must supply verified review records; nothing is
silently read from a model output, external file, or environment variable.
The historical accepted sidecar baseline is not regenerated for this metadata change.

Battle-plan review also checks position-strategy references, generic dependencies
on empty `risk_plan` scenarios, and defensive-condition reference paths. Decision
label differences remain review candidates because existing holdings and new-entry
advice can legitimately have different scopes. Watch/hold alone is not a conflict.
No natural-language trigger is treated as programmatically confirmed; buy plans
remain conditional and unpublished. These rules do not evaluate arbitrary trigger
language, invent scenarios, rewrite model labels, or regenerate accepted sidecars.

### Independent financial comparison evidence

The existing `--research-data FILE` accepts a per-symbol `financial_evidence`
object separately from the legacy `values` replacement and
`dividend_announcements`. This comparison does not replace Yahoo fields,
dates, parent/earnings statuses, errors, source chains, dividends or news.
It is appended by the controller around the pinned native formatter in both
Chinese and English and preserved as `independent_financial_evidence` in
`PROGRAM_FACTS.json`. No pinned business-source change or model call is implied.

The object contains `sources` keyed by source ID and `fields` keyed by
`revenue`, `net_income`, or `operating_cash_flow`. Each source requires an HTTPS
`url`, lowercase SHA256, aware `fetched_at`, `published_date`, `period_end`,
`page_count`, `duration_months`, `fiscal_year`, `currency`, and `unit`.
Each `direct_quarter` field contains its `kind`, numeric finite `value`,
`statement_label`, `source_id`, one-based `page`, `period_end`, `currency`,
and `unit`; the selected source duration must be three months.
One PDF may supply multiple source IDs for different table durations.

A `derived_from_ytd_difference` CFO contains its value/basis/period and exactly
two `operands` with the same row metadata. The first cumulative duration minus
the second must be three months, the fiscal year and currency/unit must match,
and the periods must increase. The value must equal the first operand minus
the second. Period ordering compares parsed calendar dates, including mixed
ISO extended/basic representations, rather than strings. Invalid dimensions or arithmetic stop preparation. This is
structural validation, not a general financial parser or source authenticator;
row transcription, source hashes and accounting comparability still require
operator review. Optional `vendor_period_key` and `notes` preserve comparison
context without rewriting the original vendor period.

`Net income` is separate from the original `net_profit_parent` field; amount
agreement does not certify parent attribution. The paid packet qualifier labels
the vendor income row accordingly. Financial comparison evidence is not recent
news and does not validate ROE, dividends, valuation, guidance or report quality.
`FINANCIAL_EVIDENCE_USED.json` records what was supplied. Missing evidence leaves
the existing behavior unchanged; legacy `values` replacement retains its
existing semantics.

### Saved news evidence (free preparation only)

The existing `mvp_three.py` preparation CLI accepts optional `--news-data FILE`.
The UTF-8 JSON maps symbols to lists of saved evidence. Each item requires
`source`, HTTPS `url`, `title`, timezone-aware `published_at` and `fetched_at`,
and `content_kind` (`metadata_only` or `full_text`). Only saved full text may
include `text`; its optional `content_sha256` is checked against UTF-8 text bytes,
not the original HTTP body. Publication must fall within three days of the new
preparation cutoff; collection must follow publication and not exceed cutoff.
Invalid items are excluded with reasons in `SAVED_NEWS_AUDIT.json`.
Missing symbol keys are explicitly audited as `ticker_entry_missing`, distinct
from an intentional empty list. Per-symbol and batch status retain `not_configured`
without a packet; provided packets report `saved_evidence_attached_not_searched`
or `saved_evidence_empty_or_rejected_not_searched`. These describe this saved
packet, not comprehensive search coverage or the absence of event risk.

The adapter supplies native context-pack and analyzer news slots, without fetching,
changing financial fields or claiming a SearchService search. Existing supplied
release text is retained separately, not counted as recent news. It can coexist
with `--research-data`, whose financial replacement remains explicit. Missing news
keeps unknown search-result counts and event risk. No environment variable, search
provider or production workflow is enabled. Omit the flag for the unchanged path.
Never apply this entry to historical consumed output directories or reuse their
approval; any future model batch still needs fresh material and authorization.

For one synthetic CLI wiring probe, combine `--offline-data DIR`, `--only NVDA`,
`--news-data FILE` and `--offline-prompt-only`. This mode requires local fixtures,
formats the native prompt and parses a clearly synthetic model fixture solely to
render a simulated report. It never calls native model dispatch or transport and
does not write `FINAL_REQUEST.json` or a request identity. The status is
`success_offline_prompt_probe`, not a real analysis success. Do not pass these
outputs to paid preparation; they cannot meet the fresh-source capture contract.

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
The controller checkout's Yahoo adapter bounds dividend TTM events to both ends
of the trailing window, excluding future ex-dates from historical cash sums and
yield. The supplied event list remains unchanged; this does not add official
announced-future-event ingestion, prove payment execution, or modify the pinned
`577624a` business checkout used by the manual controller. That pinned runtime
does not inherit this source fix until an explicitly reviewed source transition.

No Chinese counterpart existed for this new topic; local delivery notes explain
the same entry in Chinese. The upstream bilingual README is unchanged.

### Supplied future dividend announcements

The controller's existing `--research-data FILE` accepts a per-symbol object
containing `dividend_announcements` independently of the existing financial
release fields. An announcement-only object does not replace financial data,
historical `dividend.events`, TTM cash, event counts or yield. Each announcement
requires `source`, HTTPS `source_url` without credentials, `announcement_date`,
aware `fetched_at`, `ex_dividend_date`, positive finite
`cash_dividend_per_share`, and a three-uppercase-letter `currency`.
`record_date` and `payable_date` are optional calendar dates.
Accepting a dividend announcement does not upgrade the existing earnings or
parent fundamental status. Its acceptance is expressed only by the separate
announcement audit; a missing financial report remains missing and existing
financial errors and source chains are preserved.

Calendar fields must use `YYYY-MM-DD`. Their comparison calendar is explicitly
UTC; timestamps keep their supplied offset. Collection must not be after the
cutoff, announcement date must not be after the UTC collection date, and ex-date
must be strictly after the UTC cutoff date. Same-day ex-dates are not confirmed
future events. Date-only publication evidence does not prove an exact first
publication time. A payable date is planned payment, not proof of execution.

Materials are loaded once and attached before the native pack-building call;
analyze consumes those same prepared artifacts. The controller wraps the native
formatter to append a separate source-limited announcement section, compatible
with the unchanged pinned `577624a` formatter. This is a controller integration,
not a modification or upgrade of that pinned business checkout. The native pack
continues its existing coverage/status summary; it does not claim to summarize
the individual announcement details.

`DIVIDEND_ANNOUNCEMENT_AUDIT.json` and future `PROGRAM_FACTS.json` preserve
accepted entries and indexed rejection reasons. Missing material is unknown;
an explicit empty list or all-rejected input is not evidence of no announcements.
Structural/cutoff validation does not authenticate the source or prove payment,
after-tax receipts, ADR conversion or a comprehensive company-action search.
This path does not add news hits, refresh old batches, fetch sources or authorize
model dispatch. No legacy report or model narrative is rewritten.
