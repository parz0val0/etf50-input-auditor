"""Bracketed European BS IV, with explicit non-solutions (decimal volatility)."""
from math import exp, isfinite
from .black_scholes import BSInputs, price


def implied_volatility(market, spot, strike, years, rate, kind, q=0.0):
    values = (market, spot, strike, years, rate, q)
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) for x in values):
        return None, "invalid_input"
    if kind not in ("call", "put") or spot <= 0 or strike <= 0 or years < 0:
        return None, "invalid_input"
    if years == 0:
        return None, "expiry_no_identifiable_iv"
    if market <= 0:
        return None, "nonpositive_price"
    try:
        a, b = spot * exp(-q * years), strike * exp(-rate * years)
        lower = max(a-b, 0) if kind == "call" else max(b-a, 0)
        upper = a if kind == "call" else b
        if market < lower - 1e-10 or market >= upper:
            return None, "outside_model_bounds"
        if market <= lower + 1e-10:
            return None, "lower_bound_unidentified"
        def value(sigma):
            return price(BSInputs(spot, strike, years, rate, sigma, q), kind)
        lo, hi = 0.0, 1.0
        while value(hi) < market and hi < 16:
            hi *= 2
        if value(hi) < market:
            return None, "volatility_bracket_exceeded"
        for _ in range(100):
            mid = (lo + hi) / 2
            if value(mid) < market:
                lo = mid
            else:
                hi = mid
        sigma = (lo + hi) / 2
        if abs(value(sigma) - market) > 1e-9:
            return None, "residual_failed"
        return sigma, "ok"
    except (OverflowError, ValueError):
        return None, "numerical_failure"
