# Lightweight real-report quality iteration

Use the read-only NVDA/MU/QQQ fixtures in `tests/fixtures/mvp_real_three`.
They are historical model outputs, not approved research or fresh market data.
Run only affected tests:

```bash
python -m pytest tests/test_research_quality_baseline.py tests/test_mvp_completion.py -q
```

Review six dimensions: quote accuracy, technical facts, financial/news evidence,
risk arithmetic, cross-section consistency, and evidence-based analytical depth.
The fixed regression tests expose known errors and check the native prompt and
deterministic calculations. They do not automatically validate arbitrary prose.
Missing evidence and unsupported inference require editorial review.

This iteration changes only the existing prompt: respect supplied pairwise MA
facts, preserve watch-only/no-personal-holding context, and use scenario-specific
stops plus Python arithmetic. It removes an instruction that simultaneously
asked the model to write loss percentages. No model, transport, workflow or
publishing policy is changed. English and Chinese prompt branches are aligned.

An offline prompt test cannot prove improved model accuracy. Compare a separately
authorized new output using the same six dimensions. Do not count repeated
mentions as independent errors or report a whole-document accuracy percentage
from this tiny, selected baseline. Keep raw text and editorial notes separate.

The manual preparation and execution adapters now pin candidate `15a93504f909d1af118d95f6108af8bf4c7d10db`. The free three-symbol capture uses this same native code; it does not authorize a model request.

Run 39014776142 returned three complete real reports. Fixed follow-up samples live
in `tests/fixtures/quality_live_20261017`; raw prose errors remain intact. Follow-up
changes remove price-forcing legacy examples, label the MA60 reference relative
to the close, and keep unverified crossings distinct from verified non-events.
Run `tests/test_quality_live_followup.py` plus the small baseline tests. These are
offline compatibility checks; the follow-up prompt has not had another paid test.

The next candidate reuses native MA60 context construction for the preceding
daily bar and passes the native RSI(12) value with strict native thresholds
(below 30 oversold, above 70 overbought). MA ordering uses available numeric
values only. Risk prose in rendered reports is generated from the same validated
`risk_plan` rows as the calculation table, clearly labeled as program output.
Raw model prose remains unchanged.

The optional free preparation `--research-data` packet provides reviewed issuer
financial releases using the existing evidence input. It preserves the original
Yahoo block, replaces the selected quarter as a whole, and clears the earlier
Yahoo summary to avoid mixed-quarter prompts. Report date is not publication
time; date-only disclosures use a conservative availability proxy. The checked
packet is a dated evidence snapshot, not an evergreen financial provider or a
comprehensive news search. ETF company-finance fields remain not applicable.
