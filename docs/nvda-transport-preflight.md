# Free NVDA transport preflight

Manual-only controller branch; a separate checkout pins original business source to 2b896241f69d0177c2b6f298cf69042b8531dd76. No API or mail secrets are injected. The native request uses a placeholder key and is stopped at HTTPX HTTPTransport/AsyncHTTPTransport before any model POST is sent.

The shared gate allows at most one POST attempt to the exact normal DeepSeek endpoint, denies retries at pool level, custom transport bypass and redirects. In free preflight it stops even the first attempt. Native stream and parameter-recovery tests use fake underlying transports; the second POST is denied. This is test instrumentation, not a research framework or monthly budget system.

Original DataFetcherManager days=90 and DatabaseManager save APIs provide fresh NVDA history to the same database used by original process_single_stock. No old evidence fallback is allowed. At least 60 rows and latest completed session are required. Technical MA60 read checks, full native request and raw request hash are recorded. Fundamentals and news are explicitly empty; interface readiness is not report quality validation.

No paid authorization, automatic schedule or email delivery is enabled. A real DEEPSEEK_API_KEY Secret requires separate user confirmation. Disable Actions again after collection. This deployment-specific English note has no existing translated counterpart.

## Phase 2C local preparation (not deployed)

The optional `--execute-authorized --authorization FILE --run-id ID` path is OFF by default. It requires separate Secret-upload and paid-call approval references, a pinned business commit, exact canonical request hash, target session, run ID, UTC expiry, current pricing HTML hash and a positive reservation not above USD 0.03. The authorization file is metadata, never a place for a key. Current templates deliberately deny execution. Model list, balance and pricing are read-only GET checks immediately before the guarded POST; a hash, fee or account discrepancy blocks sending.

The native LiteLLM client remains unchanged. A transport observer preserves response body bytes and extracts SSE text, finish reason, model, usage and latency. Sync/async errors, HTTP errors and partial streams stop with no paid retry. Unknown usage stays unknown; no cost is invented. The original captured stream request omits `stream_options.include_usage`, so supplier usage is not guaranteed. Enabling this optional field would change the material hash and needs a new free capture/review, not a silent request mutation.

Current new-code tests are local Windows fake-network tests, not another hosted acceptance run or a real API test. Local changes are supplied for review without committing/pushing or configuring a Secret. The previously deployed free workflow and all Actions remain disabled. Live-process logs redact the key, and no headers/exception messages are placed in metadata. The one-POST limit applies to one controller process and both transport paths; it is not a distributed monthly spending limit.

Native prompts include wall-clock market-phase text. For stable authorization hashes, the controller uses the existing `process_single_stock(current_time=...)` parameter with an explicit approved `analysis_asof`. It records actual execution time separately, rejects future/snapshots older than 24 hours, and requires the actual latest completed session to match. No system clock or trading day is changed; refreshed prices still must yield the exact approved wire hash. Free previews may use `--analysis-asof` to prove reproducibility.

## Final hosted preflight

The review branch controller now adds only `stream_options: {include_usage: true}` at its native dispatch observer. Official DeepSeek documentation says final content chunks include usage even when this option is omitted; true also adds null usage fields to earlier chunks. The raw recorder reads the terminal content chunk, including cache hit/miss and reasoning details. Interrupted streams can still lack usage and remain unknown. Previous captured hashes are not authorization for this revised request.

Workflow 04 defaults to the free preflight, uses no Secret expression, pins business source and SDK versions, and runs both offline test modules. Its optional `approval_probe=true` starts only an empty protected job in `nvda-one-call-approval`; it cannot send any model request, even after approval. The environment has the owner as required reviewer and restricts the review branch. Self-review is allowed so the sole owner can manually approve their own dispatch; the controller must never approve on their behalf. Pending-deployment evidence verifies the barrier without approving the job. Actual statuses and any administrator-bypass limitation belong in the delivery report.

No live-sending Actions job is included. Separate explicit Secret-upload and single-call authorizations remain necessary. Hosted free acceptance is not permission to enable the live CLI mode or production schedule. Original workflow defaults and business source remain unchanged outside this isolated controller/workflow.

## Hash-specific frozen execution

After the user approved the exact Phase 2E SHA, the manual workflow is prepared to load the previously captured artifact, not rebuild a prompt or refresh quote/news inputs. `nvda_frozen_once.py` passes the saved packet to the original analyzer dispatch/stream consumer and reuses its native parser and report renderer. The tested OnePostGuard/LiveSession modules are unchanged. The wire hash still must match before any POST. Actual latest completed session and snapshot age are checked without replacing the approved evidence.

The workflow is dispatch-only, owner-only, protected by `nvda-one-call-approval`, and defaults execute_live=false. An actual run must wait for the user's GitHub review; the automation must not approve the environment. The downloaded source artifact is Run 38688465193. The model key is injected only into the send step and the final credential scan; no mail or batch analysis step exists. A failed/unknown send must never be rerun. Frozen replay has separate fake-network tests, including byte-equivalent JSON body identity through original LiteLLM.
# Phase 2F offline renderer repair

The frozen controller now calls `NotificationService()` through `render_native_report`,
matching the fixed upstream constructor. No analysis source, request parameters,
transport guard, historical response or workflow trigger is changed. The original
paid Run 38693407248 remains a failure after its successful unique POST; it must
never be rerun to repair rendering. Replay the saved response locally with all
network and SMTP access denied, keeping derived reports separate from evidence.
The two constructor contract tests are offline; no new hosted paid run is authorized.
