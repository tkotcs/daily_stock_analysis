# Phase2U manual test preparation

Reuse the frozen 16K request and native business revision. The workflow-only `allow_peak_test` boolean defaults to false; it is not a production environment setting. True additionally requires a Phase2U reference containing the approved full request SHA. It changes only tariff-window eligibility, never the request body, expiry, latest-session check, fees/reserve, one-POST protection, or Environment approval. No .env configuration was added.

Before dispatch obtain new explicit one-request hash and $0.03 approval; then require the user to approve nvda-one-call-approval on GitHub. No dispatch is authorized by this preparation. No retries, fallback, Gmail or schedule. Before real transmission recheck time, session, provider model/balance/prices and the complete request SHA. The reviewed frozen material expires at 2026-10-16T20:00:00Z regardless of rate window.

Only the changed rate-window path and existing transport/hash/timeout checks are selected (19 tests). Full business regressions and a duplicate free hosted run are intentionally omitted. Phase2T hosted evidence remains valid for unchanged SDK/guard paths; the opt-in is locally tested, not yet hosted.

The Chinese user-facing authorization packet accompanies the delivery ZIP; this narrowly scoped test note needs no separate bilingual product manual update. Rollback: use the prior prepared workflow commit 3a269ecbaed27be7a8d6001a620e958d027130bc, which retains default off-peak blocking.

Startup follow-up: fixed controller 9e94ecc registers the pinned source before LiveSession. The free job now runs only three actual-main isolated child processes with fake transports and no model secrets. The protected paid job points to the fixed controller but is not dispatched or authorized by this repair. Free fixture POST records are synthetic, never provider usage. Native business code and frozen request bytes remain unchanged.
