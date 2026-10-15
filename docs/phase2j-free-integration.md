# Phase 2J: free hosted integration acceptance

This review branch includes the reviewed Phase 2I patch without additional
analysis-business changes. Four business files change relative to the accepted
Phase 2G/2H baseline: native analyzer, pipeline, technical-result row-count
metadata and Yahoo fundamental class-share spelling. The existing native JSON,
LiteLLM client, renderer, price prefill and BRK.B quote patch remain.

The branch-specific `.github/workflows/01-free-market-validation.yml` is a
dedicated Phase 2J definition using the already registered free manual workflow
path. This allows dispatching the review branch without registering a new file
on `main`. It has only `workflow_dispatch`, no live input, no schedule, matrix,
environment secret or paid-provider credential. Only the selected free workflow
is temporarily enabled; other workflows remain disabled. Repository Actions is
disabled again after collecting the run evidence.

The workflow installs the original dependencies, prepares a hash-verified public
tokenizer, runs the related native/controller offline tests, downloads immutable
historical artifacts, and replays Phase 2E/2H model responses. Original responses
are SHA-checked and remain unchanged; corrected RSS metadata is explicitly a
program addition, not new model text or a successful new research generation.

Live data uses only the existing Yahoo adapter and native `days=90` price API.
The independent free-only process guard blocks Python outbound sockets, HTTPX,
requests, urllib and SMTP, allowing only HTTPS Yahoo GETs through curl_cffi.
The collector retains its timeout, 403/429 circuit, Retry-After evidence,
request trace and fresh-data validation. No old quote database substitutes for
new observations. The review tool classifies quarterly aggregates, TTM/unknown
fallbacks, inferred net income, ETF gaps and identity limitations; it does not
turn Yahoo data into official statements.

The existing paid controller's historical code pin is deliberately not updated.
Its native dispatch/parse/render helpers and one-POST guard are covered with
mocked transports on this branch. Real execution against this new business
version remains blocked until a later approved pin update, fresh capture/hash,
cost authorization and human environment approval. No current paid authority
exists in this phase.

Monthly cost projections must use current official prices and observed usage,
not the earlier one-stock/day plan. Original usage logs are not a cross-runner
monthly hard cap. No custom budget database or old research framework is added.
Production scheduling and 35-stock paid analysis remain unapproved.
