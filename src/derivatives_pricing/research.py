"""JSON-friendly local research API. Historical calculations are labeled scenarios."""

from __future__ import annotations

from dataclasses import asdict
from math import isfinite, log
from time import perf_counter

from .black_scholes import BSInputs, greeks, price as bs_price
from .heston import HestonParams, calibrate_heston, heston_price_checked, heston_prices
from .implied_volatility import implied_volatility
from .market_data import scenario_eligible, snapshot, summary
from .numerical import binomial_price, monte_carlo_price


def _error(exc: Exception) -> dict:
    return {"status": "error", "message": str(exc)}


def _assumptions(payload: dict) -> list[str]:
    return list(payload.get("assumptions", []))


def _integer(name: str, value, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def _finite_rate(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _input(payload: dict) -> tuple[BSInputs, str]:
    inputs = BSInputs(*(_finite_rate(name, payload[name]) for name in ("S", "K", "T", "r", "sigma")),
                      _finite_rate("q", payload.get("q", 0)))
    kind = payload.get("option_type", "call")
    if kind not in ("call", "put"):
        raise ValueError("option_type must be call or put")
    return inputs, kind


def _timed(name, function):
    start = perf_counter()
    try:
        result = function()
        return {"status": "ok", "value": result, "elapsed_ms": (perf_counter()-start)*1000}
    except (ValueError, OverflowError, ArithmeticError, RuntimeError) as exc:
        return {"status": "error", "message": str(exc), "elapsed_ms": (perf_counter()-start)*1000}


def pricing(payload: dict) -> dict:
    try:
        x, kind = _input(payload)
        params = HestonParams(**payload.get("heston_params", {}))
        tree_steps = _integer("tree_steps", payload.get("tree_steps", 200), 1, 1500)
        mc_paths = _integer("mc_paths", payload.get("mc_paths", 4000), 4, 200000)
        seed = _integer("seed", payload.get("seed", 20260930), -2147483648, 2147483647)
        methods = {
            "bs": _timed("bs", lambda: bs_price(x, kind)),
            "crr": _timed("crr", lambda: binomial_price(x, kind, tree_steps)),
            "mc": _timed("mc", lambda: asdict(monte_carlo_price(x, kind, mc_paths, seed))),
            "heston": _timed("heston", lambda: heston_price_checked(x.S, x.K, x.T, x.r, x.q, params, kind)),
        }
        if methods["heston"]["status"] == "ok":
            diagnostics = methods["heston"]["value"]
            methods["heston"]["diagnostics"] = diagnostics
            methods["heston"]["value"] = diagnostics["price"]
            if diagnostics["status"] != "ok":
                methods["heston"]["status"] = diagnostics["status"]
        if x.T > 0 and x.sigma > 0:
            methods["bs"]["greeks"] = asdict(greeks(x, kind))
        result = {"status": "ok", "input_label": payload.get("input_label", "synthetic_or_user_scenario"),
                "source": payload.get("source", "user_supplied_inputs"),
                "assumptions": _assumptions(payload), "inputs": asdict(x),
                "heston_params": asdict(params), "methods": methods,
                "warnings": ["Heston defaults are illustrative; BS/CRR/MC share one GBM model."]}
        if "observed_price" in payload:
            observed = _finite_rate("observed_price", payload["observed_price"])
            iv, state = implied_volatility(observed, x.S, x.K, x.T, x.r, kind, x.q)
            model_price = bs_price(BSInputs(x.S, x.K, x.T, x.r, iv, x.q), kind) if iv is not None else None
            result["implied_volatility"] = {
                "status": state, "value": iv, "observed_price": observed,
                "roundtrip_price": model_price,
                "roundtrip_residual": model_price-observed if model_price is not None else None,
                "source": payload.get("observed_source", "user_supplied_observed_price"),
                "interpretation": "Solver round-trip check only; not predictive model performance.",
            }
        return result
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _error(exc)


def market_summary() -> dict:
    result = summary()
    result["input_label"] = "user_supplied_historical_data"
    result["assumptions"] = []
    return result


def market_snapshot(payload: dict) -> dict:
    try:
        result = snapshot(payload["date"], expiry=payload.get("expiry"), cp=payload.get("cp"),
                          min_volume=_finite_rate("min_volume", payload.get("min_volume", 0)),
                          limit=_integer("limit", payload.get("limit", 500), 1, 2000))
        result["input_label"] = "user_supplied_historical_data"
        result["assumptions"] = []
        result["warnings"] = ["Vendor IV is displayed only as source metadata, not verified truth."]
        return result
    except (KeyError, TypeError, ValueError) as exc:
        return _error(exc)


def _surface_points(payload: dict) -> tuple[list[dict], str, str, list[str], dict]:
    mode = payload.get("mode", "synthetic")
    if mode == "synthetic":
        S = _finite_rate("S", payload.get("S", 100))
        r = _finite_rate("r", payload.get("r", 0.02))
        q = _finite_rate("q", payload.get("q", 0.01))
        if S <= 0:
            raise ValueError("S must be positive")
        p = HestonParams(**payload.get("heston_params", {}))
        points = []
        for T in (0.25, 0.5, 1.0):
            strikes = [S*v for v in (0.8, 0.9, 0.95, 1, 1.05, 1.1, 1.2)]
            prices = heston_prices(S, strikes, T, r, q, p)
            for K, market in zip(strikes, prices):
                iv, state = implied_volatility(market, S, K, T, r, "call", q)
                points.append({"expiry": f"T={T:g}", "T": T, "K": K, "S": S,
                               "option_type": "call", "price": market, "iv": iv,
                               "status": state, "log_moneyness": log(K/S)})
        return points, "synthetic_known_heston_parameters", "synthetic_model_prices", ["Known Heston parameters generate the demonstration prices."], {
            "r": r, "q": q, "excluded": {}, "source_rows": len(points),
            "eligible_rows": len(points), "excluded_rows": 0,
            "source_summary": {"kind": "synthetic_model_prices", "known_params": asdict(p)},
        }
    if mode != "historical_scenario":
        raise ValueError("mode must be synthetic or historical_scenario")
    if payload.get("assumptions_acknowledged") is not True:
        raise ValueError("Historical scenario requires assumptions_acknowledged=true")
    r, q = _finite_rate("r", payload["r"]), _finite_rate("q", payload["q"])
    found = snapshot(payload["date"], expiry=payload.get("expiry"), limit=2000)
    if found["status"] != "ok":
        raise ValueError("Historical CSV is unavailable")
    if found["truncated"]:
        raise ValueError("Historical snapshot exceeds surface limit; select one expiry")
    points = []
    excluded = {}
    for row in found["rows"]:
        eligible, reason = scenario_eligible(row)
        if not eligible:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        kind = "call" if row["cp"] == "C" else "put"
        iv, state = implied_volatility(row["close"], row["spot"], row["strike"],
                                       row["T_act365"], r, kind, q)
        points.append({"date": row["date"], "code": row["code"], "expiry": row["expiry"],
                       "T": row["T_act365"], "K": row["strike"], "S": row["spot"],
                       "option_type": kind, "price": row["close"], "volume": row["volume"],
                       "iv": iv, "status": state, "log_moneyness": log(row["strike"]/row["spot"])})
    return points, "historical_prices_with_user_rate_dividend_scenario", "user_supplied_audited_2024_daily_csv", [
        f"r={r:g} and q={q:g} are user-selected assumptions, not verified historical rates or dividends.",
        "Static-strike scenario excludes adjusted contracts and contracts crossing the 2024-12-02 adjustment.",
    ], {"r": r, "q": q, "excluded": excluded, "source_rows": found["total"],
        "eligible_rows": len(points), "excluded_rows": sum(excluded.values()),
        "source_summary": found["source_summary"],
        "scope": {"date": payload["date"], "expiry": payload.get("expiry"),
                  "official_chain_completeness_verified": False}}


def iv_surface(payload: dict) -> dict:
    try:
        points, label, source, warnings, selection = _surface_points(payload)
        smiles = []
        for expiry in sorted({p["expiry"] for p in points}):
            valid = [p for p in points if p["expiry"] == expiry and p["status"] == "ok"]
            # Avoid duplicate call/put observations at one strike in the slope fit.
            by_strike = {}
            for item in valid:
                by_strike.setdefault(item["K"], []).append(item["iv"])
            pairs = [(log(k/valid[0]["S"]), sum(v)/len(v)) for k, v in by_strike.items()] if valid else []
            n = len(pairs)
            xbar = sum(x for x, _ in pairs)/n if n else 0
            ybar = sum(y for _, y in pairs)/n if n else 0
            denominator = sum((x-xbar)**2 for x, _ in pairs)
            slope = sum((x-xbar)*(y-ybar) for x, y in pairs)/denominator if n >= 3 and denominator else None
            smiles.append({"expiry": expiry, "valid_strikes": n, "skew_slope_iv_per_log_moneyness": slope,
                           "atm_iv_nearest": min(valid, key=lambda p: abs(p["log_moneyness"]))["iv"] if valid else None})
        status_counts = {}
        for point in points:
            state = point["status"]
            status_counts[state] = status_counts.get(state, 0) + 1
        return {"status": "ok", "input_label": label, "source": source,
                "source_summary": selection["source_summary"],
                "assumptions": _assumptions(payload), "warnings": warnings,
                "scenario_inputs": {key: value for key, value in selection.items()
                                    if key != "source_summary"},
                "selection_summary": {"source_rows": selection["source_rows"],
                                      "eligible_rows": selection["eligible_rows"],
                                      "excluded_rows": selection["excluded_rows"],
                                      "exclusion_counts": selection["excluded"],
                                      "iv_status_counts": status_counts,
                                      "scope": selection.get("scope", {"mode": "synthetic"})},
                "points": points, "smiles": smiles,
                "point_count": len(points)}
    except (KeyError, TypeError, ValueError, ArithmeticError, RuntimeError) as exc:
        return _error(exc)


def heston_experiment(payload: dict) -> dict:
    try:
        mode = payload.get("mode", "synthetic")
        max_evals = _integer("max_evaluations", payload.get("max_evaluations", 120), 12, 2000)
        if mode == "synthetic":
            S, r, q = 100.0, 0.02, 0.01
            truth = HestonParams(**payload.get("known_params", {}))
            quotes = []
            for T in (0.25, 0.5, 1.0):
                strikes = [S*v for v in (0.85, 0.925, 1.0, 1.075, 1.15)]
                values = heston_prices(S, strikes, T, r, q, truth, integration_points=512)
                quotes.extend({"K": K, "T": T, "price": value, "option_type": "call"}
                              for K, value in zip(strikes, values))
            holdout_quotes = []
            for T in (.375, .75, 1.25):
                strikes = [88.0, 100.0, 112.0]
                values = heston_prices(S, strikes, T, r, q, truth, integration_points=512)
                holdout_quotes.extend({"K": K, "T": T, "price": value, "option_type": "call"}
                                      for K, value in zip(strikes, values))
            label, source = "synthetic_known_heston_parameters", "synthetic_model_prices"
            provenance = {"kind": "synthetic_model_prices", "known_params": asdict(truth)}
        elif mode == "historical_scenario":
            if payload.get("assumptions_acknowledged") is not True:
                raise ValueError("Historical scenario requires assumptions_acknowledged=true")
            r, q = _finite_rate("r", payload["r"]), _finite_rate("q", payload["q"])
            found = snapshot(payload["date"], cp="C", limit=2000)
            if found["status"] != "ok":
                raise ValueError("Historical CSV is unavailable")
            if found["truncated"]:
                raise ValueError("Historical snapshot exceeds calibration limit")
            provenance = found["source_summary"]
            eligible = [row for row in found["rows"] if scenario_eligible(row)[0]]
            if not eligible:
                raise ValueError("No eligible unaffected standard contracts on date")
            S = eligible[0]["spot"]
            quotes = []
            holdout_quotes = []
            for expiry in sorted({row["expiry"] for row in eligible})[:3]:
                group = [row for row in eligible if row["expiry"] == expiry]
                group.sort(key=lambda row: abs(log(row["strike"]/S)))
                quotes.extend({"K": row["strike"], "T": row["T_act365"],
                               "price": row["close"], "option_type": "call"}
                              for row in group[:5])
                holdout_quotes.extend({"K": row["strike"], "T": row["T_act365"],
                                       "price": row["close"], "option_type": "call"}
                                      for row in group[5:7])
            label, source = "historical_prices_with_user_rate_dividend_scenario", "user_supplied_audited_2024_daily_csv"
            truth = None
        else:
            raise ValueError("mode must be synthetic or historical_scenario")
        initial = (HestonParams(**payload["initial_params"])
                   if "initial_params" in payload else None)
        fit = calibrate_heston(quotes, S, r, q,
                               initial=initial,
                               max_evaluations=max_evals, integration_points=512)
        fitted_params = HestonParams(**fit["params"])
        holdout = []
        for item in holdout_quotes:
            try:
                checked = heston_price_checked(S, item["K"], item["T"], r, q,
                                               fitted_params, item["option_type"])
            except (ArithmeticError, ValueError, OverflowError) as exc:
                checked = {"price": None, "status": "pricing_error",
                           "quadrature_difference": None, "message": str(exc)}
            holdout.append({**item, "fitted_price": checked["price"],
                            "pricing_status": checked["status"],
                            "quadrature_difference": checked["quadrature_difference"]})
        valid_holdout = [item for item in holdout if item["fitted_price"] is not None]
        holdout_rmse = ((sum((item["fitted_price"]-item["price"])**2
                             for item in valid_holdout)/len(valid_holdout))**.5
                        if valid_holdout else None)
        result = {"status": "ok", "input_label": label, "source": source,
                  "source_summary": provenance,
                  "assumptions": _assumptions(payload), "quotes": quotes,
                  "scenario_inputs": {"S": S, "r": r, "q": q,
                                      "date": payload.get("date") if mode == "historical_scenario" else None},
                  "fit": fit, "known_params": asdict(truth) if truth else None,
                  "initial_params": fit["initial_params"],
                  "calculation_config": {
                      **fit["calculation_config"],
                      "synthetic_generation_integration_points": 512 if mode == "synthetic" else None,
                      "synthetic_generation_integration_upper": 160.0 if mode == "synthetic" else None,
                      "holdout_pricing": {"coarse_points": 1024, "coarse_upper": 160.0,
                                          "refined_points": 4096, "refined_upper": 320.0,
                                          "tolerance": 1e-5},
                  },
                  "training_count": len(quotes), "holdout_quotes": holdout,
                  "holdout_count": len(valid_holdout), "holdout_rmse": holdout_rmse,
                  "holdout_scope": "different_synthetic_strikes_and_tenors" if mode == "synthetic"
                                   else "same_day_cross_section_only_not_out_of_time",
                  "warnings": [fit["warning"],
                               "Calibration error is in-sample; it does not establish model superiority."]}
        if mode == "historical_scenario":
            result["warnings"].append("Historical r/q are user assumptions; daily closes are not synchronized executable quotes.")
        return result
    except (KeyError, TypeError, ValueError, ArithmeticError, RuntimeError, OverflowError) as exc:
        return _error(exc)


def comparison(payload: dict) -> dict:
    result = pricing(payload)
    if result["status"] != "ok":
        return result
    if result["methods"]["bs"]["status"] != "ok":
        return _error(ValueError("BS reference price is unavailable"))
    reference = payload.get("reference", "bs")
    if reference == "bs":
        reference_price = result["methods"]["bs"]["value"]
        result["reference"] = {"type": "bs_same_model", "price": reference_price}
        result["warnings"].append("CRR/MC errors versus BS are numerical errors; Heston difference is a model difference, not a ranking.")
    elif reference == "market":
        try:
            reference_price = _finite_rate("market_price", payload["market_price"])
            if reference_price <= 0 or not payload.get("market_source"):
                raise ValueError("Positive market_price and market_source are required")
        except (KeyError, TypeError, ValueError) as exc:
            return _error(exc)
        result["reference"] = {"type": "independent_market_observation", "price": reference_price,
                               "source": payload["market_source"]}
        result["warnings"].append("One in-sample market price does not establish out-of-sample model superiority.")
    else:
        return _error(ValueError("reference must be bs or market"))
    for name, item in result["methods"].items():
        if item["status"] == "ok":
            number = item["value"]["price"] if name == "mc" else item["value"]
            item["absolute_error_to_reference"] = abs(number-reference_price)
    return result


def convergence(payload: dict) -> dict:
    from .experiments import convergence as experiment
    return experiment(payload)


def risk_profile(payload: dict) -> dict:
    from .experiments import risk_profile as experiment
    return experiment(payload)


def model_comparison(payload: dict) -> dict:
    from .experiments import model_comparison as experiment
    return experiment(payload)


def heston_diagnostics(payload: dict) -> dict:
    from .experiments import heston_diagnostics as experiment
    return experiment(payload)
