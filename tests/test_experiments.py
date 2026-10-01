import copy
import json
from math import sqrt

import pytest

from derivatives_pricing import experiments, research
from derivatives_pricing.black_scholes import BSInputs, price


def test_convergence_repeated_error_metrics_and_fixed_seeds():
    payload = {"tree_steps": [25, 100], "mc_paths": [200, 800], "seeds": [11, 29, 47]}
    result = research.convergence(payload)
    again = research.convergence(payload)
    assert result["status"] == "ok"
    for budget, repeated in zip(result["mc"], again["mc"]):
        prices = [item["price"] for item in budget["repetitions"]]
        assert prices == [item["price"] for item in repeated["repetitions"]]
        expected = sqrt(sum((value-result["reference_price"])**2 for value in prices)/len(prices))
        assert budget["rmse"] == pytest.approx(expected)
        assert budget["effective_count"] == 3 and budget["failed_count"] == 0
        assert all(item["ci_lower"] <= item["price"] <= item["ci_upper"]
                   and item["standard_error"] > 0 for item in budget["repetitions"])
    json.dumps(result, allow_nan=False)


def test_crr_invalid_probability_is_not_zero_error():
    result = research.convergence({"sigma": .001, "r": 2, "q": 0,
                                   "tree_steps": [1], "mc_paths": [20], "seeds": [1]})
    assert result["status"] == "ok"
    assert result["crr"][0]["status"] == "failed"
    assert result["crr"][0]["price"] is None and result["crr"][0]["error"] is None
    assert research.convergence({"mc_paths": [21]})["status"] == "error"


def test_risk_scan_parity_bounds_contract_units_and_expiry():
    result = research.risk_profile({"S": 2.7, "K": 2.7, "contract_unit": 10000, "points": 5})
    assert result["status"] == "ok"
    assert all(row["parity_ok"] and row["bounds_ok"] for row in result["rows"])
    row = result["rows"][2]
    assert row["price_per_contract"] == pytest.approx(row["price"]*10000)
    assert row["greeks_per_contract"]["vega"] == pytest.approx(row["greeks"]["vega"]*10000)
    expiry = research.risk_profile({"T": 0, "points": 3})
    assert all(row["price"] == row["payoff"] and row["greeks"] is None
               for row in expiry["rows"])
    zero = research.risk_profile({"spot_min": 0, "points": 3})
    assert zero["rows"][0]["call_price"] == 0 and zero["rows"][0]["parity_ok"]
    assert zero["rows"][0]["greeks"] is None
    assert research.risk_profile({"spot_min": -1})["status"] == "error"
    json.dumps(expiry, allow_nan=False)


def test_fixed_split_and_training_only_predictions_ignore_holdout_prices():
    dataset = experiments._dataset({})
    altered = copy.deepcopy(dataset)
    for quote in altered["holdout"]:
        quote["price"] = quote["price"]*3 + 1
    first = experiments._compare_dataset(dataset, mc_paths=100, budget=36)
    second = experiments._compare_dataset(altered, mc_paths=100, budget=36)
    assert {(q["K"], q["T"]) for q in dataset["train"]}.isdisjoint(
        {(q["K"], q["T"]) for q in dataset["holdout"]})
    for row1, row2 in zip(first["rows"], second["rows"]):
        for method in experiments.METHODS:
            assert row1["predictions"][method]["price"] == row2["predictions"][method]["price"]
            assert row1["predictions"][method]["status"] == row2["predictions"][method]["status"]
    assert first["methods"]["bs_constant"]["fit"]["sigma"] == second["methods"]["bs_constant"]["fit"]["sigma"]
    assert first["methods"]["bs_constant"]["metrics"]["holdout"]["rmse"] != second["methods"]["bs_constant"]["metrics"]["holdout"]["rmse"]


