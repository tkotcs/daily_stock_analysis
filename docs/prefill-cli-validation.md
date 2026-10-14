# Phase 1C minimal compatibility acceptance

The only business change converts a class-share dot to a hyphen in the Yahoo US-symbol branch. Canonical input, database and display remain BRK.B. Index mapping runs before the stock branch. No pipeline/config defaults change.

The credential-free workflow uses original DataFetcherManager.get_daily_data(days=90) and original DatabaseManager.save_daily_data. It validates fresh source responses before saving into a new DATABASE_PATH, then calls original main.py --dry-run --no-notify --no-market-review with all 35 canonical codes. No old price artifacts are restored. The CLI observes the same prefilled database and retains original resume behavior.

Dry-run deliberately does not calculate trends. A separate instrumentation-only probe delegates to the original process_single_stock and StockTrendAnalyzer methods, then raises a BaseException sentinel after the original technical calculation. This intentionally stops before news/LLM research. It records the actual database range read and checks the original MA60 equals the last 60 closes, with its first non-null value at index 59. This is a production technical-path probe, not a complete research run.

Existing configuration disables realtime, fundamental/network extras, market review, agents, notifications and schedules during this acceptance. Paid/model/SMTP guards and a public-host allowlist remain active. No model or email credentials enter the workflow. Any failure remains in the artifacts. Original prior-phase evidence stays immutable. Disable repository Actions again after collection.

This Fork deployment-only English note has no existing translated counterpart. No new business environment variable is introduced.
