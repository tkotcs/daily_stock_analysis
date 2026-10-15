# Native stock research depth and budget (review only)

The existing analyzer/JSON/parser/notification pipeline is retained. No paid run,
Gmail delivery, remote workflow changes or production schedule is authorized.

`STOCK_ANALYSIS_MAX_TOKENS=16384` controls per-stock research generation only;
the default is 16384, clamped to 256–16384. Set 8192 to restore the old ceiling.
This is distinct from `LLM_MAX_TOKENS` or `ANTHROPIC_MAX_TOKENS`. It is a ceiling,
not a desired length or cost limit. 8–11K input and 5–6K output are planning
ranges, not padding requirements or hard token guarantees.

Use the existing `.github/phase2l-deepseek.yaml` to preserve Flash and disabled
thinking; inspect the actual final HTTP body. Preserve `stream_options` usage.
The offline review controller uses placeholder credentials, clears real keys,
disables retries/fallback and intercepts the first POST. It has no live mode.
Historical paid controllers and authorizations still require 8192 and remain
unchanged/disabled. They cannot execute this 16384 request. A future authorized
test requires separately reviewing the sender's new exact max_tokens binding,
cost reservation, frozen hash, expiry and GitHub personal approval. No old
authorization can be reused. Native stock pipeline's general retry behavior is
not replaced here; production safety is not established by this offline test.

The native prompt asks for `dashboard.battle_plan.risk_plan`:

```json
{"max_position_pct":20,"scenarios":[{"entry":100,"stop":95,"target":110,"position_pct":10,"trigger":"hypothetical close/volume confirmation","invalidation":"failure condition"}]}
```

Numbers above are schema examples, not market evidence. A null plan means no
justified scenario; target may be null. Python validates finite positive prices,
stop < entry < target for LONG scenarios (when target exists), positions within
one shared cap and nonempty conditions. It computes nominal loss and reward/risk;
invalid or missing plans are not inferred from prose. All scenarios are
alternatives, not simultaneous allocations. No price-source or trading validity
is implied by arithmetic correctness. This small calculator is not a new research
framework or a full natural-language validator.

When `risk_plan` is present, detailed dashboard/single-stock views display this
calculated table instead of contradictory legacy sniper/position prose; raw JSON
and raw model text remain unchanged. Legacy reports without the new object are
still reviewable but have no verified risk plan. This is not a retrofit that makes
Phase 2P's raw response publishable. Free-form narrative elsewhere still requires
human review. Computed MA state/crossing lines accompany model explanation.

Single-stock long-field clipping is removed. Detailed dashboard/single views show
native short/medium outlook, MA, volume, financial, sector, business and news
paragraphs without length slicing. Existing compact WeChat/brief summaries retain
their intentional length limits and are not the full research delivery mode.
Full research uses detailed Markdown/HTML; never treat a compact summary as the
entire model response. Chinese and English prompt guidance are updated together;
this operational review note is English-only, with Chinese delivery reports.

For USD/1M tokens at off-peak cache miss 0.15/output 0.60, 770 calls cost:
8K/5K $3.234 ($3.8808 with 20% margin); 10K/6K $3.927 ($4.7124);
12K/7K $4.62 ($5.544). 16,384 is only a ceiling: 10K input and full output
would cost $8.724408/month ($10.4692896 with margin). No cross-Runner monthly
hard stop is verified. Reduce redundant evidence/verbose output if projected
usage exceeds $5; do not promise a hard cap, silently switch models or enable
35-stock production. Off-peak eligibility must be checked at actual request time;
this branch deploys no schedule or off-peak enforcement service.