def test_training_iv_interpolation_refuses_extrapolation_and_invalid_knots():
    dataset = experiments._dataset({})
    interp = experiments._IVInterpolation(dataset["train"], dataset["S"], dataset["r"], dataset["q"])
    assert interp.predict(dict(K=100, T=1.5, option_type="call")) == (None, "outside_training_maturities")
    assert interp.predict(dict(K=160, T=.5, option_type="call")) == (None, "outside_training_strikes")
    bad = [dict(row, price=300) for row in dataset["train"]]
    empty = experiments._IVInterpolation(bad, 100, .02, .01)
    assert empty.predict(dict(K=100, T=.5, option_type="call")) == (None, "no_valid_training_iv")


@pytest.mark.parametrize("state", ["quadrature_not_converged", "ok"])
def test_failed_heston_predictions_have_null_metrics_and_common_denominator(monkeypatch, state):
    dataset = experiments._dataset({})
    monkeypatch.setattr(experiments, "heston_price_checked", lambda *args, **kwargs: {
        "status": state, "price": None, "quadrature_difference": .1})
    result = experiments._compare_dataset(dataset, mc_paths=100, budget=36)
    held = result["methods"]["heston"]["metrics"]["holdout"]
    assert held["effective_count"] == 0 and held["failed_count"] == 20
    assert held["rmse"] is None and held["mae"] is None
    assert result["common_valid_holdout"]["count"] == 0
    json.dumps(result, allow_nan=False)


def test_comparison_group_counts_and_diagnostics_use_fixed_primary_start():
    result = research.model_comparison({"mc_paths": 100, "heston_diagnostics": True})
    assert result["status"] == "ok" and result["split"]["training_count"] == 15
    assert result["split"]["holdout_count"] == 20
    for info in result["methods"].values():
        for dimension in ("moneyness_bucket", "maturity_bucket"):
            for subset, expected in (("training", 15), ("holdout", 20)):
                assert sum(item["total_count"] for item in info["groups"][dimension]
                           if item["split"] == subset) == expected
    diag = result["heston_diagnostics"]
    assert diag["selected_start_id"] == 1 and diag["holdout_used_for_selection"] is False
    assert len(diag["runs"]) == 3
    assert diag["runs"][0]["fit"]["params"] == result["methods"]["heston"]["fit"]["params"]
    assert diag["runs"][0]["initial_params"] != result["source_summary"]["known_params"]
    json.dumps(result, allow_nan=False)


def test_historical_comparison_scope_source_and_exclusion_counts(monkeypatch):
    rows = []
    for tenor in (.25, .5):
        for i, strike in enumerate((2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0)):
            rows.append(dict(date="2024-01-02", code=f"{tenor}-{i}",
                             expiry="2024-04-02" if tenor == .25 else "2024-07-02", cp="C",
                             adjustment_flag="M", contract_unit=10000, official_strike_mismatch=False,
                             invalid_terms=False, spot_conflict=False, volume=100, spot=2.7, strike=strike,
                             T_act365=tenor, close=price(BSInputs(2.7, strike, tenor, .02, .2), "call")))
    rows.extend([dict(rows[0], code="adjusted", adjustment_flag="A"), dict(rows[0], code="illiquid", volume=0)])
    provenance = {"normalized_sha256": "fixture", "audit_status": "complete"}
    monkeypatch.setattr(experiments, "snapshot", lambda *args, **kwargs: {
        "status": "ok", "total": len(rows), "rows": rows, "truncated": False, "source_summary": provenance})
    payload = dict(mode="historical_scenario", date="2024-01-02", r=.02, q=0,
                   assumptions_acknowledged=True, mc_paths=100, max_evaluations=36)
    result = research.model_comparison(payload)
    assert result["status"] == "ok" and result["source_summary"] == provenance
    assert result["split"]["scope"] == "same_day_cross_section_not_out_of_time"
    selection = result["selection_summary"]
    assert selection["source_rows"] == selection["eligible_rows"]+selection["excluded_rows"] == 16
    assert selection["eligible_rows"] == 14 and selection["excluded_rows"] == 2
    assert result["methods"]["bs_constant"]["fit"]["sigma"] == pytest.approx(.2, abs=1e-5)
    json.dumps(result, allow_nan=False)
    assert research.model_comparison(dict(payload, assumptions_acknowledged=False))["status"] == "error"
