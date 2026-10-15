# Final free NVDA request preparation

Business source is pinned to 578fc55364bf32b7299e84eea7a630eb7e93e973;
controller source is a separately reviewed commit. Free capture injects a
placeholder credential, never a real Secret. The first POST is intercepted at
HTTPX before transmission, with streaming usage enabled. Old authorization
files and source pins must not be reused. No business source changes are made.

The existing native Yahoo fundamental pipeline is enabled for this preparation
only. Its original context is saved. An independent small data-preparation
adapter reads three recent official RSS titles/URLs/timestamps into the native
news_context parameter and adds provenance to the native context summary.
It does not claim full article access or enable the production news pipeline.

Official quarterly figures are compared to Yahoo fields. A report-period
annotation is changed only if all three figures and USD match the publisher's
statement; both the original Yahoo date and official period remain explicit.
Missing/mismatched data is kept unverified. Exact publication time is not
invented. Current preparation is not a historical-availability assertion.

The frozen live controller still requires explicit independent authorization,
an exact SHA, a valid run, expiry and the new business pin. The real workflow
template is disabled and must retain nvda-one-call-approval and owner-only
manual execution. This phase sends no model POST, notification or scheduled
task and issues no live authorization. Read-only account checks do not grant
permission to generate content.

This deployment-specific English note has no pre-existing translation.

## Separately authorized frozen execution

The manual workflow now pins controller source to
93d8ba0110460718517e0e4ca11d0b051b518a29 and business source to
578fc55364bf32b7299e84eea7a630eb7e93e973. It downloads only the final
Run 38704910265 artifact and accepts SHA
f7ca322b236ff4b993a081e33090740eb9891fa584f0abf33dbab0677cf88e3b.
The user must personally review nvda-one-call-approval. No automation approval
is permitted. The snapshot and latest complete trading day are checked again
without fetching or updating market/news data. One POST only, no fallback,
retry, mail, batch analysis or cron. Workflow failure must not cause a rerun.
