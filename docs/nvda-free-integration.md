# Free integration acceptance

This review branch retains the BRK.B Yahoo-only mapping and native 90-day
prefill evidence. The only additional business changes are quote currency
resolution/display in src/formatters.py, src/analyzer.py, and
src/notification.py. Trading currency is never taken from financial reports.
Explicit quote metadata wins, known markets supply a fallback, and unrecognized
currency remains unverified. No FX conversion or ADR share-ratio substitution
is performed. Native financial currency fields remain unchanged.

The manual 04-nvda-free-preflight.yml now has a free-only entry. It injects no
model, search, email, or other service secrets. Full requirements.txt is
installed, with pytest as a test dependency; no incompatible LiteLLM override
is used. Offline tests block external sockets; Windows literal loopback is
allowed only for asyncio IPC. Replay fully blocks network/SMTP, reconstructs
the deterministic display snapshot from frozen quotes, and preserves the
historical raw model text and dashboard. It is not a new dollar-prompt model
response. The old paid workflow remains in Git history and evidence packages;
it is not run again. Future live tests require a newly reviewed business pin,
request body/hash, and explicit authorization.

The separate free-data step uses the unmodified Yahoo fundamental adapter,
records raw statement tables/metadata and per-field provenance, and stops
Yahoo network access after an access restriction. Missing fields are not
success. Quarterly/TTM fallbacks and derived net income are identified; current
Yahoo data does not prove historical publication availability. The public
NVIDIA newsroom RSS probe is not an enabled DSA news provider or a general
redistribution license. No public SearXNG instance is enabled automatically.

No production schedule, Gmail delivery or model POST is authorized by this
acceptance workflow. Disable Actions again after the manual run. Existing
Secrets are neither read nor changed. This deployment-specific English
document has no pre-existing translated counterpart.
