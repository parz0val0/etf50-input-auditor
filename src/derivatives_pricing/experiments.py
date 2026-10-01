"""Reproducible numerical and held-out option-pricing experiments.

Fitting functions only receive training quotes. Missing predictions retain a
status and null; no metric treats a failed numerical calculation as a zero.
"""

from __future__ import annotations

from dataclasses import asdict
from functools import wraps
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from math import exp, isfinite, log, sqrt
from pathlib import Path
from platform import python_version
from time import perf_counter

from .black_scholes import BSInputs, greeks, parity_gap, price
from .heston import HestonParams, calibrate_heston, heston_price_checked
from .implied_volatility import implied_volatility
from .market_data import scenario_eligible, snapshot
from .numerical import binomial_price, monte_carlo_price

METHODS = ("bs_constant", "iv_interpolation", "heston", "mc")
STARTS = (
    HestonParams(1.3, .055, .42, -.25, .055),
    HestonParams(.5, .025, .20, -.70, .025),
    HestonParams(4.0, .08, .80, -.10, .08),
)


def _api(function):
    @wraps(function)
    def run(payload):
        try:
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            return function(payload)
        except (KeyError, ValueError, TypeError, ArithmeticError, RuntimeError, OSError) as exc:
            return {"status": "error", "operation": function.__name__, "message": str(exc)}
    return run


