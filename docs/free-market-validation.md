# Fork-only manual free-market acceptance

This deployment workflow reuses the official Python, dependency installation,
upstream CLI and artifact actions. All original workflow files remain byte-identical
with a `.disabled` suffix; GitHub does not execute them. Only
`01-free-market-validation.yml` is recognized, and it has `workflow_dispatch` only.
There are no repository secrets or notification credentials in its environment.

The one-run observer calls the original CLI with
`--dry-run --no-notify --no-market-review --stocks ...` against a new empty SQLite
database. It neither replaces the data adapter nor manufactures successful data.
It records source HTTP status, fresh daily rows and provider identity metadata;
model, SMTP and notification paths are denied before transport. A Yahoo 429 stops
further Yahoo traffic. Missing data, identity ambiguity and stale bars stay failures.

Run NVDA first. Review real source evidence and zero denied-cost/notification
attempts before manually selecting `watchlist35`. A workflow exit code alone does
not prove current OHLCV correctness or company identity. The JSON evidence records
each symbol independently, including unresolved SPCX/SKHY and BRK.B mapping.

This is data-only acceptance. It does not generate AI analysis, configure DeepSeek,
send Gmail, enable the production schedule, or reuse any previous custom research
or budget module. Restoring original workflow filenames must be a separate reviewed
deployment change, as it would reintroduce upstream automatic triggers.
