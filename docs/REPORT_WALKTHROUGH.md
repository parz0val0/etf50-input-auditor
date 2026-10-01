# An actual synthetic report

[English](REPORT_WALKTHROUGH.md) · [简体中文](REPORT_WALKTHROUGH.zh-CN.md)

The six input records below are fictional. This is actual program output, not a fabricated screenshot or market result. Core CLI/report text is currently Chinese; this page explains it in English.

## Run it locally (publicly runnable)

From the repository root, after the README installation, with a fresh directory:

```sh
.venv/bin/python scripts/reproduce_onboarding_case.py --output onboarding-demo
```

The demonstration exits0 after checking that the bad input audit exits1 and corrected input audit exits0. The corrections are explicit fictional earlier observations/estimates and bid/ask, not relabeling timestamps or settlement prices. See [eight field changes](../examples/onboarding/output/comparison.md).

## Read the before/after

| Purpose | Before | After |
|---|---|---|
| Historical-IV input records | 3 consistent, 2 need evidence, 1 blocked / 6 | 6 consistent / 6 |
| Pair input records | 4 consistent, 2 blocked / 6 | 6 consistent / 6 |
| Complete conditionally consistent pairs | 2 / 3 | 3 / 3 |

Records and pairs are different denominators. These are declarations agreeing under implemented checks, not research eligibility or accuracy.

The before JSON summary, excerpted without changing values:

```json
{
  "rows": 6,
  "historical_iv": {
    "conditional_input_consistent": 3,
    "needs_evidence": 2,
    "blocked": 1
  },
  "pair": {
    "conditional_input_consistent": 4,
    "blocked": 2
  },
  "conditional_pairs": 2
}
```

[Before JSON](../examples/onboarding/output/before/report.json) · [After JSON](../examples/onboarding/output/after/report.json) · [Before offline HTML](../examples/onboarding/output/before/report.html) · [After offline HTML](../examples/onboarding/output/after/report.html)

GitHub displays HTML as source; download the repository and open the locally generated report in your browser. It is not a hosted application. Start with the issue code, business record and peer record, then the suggested repair. Expected issues include SPOT_ALIGNMENT_MISSING, Q_INPUT_MISSING and SETTLEMENT_NOT_INDEPENDENT.

## A clean report can still have unknown facts

Even after correction, evidence_truth_verified remains false. The fictional policy and references have not been authenticated; real source permissions and the daily universe remain unverified. No IV, carry, market prediction, trading or efficiency improvement is established. A real record with missing evidence stays unknown; do not copy fictional q=0 or event coverage into your own data.

[Boundaries](TOOL_BOUNDARIES.md) · [Case specification](ONBOARDING_CASE.md) · [Complete workflow](GETTING_STARTED.md)
