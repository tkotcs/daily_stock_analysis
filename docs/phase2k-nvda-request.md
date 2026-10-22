# Phase 2K: locked native NVDA request, awaiting new authorization

The accepted analysis business source is fixed at
`f93a7609e569e3b6c6372e652a3d36a27225d783`. The test controller's `FIXED`
pin now points to that commit; old `578fc553...` authorizations are rejected.
No analysis-business file changes are added to Phase 2J.

Manual free Run `38736466986`, controller
`39b224567f89f313c54b5c6fb4791a6a3f2caf1e`, captured the final native
SDK body before transport. Actual model POSTs: zero. The body is frozen as
`ORIGINAL_REQUEST_PACKET.json` in that run's `nvda-inputs` artifact.

- Canonical complete-request SHA256:
  `043d5d42d52c016c12cec10fef9f73865459290aec634bbe7bd7adcea8acce71`
- Latest completed US session: 2026-10-14; cutoff:
  2026-10-15T12:42:02.263395+00:00.
- Model `deepseek-flash`, official `/chat/completions`, stream enabled,
  `stream_options.include_usage=true`, temperature 0.7, maximum output 8192.
- Thinking/reasoning effort is not explicitly set in the native request;
  current official default is thinking enabled. Do not label it disabled.
- Approximate cl100k input: 7946; message UTF-8 bytes: 22128. This is not
  supplier usage or a native hard input cap. Full body: 22256 bytes.
- Peak all-miss byte-allowance scenario plus 8192 output: $0.0168144;
  proposed single-call reserve $0.03, not a supplier hard spending limit.

The disabled paid workflow now checks out that controller and accepted business
source, downloads exactly this new artifact, and checks the full hash/cutoff.
It still requires a separate authorization reference and genuine human approval
in `nvda-one-call-approval`. The existing preparation branch is already allowed;
no reviewer, bypass setting or branch whitelist is changed. `execute_live` stays
false by default. This preparation phase grants no new paid authority.

Keep materials immutable. If the completed session changes, the 24-hour validity
expires, or any payload/price/news/parameter changes, stop and obtain a new
capture/hash authorization. Do not regenerate the prompt inside the frozen send
entry. Unknown outcomes, timeouts and errors never justify a second POST.

The official quarterly statement matched the three Yahoo amounts, with original
Yahoo period labeling retained. RSS only supplies titles/publication metadata,
not article bodies or an exhaustive adverse-news search. Structure pass does
not imply factual quality. A future response still needs human checks of gap
direction, all four MAs, state versus crossings, source scope, financial periods,
currency, entry-specific stop loss and unsupported earnings-quality claims.

There is still no verified cross-runner monthly budget hard stop. This single
request proposal does not authorize 35-stock paid analysis, Gmail or scheduling.