def _number(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _integer(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def _inputs(payload):
    defaults = {"S": 100, "K": 100, "T": .5, "r": .02, "q": .01, "sigma": .2}
    x = BSInputs(**{key: _number(key, payload.get(key, value)) for key, value in defaults.items()})
    kind = payload.get("option_type", "call")
    if kind not in ("call", "put"):
        raise ValueError("option_type must be call or put")
    return x, kind


def _sequence(name, values, low, high, even=False):
    if not isinstance(values, list) or not 1 <= len(values) <= 10:
        raise ValueError(f"{name} must contain 1 to 10 integers")
    values = [_integer(name, v, low, high) for v in values]
    if len(set(values)) != len(values) or (even and any(v % 2 for v in values)):
        raise ValueError(f"{name} must be unique" + (" even integers" if even else " integers"))
    return values


def _base(operation, label="synthetic_or_user_scenario", source="user_supplied_inputs"):
    folder = Path(__file__).parent
    try:
        numpy_version = version("numpy")
    except PackageNotFoundError:
        numpy_version = None
    return {"status": "ok", "operation": operation, "input_label": label,
            "source": source, "assumptions": [], "warnings": [], "schema_version": 1,
            "reproducibility": {"python_version": python_version(), "numpy_version": numpy_version,
                                "code_sha256": {name: sha256((folder/name).read_bytes()).hexdigest()
                                                for name in ("experiments.py", "heston.py", "black_scholes.py", "numerical.py",
                                                             "implied_volatility.py", "market_data.py")}}}


@_api
def convergence(payload):
    x, kind = _inputs(payload)
    steps = _sequence("tree_steps", payload.get("tree_steps", [25, 50, 100, 200, 400]), 1, 1500)
    paths = _sequence("mc_paths", payload.get("mc_paths", [1000, 4000, 16000]), 4, 200000, True)
    seeds = _sequence("seeds", payload.get("seeds", [11, 29, 47, 71, 101]), -2147483648, 2147483647)
    if sum(n*n for n in steps) > 4000000 or sum(paths)*len(seeds) > 2000000:
        raise ValueError("Convergence budget exceeds interactive limit")
    reference = price(x, kind)
    crr = []
    for n in steps:
        start = perf_counter()
        try:
            value = binomial_price(x, kind, n)
            row = {"steps": n, "status": "ok", "price": value,
                   "error": value-reference, "absolute_error": abs(value-reference)}
        except (ValueError, ArithmeticError) as exc:
            row = {"steps": n, "status": "failed", "price": None, "error": None,
                   "absolute_error": None, "message": str(exc)}
        row["elapsed_ms"] = (perf_counter()-start)*1000
        crr.append(row)
    mc = []
    for n in paths:
        repeats = []
        for seed in seeds:
            start = perf_counter()
            try:
                result = asdict(monte_carlo_price(x, kind, n, seed))
                result.update(status="ok", error=result["price"]-reference,
                              absolute_error=abs(result["price"]-reference))
            except (ValueError, ArithmeticError) as exc:
                result = {"status": "failed", "seed": seed, "paths": n, "price": None,
                          "error": None, "standard_error": None, "ci_lower": None,
                          "ci_upper": None, "message": str(exc)}
            result["elapsed_ms"] = (perf_counter()-start)*1000
            repeats.append(result)
        good = [row for row in repeats if row["status"] == "ok"]
        mc.append({"paths": n, "repetitions": repeats,
                   "effective_count": len(good), "failed_count": len(repeats)-len(good),
                   "rmse": sqrt(sum(row["error"]**2 for row in good)/len(good)) if good else None,
                   "mae": sum(abs(row["error"]) for row in good)/len(good) if good else None,
                   "mean_price": sum(row["price"] for row in good)/len(good) if good else None,
                   "elapsed_ms": sum(row["elapsed_ms"] for row in repeats)})
    out = _base("convergence")
    out.update(inputs={**asdict(x), "option_type": kind}, reference_price=reference, crr=crr, mc=mc,
               config={"tree_steps": steps, "mc_paths": paths, "seeds": seeds,
                       "sampling": "antithetic_terminal_GBM", "ci": "approximate_95_percent_normal"},
               units={"price": "currency_per_underlying_unit", "sigma": "annual_decimal", "T": "years"})
    out["warnings"] = [
        "CRR and MC are numerical methods for the same GBM model; error versus BS is not market-model error.",
        "CRR error can oscillate; MC RMSE is expected to scale approximately as N^(-1/2), not monotonically in one sample.",
        "Same seeds reuse simulation prefixes across budgets; elapsed time is a single local measurement, not a stable ranking.",
    ]
    return out


def _bounds(S, K, T, r, q):
    a, b = S*exp(-q*T), K*exp(-r*T)
    return {"call_lower": max(a-b, 0), "call_upper": a,
            "put_lower": max(b-a, 0), "put_upper": b}


@_api
def risk_profile(payload):
    x, kind = _inputs(payload)
    low = _number("spot_min", payload.get("spot_min", .6*x.S))
    high = _number("spot_max", payload.get("spot_max", 1.4*x.S))
    count = _integer("points", payload.get("points", 41), 3, 121)
    unit = _integer("contract_unit", payload.get("contract_unit", 1), 1, 1000000)
    if not 0 <= low < high:
        raise ValueError("Require 0 <= spot_min < spot_max")
    rows = []
    for i in range(count):
        S = low+(high-low)*i/(count-1)
        item = BSInputs(S, x.K, x.T, x.r, x.sigma, x.q) if S > 0 else None
        call, put = (price(item, "call"), price(item, "put")) if item else (0.0, x.K*exp(-x.r*x.T))
        selected = call if kind == "call" else put
        bounds = _bounds(S, x.K, x.T, x.r, x.q)
        tol = 1e-10*max(S, x.K, 1)
        gap = parity_gap(call, put, item) if item else call-put+x.K*exp(-x.r*x.T)
        sensitivity = asdict(greeks(item, kind)) if item and x.T > 0 and x.sigma > 0 else None
        payoff = max(S-x.K, 0) if kind == "call" else max(x.K-S, 0)
        rows.append({"S": S, "price": selected, "call_price": call, "put_price": put,
                     "price_per_contract": selected*unit, "payoff": payoff,
                     "payoff_per_contract": payoff*unit, "greeks": sensitivity,
                     "greeks_per_contract": {k: v*unit for k, v in sensitivity.items()} if sensitivity else None,
                     "greeks_display": {"vega_per_vol_percentage_point": sensitivity["vega"]*.01,
                                        "rho_per_rate_percentage_point": sensitivity["rho"]*.01,
                                        "theta_per_calendar_day": sensitivity["theta"]/365} if sensitivity else None,
                     "greeks_status": "ok" if sensitivity else "undefined_at_expiry_zero_volatility_or_zero_spot",
                     "parity_gap": gap, "parity_ok": abs(gap) <= tol,
                     "bounds": bounds, "bounds_ok": bounds["call_lower"]-tol <= call <= bounds["call_upper"]+tol
                     and bounds["put_lower"]-tol <= put <= bounds["put_upper"]+tol})
    out = _base("risk_profile")
    out.update(inputs={**asdict(x), "option_type": kind}, rows=rows,
               config={"spot_min": low, "spot_max": high, "points": count, "contract_unit": unit},
               units={"price": "currency_per_underlying_unit", "payoff": "gross_currency_per_underlying_unit",
                      "r_q": "continuous_annual_decimal", "sigma": "annual_decimal", "T": "ACT365_years",
                      "delta": "price_change_per_one_spot_unit", "gamma": "delta_change_per_one_spot_unit",
                      "vega": "price_change_per_1_0_annual_volatility", "theta": "price_decay_per_year",
                      "rho": "price_change_per_1_0_annual_rate", "per_contract": "per_unit_value_times_contract_unit"},
               parity_formula="C-P=S*exp(-q*T)-K*exp(-r*T)")
    out["warnings"] = ["Payoff is gross at expiry, before premium and costs; theta is annual and vega/rho use a 1.0 rate change.",
                       "Greeks at expiry, zero volatility or the explicit zero-spot boundary are deliberately left null."]
    return out


def _make_quote(identifier, K, T, observed, kind, expiry=None):
    return {"id": identifier, "K": float(K), "T": float(T), "price": float(observed),
            "option_type": kind, "expiry": expiry or f"T={T:g}"}


def _dataset(payload):
    mode = payload.get("mode", "synthetic")
    kind = payload.get("option_type", "call")
    if kind not in ("call", "put"):
        raise ValueError("option_type must be call or put")
    if mode == "synthetic":
        S = _number("S", payload.get("S", 100))
        r, q = _number("r", payload.get("r", .02)), _number("q", payload.get("q", .01))
        if S <= 0:
            raise ValueError("S must be positive")
        truth = HestonParams(**payload.get("known_params", {}))
        subsets = {"training": ((.25, .5, 1.0), (.85, .925, 1, 1.075, 1.15)),
                   "holdout": ((.25, .375, .5, .75, 1.0), (.89, .965, 1.035, 1.11))}
        train, holdout = [], []
        for subset, (tenors, ratios) in subsets.items():
            for T in tenors:
                for ratio in ratios:
                    K = S*ratio
                    check = heston_price_checked(S, K, T, r, q, truth, kind)
                    if check["status"] != "ok" or check["price"] is None:
                        raise ArithmeticError("Synthetic Heston price did not pass quadrature refinement")
                    item = _make_quote(f"synthetic-{subset}-{T:g}-{ratio:g}", K, T, check["price"], kind)
                    (train if subset == "training" else holdout).append(item)
        return {"S": S, "r": r, "q": q, "train": train, "holdout": holdout,
                "label": "synthetic_known_heston_parameters", "source": "synthetic_model_prices",
                "source_summary": {"kind": "synthetic_model_prices", "known_params": asdict(truth)},
                "selection_summary": {"source_rows": len(train)+len(holdout), "eligible_rows": len(train)+len(holdout),
                                      "experiment_rows": len(train)+len(holdout), "exclusion_counts": {}},
                "split_rule": "fixed_disjoint_strike_tenor_grids", "scope": "synthetic_held_out_strikes_and_tenors"}
    if mode != "historical_scenario" or payload.get("assumptions_acknowledged") is not True:
        raise ValueError("Historical mode requires mode=historical_scenario and assumptions_acknowledged=true")
    r, q = _number("r", payload["r"]), _number("q", payload["q"])
    found = snapshot(payload["date"], cp="C" if kind == "call" else "P", limit=2000)
    if found["status"] != "ok" or found.get("truncated"):
        raise ValueError("Historical audited snapshot unavailable or truncated")
    eligible, exclusions = [], {}
    for row in found["rows"]:
        ok, reason = scenario_eligible(row)
        if ok:
            eligible.append(row)
        else:
            exclusions[reason] = exclusions.get(reason, 0)+1
    if not eligible:
        raise ValueError("No eligible standard historical contracts on this date")
    S = eligible[0]["spot"]
    if any(abs(row["spot"]-S) > 1e-10 for row in eligible):
        raise ValueError("Historical quote slice has conflicting ETF prices")
    selected = []
    tenors = sorted({row["expiry"] for row in eligible})[:4]
    for expiry in tenors:
        group = [row for row in eligible if row["expiry"] == expiry]
        group.sort(key=lambda row: (abs(log(row["strike"]/S)), row["code"]))
        selected.extend(group[:13])
    train, holdout = [], []
    for expiry in tenors:
        group = sorted((row for row in selected if row["expiry"] == expiry), key=lambda row: row["strike"])
        for i, row in enumerate(group):
            item = _make_quote(row["code"], row["strike"], row["T_act365"], row["close"], kind, expiry)
            item["source_file"], item["source_row"] = row.get("source_file"), row.get("source_row")
            target = holdout if i % 3 == 1 and 0 < i < len(group)-1 else train
            target.append(item)
    if len(train) < 5 or not holdout:
        raise ValueError("Selected slice needs at least five training quotes and one holdout")
    return {"S": S, "r": r, "q": q, "date": payload["date"], "train": train, "holdout": holdout,
            "label": "historical_prices_with_user_rate_dividend_scenario",
            "source": "user_supplied_audited_2024_daily_csv", "source_summary": found["source_summary"],
            "selection_summary": {"source_rows": found["total"], "eligible_rows": len(eligible),
                                  "excluded_rows": sum(exclusions.values()), "exclusion_counts": exclusions,
                                  "experiment_rows": len(selected), "eligible_not_selected": len(eligible)-len(selected),
                                  "selection_rule": "first_four_expiries_and_thirteen_strikes_nearest_spot_each",
                                  "option_type": kind, "date": payload["date"],
                                  "official_chain_completeness_verified": False},
            "split_rule": "each_expiry_sorted_strikes_interior_index_mod3_eq1_held_out",
            "scope": "same_day_cross_section_not_out_of_time"}


def _fit_bs(train, S, r, q):
    # One bounded price-space parameter, fitted independently of IV estimates.
    low, high = .0001, 3.0
    ratio = (sqrt(5)-1)/2
    def objective(sigma):
        return sum((price(BSInputs(S, row["K"], row["T"], r, sigma, q), row["option_type"])-row["price"])**2 for row in train)
    a, b = low, high
    c, d = b-ratio*(b-a), a+ratio*(b-a)
    fc, fd = objective(c), objective(d)
    evaluations = 2
    for _ in range(70):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b-ratio*(b-a)
            fc = objective(c)
        else:
            a, c, fc = c, d, fd
            d = a+ratio*(b-a)
            fd = objective(d)
        evaluations += 1
        if b-a < 1e-8:
            break
    sigma = (a+b)/2
    return {"sigma": sigma, "status": "bounded_scalar_search", "evaluations": evaluations,
            "bounds": [low, high], "objective": "unweighted_training_price_squared_error",
            "at_boundary": min(sigma-low, high-sigma) < 1e-5}


class _IVInterpolation:
    """Training-only piecewise linear total variance; no strike/tenor extrapolation."""
    def __init__(self, train, S, r, q):
        self.S, self.r, self.q = S, r, q
        self.slices, self.states = {}, {}
        for row in train:
            iv, state = implied_volatility(row["price"], S, row["K"], row["T"], r, row["option_type"], q)
            self.states[state] = self.states.get(state, 0)+1
            if state == "ok":
                x = log(row["K"]/S)-(r-q)*row["T"]
                self.slices.setdefault(row["T"], []).append((x, iv*iv*row["T"]))
        for knots in self.slices.values():
            knots.sort()

    @staticmethod
    def _linear(knots, x):
        if not knots or x < knots[0][0]-1e-12 or x > knots[-1][0]+1e-12:
            return None
        for at, value in knots:
            if abs(at-x) <= 1e-12:
                return value
        for (a, va), (b, vb) in zip(knots, knots[1:]):
            if a < x < b:
                return va+(vb-va)*(x-a)/(b-a)
        return None

    def predict(self, row):
        T = row["T"]
        x = log(row["K"]/self.S)-(self.r-self.q)*T
        tenors = sorted(self.slices)
        if not tenors:
            return None, "no_valid_training_iv"
        if T < tenors[0]-1e-12 or T > tenors[-1]+1e-12:
            return None, "outside_training_maturities"
        if T in self.slices:
            variance = self._linear(self.slices[T], x)
        else:
            bracket = next(((a, b) for a, b in zip(tenors, tenors[1:]) if a < T < b), None)
            if bracket is None:
                return None, "outside_training_maturities"
            a, b = bracket
            va, vb = self._linear(self.slices[a], x), self._linear(self.slices[b], x)
            variance = va+(vb-va)*(T-a)/(b-a) if va is not None and vb is not None else None
        if variance is None:
            return None, "outside_training_strikes"
        sigma = sqrt(max(variance/T, 0))
        return price(BSInputs(self.S, row["K"], T, self.r, sigma, self.q), row["option_type"]), "ok"


def _metrics(rows, method):
    good = [row["predictions"][method] for row in rows if row["predictions"][method]["status"] == "ok"]
    failures = {}
    for row in rows:
        state = row["predictions"][method]["status"]
        if state != "ok":
            failures[state] = failures.get(state, 0)+1
    errors = [item["residual"] for item in good]
    return {"total_count": len(rows), "effective_count": len(good), "failed_count": len(rows)-len(good),
            "rmse": sqrt(sum(error*error for error in errors)/len(errors)) if errors else None,
            "mae": sum(abs(error) for error in errors)/len(errors) if errors else None,
            "failure_status_counts": failures}


def _prediction(function, observed):
    start = perf_counter()
    try:
        value = function()
        if not isinstance(value, dict):
            value = {"price": value, "status": "ok"}
        else:
            value = dict(value)
        if value.get("price") is None and value.get("status") == "ok":
            value["status"] = "missing_prediction"
        elif value.get("price") is not None and not isfinite(value["price"]):
            value.update(price=None, status="nonfinite_prediction")
        value["residual"] = value["price"]-observed if value.get("price") is not None else None
    except (ValueError, TypeError, ArithmeticError, RuntimeError) as exc:
        value = {"price": None, "residual": None, "status": "pricing_failed", "message": str(exc)}
    value["elapsed_ms"] = (perf_counter()-start)*1000
    return value


def _heston_run(dataset, initial, budget):
    start = perf_counter()
    try:
        fit = calibrate_heston(dataset["train"], dataset["S"], dataset["r"], dataset["q"],
                               initial=initial, max_evaluations=budget, integration_points=512)
        fit_ms = (perf_counter()-start)*1000
        params = HestonParams(**fit["params"])
        predictions = {}
        for row in dataset["train"]+dataset["holdout"]:
            predictions[row["id"]] = _prediction(lambda row=row: heston_price_checked(
                dataset["S"], row["K"], row["T"], dataset["r"], dataset["q"], params, row["option_type"]), row["price"])
        return fit, predictions, fit_ms
    except (ValueError, TypeError, ArithmeticError, RuntimeError) as exc:
        fit = {"status": "calibration_failed", "message": str(exc), "params": None,
               "initial_params": asdict(initial), "rmse": None,
               "calculation_config": {"max_evaluations": budget, "integration_points": 512}}
        predictions = {row["id"]: {"status": "calibration_failed", "price": None, "residual": None,
                                    "elapsed_ms": 0.0} for row in dataset["train"]+dataset["holdout"]}
        return fit, predictions, (perf_counter()-start)*1000


def _bucket(row, S, r, q):
    m = log(row["K"]/S)-(r-q)*row["T"]
    money = "K_below_forward" if m < -.05 else "K_above_forward" if m > .05 else "near_forward"
    tenor = "up_to_0.25y" if row["T"] <= .25 else "0.25_to_0.75y" if row["T"] <= .75 else "above_0.75y"
    return m, money, tenor


def _compare_dataset(dataset, mc_paths=2000, seed=20260930, budget=120):
    """Internal testable comparison. Holdout prices enter scoring only."""
    S, r, q = dataset["S"], dataset["r"], dataset["q"]
    start = perf_counter()
    bs_fit = _fit_bs(dataset["train"], S, r, q)
    bs_ms = (perf_counter()-start)*1000
    start = perf_counter()
    interpolator = _IVInterpolation(dataset["train"], S, r, q)
    interp_ms = (perf_counter()-start)*1000
    heston_fit, heston_predictions, heston_ms = _heston_run(dataset, STARTS[0], budget)
    rows = []
    for subset, quotes in (("training", dataset["train"]), ("holdout", dataset["holdout"])):
        for quote in quotes:
            index = len(rows)
            inputs = BSInputs(S, quote["K"], quote["T"], r, bs_fit["sigma"], q)
            def interpolate(row=quote):
                value, state = interpolator.predict(row)
                return {"price": value, "status": state}
            def simulate(x=inputs, row=quote, i=index):
                mc = asdict(monte_carlo_price(x, row["option_type"], mc_paths, seed+i))
                mc["status"] = "ok"
                return mc
            predictions = {
                "bs_constant": _prediction(lambda: price(inputs, quote["option_type"]), quote["price"]),
                "iv_interpolation": _prediction(interpolate, quote["price"]),
                "heston": heston_predictions[quote["id"]],
                "mc": _prediction(simulate, quote["price"]),
            }
            predictions["heston"]["fit_status"] = heston_fit["status"]
            m, money, tenor = _bucket(quote, S, r, q)
            rows.append({**quote, "observed_price": quote["price"], "split": subset, "S": S,
                         "log_forward_moneyness": m, "moneyness_bucket": money,
                         "maturity_bucket": tenor, "predictions": predictions})
    method_info = {
        "bs_constant": {"fit": bs_fit, "fit_elapsed_ms": bs_ms},
        "iv_interpolation": {"fit": {"status": "training_iv_only", "training_iv_status_counts": interpolator.states,
                                     "knot_count": sum(len(v) for v in interpolator.slices.values()),
                                     "rule": "linear_total_variance_in_log_forward_moneyness_then_maturity_no_extrapolation"},
                             "fit_elapsed_ms": interp_ms},
        "heston": {"fit": heston_fit, "fit_elapsed_ms": heston_ms},
        "mc": {"config": {"paths": mc_paths, "base_seed": seed, "seed_rule": "base_seed_plus_fixed_quote_index",
                           "sigma": bs_fit["sigma"], "sigma_source": "same_training_bs_constant"}, "fit_elapsed_ms": 0.0},
    }
    for method, info in method_info.items():
        info["metrics"] = {subset: _metrics([row for row in rows if row["split"] == subset], method)
                           for subset in ("training", "holdout")}
        info["predict_elapsed_ms"] = sum(row["predictions"][method]["elapsed_ms"] for row in rows)
        info["total_elapsed_ms"] = info["fit_elapsed_ms"]+info["predict_elapsed_ms"]
        info["groups"] = {}
        for dimension in ("moneyness_bucket", "maturity_bucket"):
            info["groups"][dimension] = [{"split": subset, "bucket": group,
                                         **_metrics([row for row in rows if row["split"] == subset and row[dimension] == group], method)}
                                        for subset in ("training", "holdout")
                                        for group in sorted({row[dimension] for row in rows})]
    common = [row for row in rows if row["split"] == "holdout"
              and all(row["predictions"][method]["status"] == "ok" for method in METHODS)]
    return {"rows": rows, "methods": method_info,
            "common_valid_holdout": {"count": len(common), "ids": [row["id"] for row in common],
                                     "methods": {method: _metrics(common, method) for method in METHODS}}}


def _diagnostics(dataset, budget):
    runs = []
    for i, initial in enumerate(STARTS):
        fit, predictions, elapsed = _heston_run(dataset, initial, budget)
        rows = [{**row, "split": subset, "predictions": {"heston": predictions[row["id"]]}}
                for subset, quotes in (("training", dataset["train"]), ("holdout", dataset["holdout"])) for row in quotes]
        runs.append({"start_id": i+1, "initial_params": asdict(initial), "fit": fit,
                     "metrics": {subset: _metrics([row for row in rows if row["split"] == subset], "heston")
                                 for subset in ("training", "holdout")},
                     "elapsed_ms": elapsed+sum(item["elapsed_ms"] for item in predictions.values()),
                     "max_evaluations": budget})
    return {"runs": runs, "selection_rule": "fixed_first_start_used_by_primary_comparison",
            "selected_start_id": 1, "holdout_used_for_selection": False}


def _dataset_metadata(operation, dataset):
    out = _base(operation, dataset["label"], dataset["source"])
    out.update(source_summary=dataset["source_summary"], selection_summary=dataset["selection_summary"],
               scenario_inputs={"S": dataset["S"], "r": dataset["r"], "q": dataset["q"], "date": dataset.get("date")},
               split={"rule": dataset["split_rule"], "scope": dataset["scope"],
                      "training_count": len(dataset["train"]), "holdout_count": len(dataset["holdout"]),
                      "training_ids": [row["id"] for row in dataset["train"]],
                      "holdout_ids": [row["id"] for row in dataset["holdout"]]})
    out["warnings"] = ["All fitting and IV knots use training prices only. Missing predictions are excluded from error metrics and counted as failures.",
                       "IV-interpolation training error is a reconstruction check; held-out error is the prediction test.",
                       "MC uses the fitted constant-BS sigma; its confidence interval describes simulation uncertainty, not model fit uncertainty.",
                       "Timing is a single local measurement; parameter fits are not a proof of identifiability or global optimum."]
    if dataset.get("date"):
        out["warnings"].append("Historical r/q are assumptions and validation is same-day cross-sectional, not out-of-time.")
    else:
        out["warnings"].append("Synthetic Heston truth validates the workflow under its generating model; it is not evidence of market superiority.")
    return out


@_api
def model_comparison(payload):
    paths = _integer("mc_paths", payload.get("mc_paths", 2000), 4, 40000)
    if paths % 2:
        raise ValueError("mc_paths must be even")
    seed = _integer("seed", payload.get("seed", 20260930), -2147483648, 2147483647)
    budget = _integer("max_evaluations", payload.get("max_evaluations", 120), 12, 400)
    if not isinstance(payload.get("heston_diagnostics", False), bool):
        raise ValueError("heston_diagnostics must be boolean")
    dataset = _dataset(payload)
    if paths*(len(dataset["train"])+len(dataset["holdout"])) > 1000000:
        raise ValueError("Model-comparison simulation budget exceeds interactive limit")
    out = _dataset_metadata("model_comparison", dataset)
    out.update(_compare_dataset(dataset, paths, seed, budget))
    out["config"] = {"mc_paths": paths, "seed": seed, "max_evaluations": budget,
                     "primary_heston_initial_params": asdict(STARTS[0]), "fit_uses_holdout": False}
    out["group_definitions"] = {"moneyness": "log(K/forward): below -0.05, [-0.05,0.05], above 0.05",
                                "maturity": "T<=0.25, 0.25<T<=0.75, T>0.75 years"}
    if payload.get("heston_diagnostics", False) is True:
        out["heston_diagnostics"] = _diagnostics(dataset, budget)
    return out


@_api
def heston_diagnostics(payload):
    dataset = _dataset(payload)
    budget = _integer("max_evaluations", payload.get("max_evaluations", 120), 12, 400)
    out = _dataset_metadata("heston_diagnostics", dataset)
    out.update(_diagnostics(dataset, budget))
    return out
