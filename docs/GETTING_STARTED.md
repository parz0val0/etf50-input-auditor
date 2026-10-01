# ETF50 input auditor

[English](GETTING_STARTED.md) | [简体中文](GETTING_STARTED.zh-CN.md)

A small local research-input checker for people with 510050 option CSVs preparing historical-IV or same-term call-put work. **0.4.0rc6** adds conservative supplier CSV preflight. It identifies contradictions, missing evidence and unsupported static terms before modeling. This is ordinary Python software: no AI service, account, API key or network is needed at runtime. Installation may download a build backend. It does not price options, certify data or complete the historical empirical study.

## Install and verify (publicly runnable)

Python 3.9+, from this repository root on macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/etf50-audit --version
.venv/bin/etf50-preflight --help
```

Core runtime has no third-party dependencies. Windows paths have not been tested. See [installation](INSTALLATION.md).

## Complete synthetic demonstration (publicly runnable)

Use fresh output paths. The normal case, failure case and correction are fully synthetic, never market evidence:

```sh
.venv/bin/etf50-audit examples/admission/synthetic_consistent.csv --policy examples/admission/synthetic_policy.json --output audit-output/normal
.venv/bin/etf50-audit examples/admission/synthetic_failures.csv --policy examples/admission/synthetic_failure_policy.json --output audit-output/failures
.venv/bin/python scripts/reproduce_onboarding_case.py --output onboarding-demo
```

The first command exits0, the second exits1 with a report (expected findings). The third exits0 after verifying the before/after case: future ETF input, not-yet-known q and settlement-as-market-price are corrected using explicit fictional earlier observations, estimates and BBO. Read `onboarding-demo/comparison.md` and its HTML report links. Corrected inputs are only conditionally consistent; their evidence is fictional. [Case details](ONBOARDING_CASE.md).

## Supplier CSV: inspect, review, then convert

[Supplier requirements](SUPPLIER_REQUIREMENTS.md) distinguish the ten parseable base columns from additional historical-IV/pair evidence and high-quality research requirements. UTF-8 CSV (BOM allowed), one contract per Shanghai date, unique headers; Excel must first be exported. Do not infer units, timezone, source or price meaning from convenience. [Full schema](ADMISSION_SCHEMA.md).

Publicly runnable preflight of a synthetic daily CSV:

```sh
.venv/bin/etf50-preflight examples/admission/synthetic_minimal_daily.csv --output audit-output/preflight
```

Expected exit0 for an unambiguous basic schema; the JSON still lists missing purpose evidence and **does not certify admission**. It includes suggestions, ambiguities, type/date/time warnings, unknown columns and up to five preview rows. Preflight exit0 means the inspection itself found no structural/mapping warnings; exit1 means review findings or unsuccessful admission; exit2 means invalid input/output. Main audit has its own0/1/2 meaning below.

User-data templates (require your own legal local files; not a public demo):

```sh
.venv/bin/etf50-preflight user-data/vendor.csv --output audit-output/review
.venv/bin/etf50-preflight user-data/vendor.csv --mapping user-data/confirmed-mapping.json --expected-source-sha256 SOURCE_SHA256_FROM_REVIEW --policy user-data/policy.json --output audit-output/converted
```

Review the suggestions and original dictionary; write a JSON object such as `{"date":"交易日期","code":"合约代码"}` expanded to all required fields. Choosing `price` explicitly does not verify its semantics. Alias collisions need a deliberate one-to-one mapping. Missing required columns produce a report but no normalized CSV. Confirmed mapping only renames columns, preserving values; it does not translate C/P, dates, units or fabricate evidence. Each conversion requires the current source hash; reusable mappings are hashed too. Successful conversion calls the **same main checker**, optionally with your policy; read the embedded admission result. Missing policy prevents verified coverage. The source is untouched and existing output directories are refused.

Previews contain original IDs/prices: keep them private. Put files in ignored `user-data/` and `audit-output/`. Inspect every report before sharing; gitignore is not a security guarantee.

Publicly runnable Chinese-header/BOM confirmation demonstration; it creates a synthetic supplier CSV, records an explicit mapping and source hash, and verifies the same primary checker:

```sh
.venv/bin/python scripts/reproduce_preflight_case.py --output audit-output/preflight-demo
```

Expected exit0; fictional evidence is never authenticated.

## Interpret results and limits

Main-audit exit0 means implemented checks are conditionally consistent; exit1 means reported findings; exit2 means malformed input/output. `blocked` means an implemented hard contradiction; `needs_evidence` means absent/unusable evidence; `conditional_input_consistent` means declared inputs agree under implemented conditions. Historical-IV and pair purposes are separate; peer failures propagate across the whole pair. Some known unusable inputs still reside in the needs-evidence bucket; do not treat that bucket as a promise that adding a citation fixes values.

Only static M/10000 terms are supported. Adjusted, cross-event and unverified event-day terms are rejected. User-declared event coverage is not certified. No source/permission authentication, daily universe certification, IV/carry estimation, market effectiveness, financial advice or trading. Unknown inputs remain unknown. HTML escaping/structure is tested; browser visual review remains unverified. [Boundaries](TOOL_BOUNDARIES.md).

The [first simulated evaluation](SIMULATED_USER_EVALUATION.md) did not establish higher accuracy or human time savings. Subsequent simulated regressions test mechanisms, not an independent efficacy claim. The reusable numerical toolkit and input checks are deliverables; the original historical empirical study remains incomplete. [Numerical auxiliary](NUMERICAL_AUXILIARY.md) · [Related work](RELATED_WORK.md) · [Release checklist](RELEASE_CHECKLIST.md).

## License

[MIT](../LICENSE), Copyright (c) 2026 JasonChen. This license covers this software, not supplier data or third-party materials; preserve applicable attributions. Version 0.4.0rc6 has been published.
