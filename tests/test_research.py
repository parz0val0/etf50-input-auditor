import json

from derivatives_pricing import research


def test_json_api_and_same_model_comparison_labels():
    inputs = dict(S=100, K=100, T=.5, r=.02, q=.01, sigma=.2,
                  option_type="call", mc_paths=2000, tree_steps=150)
    priced = research.pricing(inputs)
    assert priced["status"] == "ok"
    assert all(priced["methods"][name]["status"] == "ok"
               for name in ("bs", "crr", "mc", "heston"))
    compared = research.comparison(inputs)
    assert compared["reference"]["type"] == "bs_same_model"
    assert compared["methods"]["bs"]["absolute_error_to_reference"] == 0
    json.dumps(compared, allow_nan=False)
    observed = research.pricing(dict(inputs, observed_price=5.8, observed_source="test_fixture"))
    assert observed["implied_volatility"]["status"] == "ok"
    assert abs(observed["implied_volatility"]["roundtrip_residual"]) < 1e-9
    assert observed["implied_volatility"]["source"] == "test_fixture"


def test_surface_and_calibration_demonstrations_are_labeled():
    surface = research.iv_surface({"mode": "synthetic"})
    assert surface["status"] == "ok" and surface["point_count"] == 21
    assert surface["input_label"] == "synthetic_known_heston_parameters"
    assert all(p["status"] == "ok" for p in surface["points"])
    fit = research.heston_experiment({"mode": "synthetic"})
    assert fit["status"] == "ok" and fit["fit"]["rmse"] < 1e-5
    assert fit["training_count"] == 15 and fit["holdout_count"] == 9
    assert fit["holdout_rmse"] < 1e-4
    assert fit["initial_params"]["kappa"] == 1.3
    assert fit["calculation_config"]["integration_points"] == 512
    assert fit["calculation_config"]["max_evaluations"] == 120
    assert fit["calculation_config"]["parameter_bounds"]["rho"] == {"min": -.95, "max": .95}
    json.dumps(fit, allow_nan=False)


def test_historical_scenario_requires_explicit_assumptions():
    denied = research.iv_surface(dict(mode="historical_scenario", date="2024-01-02", r=.02, q=0))
    assert denied["status"] == "error"
    denied_fit = research.heston_experiment(dict(mode="historical_scenario", date="2024-01-02", r=.02, q=0))
    assert denied_fit["status"] == "error"
    assert research.iv_surface(dict(mode="historical_scenario", date="2024-01-02", r=float("nan"), q=0,
                                    assumptions_acknowledged=True))["status"] == "error"
    assert research.pricing(dict(S=100, K=100, T=.5, r=.02, q=0, sigma=.2,
                                 tree_steps=3.5))["status"] == "error"


def test_historical_surface_counts_exclusions_and_failed_iv(monkeypatch):
    base = dict(date="2024-01-02", code="1", expiry="2024-03-27", cp="C",
                adjustment_flag="M", contract_unit=10000,
                official_strike_mismatch=False, invalid_terms=False, spot_conflict=False,
                volume=100, close=.1, spot=2.7, strike=2.7, T_act365=.23)
    rows = [base, dict(base, code="2", adjustment_flag="A", contract_unit=10161),
            dict(base, code="3", volume=0), dict(base, code="4", close=3.0)]
    provenance = {"normalized_sha256": "fixture-version", "audit_status": "complete"}
    monkeypatch.setattr(research, "snapshot", lambda *args, **kwargs: {
        "status": "ok", "total": 4, "rows": rows, "truncated": False,
        "source_summary": provenance})
    result = research.iv_surface(dict(mode="historical_scenario", date="2024-01-02", r=.02, q=0,
                                      assumptions_acknowledged=True))
    selected = result["selection_summary"]
    assert selected["source_rows"] == 4
    assert selected["eligible_rows"] == 2 and selected["excluded_rows"] == 2
    assert sum(selected["exclusion_counts"].values()) + selected["eligible_rows"] == 4
    assert selected["iv_status_counts"] == {"ok": 1, "outside_model_bounds": 1}
    assert result["point_count"] == 2 and result["source_summary"] == provenance
    json.dumps(result, allow_nan=False)
