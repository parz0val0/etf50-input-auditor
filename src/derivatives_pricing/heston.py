"""European Heston prices and a reproducible, bounded calibration baseline.

NumPy is optional for the package as a whole, but required by this module's
Fourier quadrature. Prices are per underlying unit, not per option contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, isfinite, sqrt
from typing import Sequence

from .black_scholes import BSInputs, price as bs_price

try:
    import numpy as np
except ImportError:  # optional research dependency
    np = None


@dataclass(frozen=True)
class HestonParams:
    kappa: float = 2.0
    theta: float = 0.04
    xi: float = 0.30
    rho: float = -0.50
    v0: float = 0.04

    def __post_init__(self):
        values = asdict(self)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
               for v in values.values()):
            raise ValueError("Heston parameters must be finite real numbers")
        if self.kappa <= 0 or self.theta < 0 or self.xi < 0 or self.v0 < 0 or abs(self.rho) >= 1:
            raise ValueError("Require kappa>0, theta/v0/xi>=0, and -1<rho<1")

    @property
    def feller_ratio(self) -> float | None:
        return 2 * self.kappa * self.theta / self.xi**2 if self.xi else None


def _cf(u, S: float, T: float, r: float, q: float, p: HestonParams):
    """Stable branch of the Heston log-spot characteristic function."""
    iu = 1j * u
    beta = p.kappa - p.rho * p.xi * iu
    d = np.sqrt(beta * beta + p.xi**2 * (u * u + iu))
    # Keep the square-root branch with nonnegative real part.
    d = np.where(np.real(d) < 0, -d, d)
    g = (beta - d) / (beta + d)
    decay = np.exp(-d * T)
    ratio = (1 - g * decay) / (1 - g)
    c = (iu * (np.log(S) + (r - q) * T)
         + p.kappa * p.theta / p.xi**2 * ((beta - d) * T - 2 * np.log(ratio)))
    dterm = (beta - d) / p.xi**2 * (1 - decay) / (1 - g * decay) * p.v0
    return np.exp(c + dterm)


def heston_prices(S: float, strikes: Sequence[float], T: float, r: float, q: float,
                  params: HestonParams, option_types: Sequence[str] | None = None,
                  *, integration_points: int = 1024,
                  integration_upper: float = 160.0) -> list[float]:
    """Price a strike slice using Heston P1/P2 Fourier integrals.

    Integration uses composite Simpson on (0, integration_upper]. Deep tails and extremely
    short maturities can remain inaccurate; boundary failure raises instead of
    silently making a plausible-looking price.
    """
    if np is None:
        raise RuntimeError("NumPy is required for Heston Fourier integration")
    if not isinstance(params, HestonParams):
        raise TypeError("params must be HestonParams")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x)
           for x in (S, T, r, q)) or S <= 0 or T < 0:
        raise ValueError("S, T, r and q must be finite; S>0, T>=0")
    strikes = list(strikes)
    if not strikes:
        return []
    if any(isinstance(k, bool) or not isinstance(k, (int, float)) or not isfinite(k) or k <= 0
           for k in strikes):
        raise ValueError("strikes must be positive finite numbers")
    kinds = list(option_types) if option_types is not None else ["call"] * len(strikes)
    if len(kinds) != len(strikes) or any(x not in ("call", "put") for x in kinds):
        raise ValueError("option_types must match strikes and contain call/put")
    if not isinstance(integration_points, int) or isinstance(integration_points, bool) or integration_points < 128 or integration_points % 2:
        raise ValueError("integration_points must be an even integer >=128")
    if isinstance(integration_upper, bool) or not isinstance(integration_upper, (int, float)) or not isfinite(integration_upper) or integration_upper < 40 or integration_upper > 1000:
        raise ValueError("integration_upper must be finite and between 40 and 1000")
    if T == 0:
        return [max(S-k, 0) if kind == "call" else max(k-S, 0)
                for k, kind in zip(strikes, kinds)]
    if params.xi < 1e-7:
        integrated_var = params.theta * T + (params.v0 - params.theta) * (-np.expm1(-params.kappa*T)) / params.kappa
        sigma = sqrt(max(float(integrated_var / T), 0.0))
        return [bs_price(BSInputs(S, k, T, r, sigma, q), kind)
                for k, kind in zip(strikes, kinds)]

    n = integration_points
    u = np.linspace(1e-8, integration_upper, n + 1)
    weights = np.ones(n + 1)
    weights[1:-1:2] = 4
    weights[2:-1:2] = 2
    weights *= (integration_upper - 1e-8) / n / 3
    phi2 = _cf(u, S, T, r, q, params)
    phi1 = _cf(u - 1j, S, T, r, q, params) / (S * exp((r-q)*T))
    if not np.all(np.isfinite(phi1)) or not np.all(np.isfinite(phi2)):
        raise ArithmeticError("Heston characteristic function became non-finite")
    logk = np.log(np.asarray(strikes, dtype=float))
    phase = np.exp(-1j * np.outer(u, logk))
    p1 = 0.5 + np.sum(weights[:, None] * np.real(phase * (phi1 / (1j*u))[:, None]), axis=0) / np.pi
    p2 = 0.5 + np.sum(weights[:, None] * np.real(phase * (phi2 / (1j*u))[:, None]), axis=0) / np.pi
    calls = S * exp(-q*T) * p1 - np.asarray(strikes) * exp(-r*T) * p2
    out = []
    for k, kind, call in zip(strikes, kinds, calls):
        value = float(call if kind == "call" else call - S*exp(-q*T) + k*exp(-r*T))
        lower = max((S*exp(-q*T) - k*exp(-r*T)) * (1 if kind == "call" else -1), 0.0)
        upper = S*exp(-q*T) if kind == "call" else k*exp(-r*T)
        tolerance = 1e-7 * max(S, k, 1.0)
        if not isfinite(value) or value < lower-tolerance or value > upper+tolerance:
            raise ArithmeticError("Heston quadrature failed option price bounds")
        out.append(min(max(value, lower), upper))
    return out


def heston_price(S: float, K: float, T: float, r: float, q: float,
                 params: HestonParams, option_type: str = "call",
                 *, integration_points: int = 1024,
                 integration_upper: float = 160.0) -> float:
    return heston_prices(S, [K], T, r, q, params, [option_type],
                         integration_points=integration_points,
                         integration_upper=integration_upper)[0]


def heston_price_checked(S: float, K: float, T: float, r: float, q: float,
                         params: HestonParams, option_type: str = "call",
                         *, tolerance: float = 1e-5) -> dict:
    """Double grid and frequency range; expose numerical discrepancy."""
    if not isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be positive and finite")
    coarse = heston_price(S, K, T, r, q, params, option_type,
                          integration_points=1024, integration_upper=160)
    refined = heston_price(S, K, T, r, q, params, option_type,
                           integration_points=4096, integration_upper=320)
    difference = abs(coarse-refined)
    return {"price": refined if difference <= tolerance else None,
            "status": "ok" if difference <= tolerance else "quadrature_not_converged",
            "quadrature_difference": difference, "tolerance": tolerance,
            "coarse_price": coarse, "refined_price": refined}


def calibrate_heston(quotes: Sequence[dict], S: float, r: float, q: float,
                     *, initial: HestonParams | None = None,
                     max_evaluations: int = 240, integration_points: int = 512) -> dict:
    """Deterministic bounded damped least squares; report residual and stopping reason.

    This is a reproducible first fit, not a global optimizer or identifiability proof.
    Quotes: dictionaries with K, T, price, option_type (call/put).
    """
    if np is None:
        raise RuntimeError("NumPy is required for Heston calibration")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
           for v in (S, r, q)) or S <= 0:
        raise ValueError("Calibration S, r, q must be finite and S positive")
    if len(quotes) < 5:
        raise ValueError("At least five quotes are needed for a five-parameter fit")
    if isinstance(max_evaluations, bool) or not isinstance(max_evaluations, int) or max_evaluations < 12 or max_evaluations > 2000:
        raise ValueError("max_evaluations must be between 12 and 2000")
    if any(not all(isfinite(float(x[key])) for key in ("price", "K", "T"))
           or float(x["price"]) <= 0 or float(x["K"]) <= 0 or float(x["T"]) <= 0
           or x.get("option_type", "call") not in ("call", "put") for x in quotes):
        raise ValueError("Calibration quotes require positive price, strike and tenor")
    initial = initial or HestonParams(1.3, 0.055, 0.42, -0.25, 0.055)
    bounds = [(0.2, 8.0), (0.0025, 0.30), (0.02, 1.5), (-0.95, 0.95), (0.0025, 0.30)]
    names = ("kappa", "theta", "xi", "rho", "v0")
    x = np.array([getattr(initial, n) for n in names], dtype=float)
    x = np.array([np.clip(v, *b) for v, b in zip(x, bounds)])
    actual_initial = {name: float(value) for name, value in zip(names, x)}
    widths = np.array([hi-lo for lo, hi in bounds])
    groups = {}
    for item in quotes:
        groups.setdefault(float(item["T"]), []).append(item)
    observed = np.array([float(v["price"]) for v in quotes])
    evaluations = 0

    def predict(vector):
        nonlocal evaluations
        evaluations += 1
        try:
            p = HestonParams(*map(float, vector))
            predicted = {}
            for tenor, group in groups.items():
                values = heston_prices(S, [float(v["K"]) for v in group], tenor, r, q, p,
                                       [v.get("option_type", "call") for v in group],
                                       integration_points=integration_points)
                predicted[tenor] = iter(values)
            fitted = np.array([next(predicted[float(v["T"])]) for v in quotes])
            return fitted if np.all(np.isfinite(fitted)) else None
        except (ArithmeticError, ValueError, OverflowError, FloatingPointError):
            return None

    fitted = predict(x)
    if fitted is None:
        raise ArithmeticError("Initial Heston parameters cannot price the quote slice")
    best = float(np.sqrt(np.mean((fitted-observed)**2)))
    damping = 0.01
    status = "evaluation_limit"
    while evaluations + 6 <= max_evaluations:
        if best < 1e-5:
            status = "rmse_tolerance"
            break
        jac = np.empty((len(quotes), 5))
        for j in range(5):
            trial = x.copy()
            h = 1e-4 * widths[j]
            trial[j] = np.clip(x[j] + h, *bounds[j])
            if trial[j] == x[j]:
                trial[j] = np.clip(x[j] - h, *bounds[j])
            estimate = predict(trial)
            if estimate is None:
                raise ArithmeticError("Finite-difference Heston price failed")
            jac[:, j] = (estimate-fitted) / ((trial[j]-x[j])/widths[j])
        residual = observed-fitted
        normal = jac.T @ jac
        try:
            direction = np.linalg.solve(normal + damping*np.eye(5), jac.T @ residual)
        except np.linalg.LinAlgError:
            damping *= 10
            continue
        direction = np.clip(direction, -0.2, 0.2)
        candidate = np.array([np.clip(value + change*width, *bound)
                              for value, change, width, bound in zip(x, direction, widths, bounds)])
        candidate_prices = predict(candidate)
        score = (float(np.sqrt(np.mean((candidate_prices-observed)**2)))
                 if candidate_prices is not None else float("inf"))
        if score + 1e-10 < best:
            change = float(np.max(np.abs((candidate-x)/widths)))
            x, fitted, best = candidate, candidate_prices, score
            damping = max(damping/2, 1e-7)
            if change < 1e-5:
                status = "step_tolerance"
                break
        else:
            damping = min(damping*5, 1e7)
            if damping >= 1e7:
                status = "no_improvement"
                break
    if best < 1e-5:
        status = "rmse_tolerance"
    result = HestonParams(*map(float, x))
    return {
        "params": asdict(result), "rmse": best, "evaluations": evaluations,
        "initial_params": actual_initial,
        "calculation_config": {
            "method": "bounded_damped_least_squares",
            "integration_points": integration_points,
            "integration_upper": 160.0,
            "max_evaluations": max_evaluations,
            "evaluation_count_rule": "training_slice_price_evaluations_including_finite_difference_calls",
            "parameter_bounds": {name: {"min": low, "max": high}
                                 for name, (low, high) in zip(names, bounds)},
            "rmse_tolerance": 1e-5,
            "normalized_step_tolerance": 1e-5,
            "finite_difference_relative_step": 1e-4,
            "initial_damping": 0.01,
        },
        "status": status, "fitted_prices": [float(v) for v in fitted],
        "feller_ratio": result.feller_ratio,
        "feller_satisfied": result.feller_ratio is None or result.feller_ratio >= 1,
        "warning": "Five parameters may be weakly identified from one cross-section; multiple starts and holdout quotes are needed for research claims.",
    }
