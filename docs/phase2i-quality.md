# Phase 2I: minimal research-input corrections

The native analyzer now includes computed opening direction and MA5/10/20/60
positions in its existing user prompt. A close crossing requires both bars'
own MA, adjacent exchange-calendar sessions and non-provisional bars. Missing
history/calendar data yields an unknown event, not a substituted MA20/MA60.
The existing trend engine supplies current MA60; the daily-frame fallback
calculates the actual 60-row window before taking the final two bars.

The prompt distinguishes limited news evidence from comprehensive search, and
requires qualification of headline-only input, Yahoo financial ratios, earnings
quality and nominal entry-to-stop loss. These are input constraints, not proof
that an untested model will comply. Existing output schema and renderer remain.

The independent frozen-request controller binds the saved RSS-preparation audit
to existing `news_evidence_present`, `news_result_count` and `data_sources`
fields. RSS does not set `search_performed`. Original model text is unchanged.
Native normal and Agent pipeline paths derive search status from actual search
counts, including a zero-result search. No RSS crawler is added to production.

Yahoo fundamentals use the same class-share spelling as quotes (`BRK.B` ->
`BRK-B`); internal storage/display identity stays dotted. Missing or estimated
fundamentals still require explicit provenance outside the aggregated adapter
bundle; the adapter's fallback behavior itself has not been rewritten.

This patch adds no model invocation, retry policy, scheduler, mail sender,
budget database or custom research framework. Existing manual workflows retain
their old pins and remain disabled. A new code pin, fresh request capture,
independent authorization and environment approval are required before any
future paid test. Historical frozen packets must not be regenerated in place.

Review the accompanying evidence package for local-only data coverage, offline
test results, raw historical responses and budget risks. Batch paid analysis is
not approved by these tests.
