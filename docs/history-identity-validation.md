# Fork-only manual Phase 1B evidence

This workflow is manual-only, credential-free, and blocks model/notification transports with the existing Phase 1 guards. It does not run an analysis task.

For 34 supported symbols it calls the original DataFetcherManager.get_daily_data with days=90. The original BaseFetcher expands this to 180 calendar days. End is the day after the latest completed US trading session, exclusive in Yahoo.

BRK.B has no working configurable Yahoo alias in this baseline. The separate BRK-B yfinance SDK probe establishes provider data availability only; it does not fix original CLI routing or write renamed prices into its database. Original dry-run still uses days=30 and is not changed by this workflow.

Evidence requires at least 60 complete daily bars, latest completed session, exchange-calendar continuity, OHLCV integrity, identity metadata, and all-bar correspondence to fresh captured source responses. Pre-listing SPCX/SKHY prices are flagged rather than silently accepted. Listing dates are issuer-announced 2026-06-12 and 2026-07-10 respectively; source documents are retained in the separate delivery archive.

No old artifacts or price caches are restored. Pip caches contain dependencies only. The diagnostic writes a new evidence directory and refuses overwrite. Leave automatic upstream workflows disabled. Disable this workflow and repository Actions again after evidence collection.

This English Fork deployment note has no existing translated counterpart; no product documentation or business configuration contract is changed.
