"""Independent benchmarks, identities, boundaries, and finite differences."""

from dataclasses import replace
from math import exp, isfinite

import pytest

from derivatives_pricing import BSInputs, greeks, parity_gap, price


@pytest.mark.parametrize(
    "q, expected_call, expected_put",
    [
        (0.0, 10.4505835722, 5.5735260223),
        (0.03, 8.6525285539, 6.7309176492),
    ],
)
def test_reference_prices(q, expected_call, expected_put):
    inputs = BSInputs(100, 100, 1, 0.05, 0.2, q)
    assert price(inputs, "call") == pytest.approx(expected_call, abs=1e-9)
    assert price(inputs, "put") == pytest.approx(expected_put, abs=1e-9)


CASES = [
    BSInputs(100, 100, 1, 0.05, 0.2, 0.03),
    BSInputs(130, 80, 0.25, -0.02, 0.35, 0.01),
    BSInputs(60, 125, 3, 0.04, 0.55, 0.08),
    BSInputs(100, 100, 1e-4, 0.02, 0.3, 0.01),
    BSInputs(1e6, 1, 1, 0.01, 0.2, 0),
    BSInputs(1, 1e6, 1, 0.01, 0.2, 0),
    BSInputs(100, 100, 20, -0.01, 1.2, -0.005),
]


@pytest.mark.parametrize("inputs", CASES)
def test_parity_and_no_arbitrage_bounds(inputs):
    call = price(inputs, "call")
    put = price(inputs, "put")
    a = inputs.S * exp(-inputs.q * inputs.T)
    b = inputs.K * exp(-inputs.r * inputs.T)
    scale = max(a, b)
    assert isfinite(call) and isfinite(put)
    assert 0 <= call <= a + 1e-12 * scale
    assert 0 <= put <= b + 1e-12 * scale
    assert call >= max(a - b, 0) - 1e-12 * scale
    assert put >= max(b - a, 0) - 1e-12 * scale
    assert abs(parity_gap(call, put, inputs)) <= 1e-12 * scale
    assert parity_gap(call + 0.25, put, inputs) == pytest.approx(0.25, abs=1e-9)


@pytest.mark.parametrize("S,K,call,put", [
    (120, 100, 20, 0), (100, 100, 0, 0), (80, 100, 0, 20),
])
def test_expiry_payoff(S, K, call, put):
    inputs = BSInputs(S, K, 0, 1e308, 0, -1e308)
    assert price(inputs, "call") == call
    assert price(inputs, "put") == put


@pytest.mark.parametrize("S,K,r,q,T", [
    (120, 100, 0.03, 0.01, 2),
    (80, 100, -0.02, 0.04, 0.5),
    (100, 100, 0.01, 0.01, 1),
])
def test_zero_volatility(S, K, r, q, T):
    inputs = BSInputs(S, K, T, r, 0, q)
    forward_difference = S * exp(-q * T) - K * exp(-r * T)
    assert price(inputs, "call") == pytest.approx(max(forward_difference, 0))
    assert price(inputs, "put") == pytest.approx(max(-forward_difference, 0))


@pytest.mark.parametrize("field,value,error", [
    ("S", 0, ValueError), ("K", -1, ValueError),
    ("T", -0.1, ValueError), ("sigma", -0.1, ValueError),
    ("S", True, TypeError), ("r", "0.05", TypeError),
    ("q", float("nan"), ValueError), ("sigma", float("inf"), ValueError),
])
def test_invalid_inputs(field, value, error):
    values = dict(S=100, K=100, T=1, r=0.05, sigma=0.2, q=0)
    values[field] = value
    with pytest.raises(error):
        BSInputs(**values)


def test_invalid_option_and_parity_prices():
    inputs = BSInputs(100, 100, 1, 0.05, 0.2)
    with pytest.raises(ValueError, match="option_type"):
        price(inputs, "digital")
    with pytest.raises(ValueError, match="option_type"):
        greeks(inputs, True)
    with pytest.raises(TypeError):
        parity_gap(True, 0, inputs)
    with pytest.raises(ValueError):
        parity_gap(float("inf"), 0, inputs)


@pytest.mark.parametrize("T,sigma", [(0, 0.2), (1, 0), (0, 0)])
def test_greeks_reject_degenerate_boundary(T, sigma):
    with pytest.raises(ValueError, match="T > 0 and sigma > 0"):
        greeks(BSInputs(100, 100, T, 0.05, sigma), "call")


def test_overflow_is_explicit():
    inputs = BSInputs(100, 100, 10, -100, 0.2)
    with pytest.raises(OverflowError, match="floating-point range"):
        price(inputs, "call")


@pytest.mark.parametrize("inputs", [
    BSInputs(100, 100, 1, 0.05, 0.2, 0),
    BSInputs(115, 100, 0.7, -0.01, 0.35, 0.04),
    BSInputs(85, 100, 2.5, 0.03, 0.25, 0.01),
])
@pytest.mark.parametrize("option_type", ["call", "put"])
def test_greeks_against_central_differences(inputs, option_type):
    analytic = greeks(inputs, option_type)
    base = price(inputs, option_type)

    def first(field, h):
        up = price(replace(inputs, **{field: getattr(inputs, field) + h}), option_type)
        down = price(replace(inputs, **{field: getattr(inputs, field) - h}), option_type)
        return (up - down) / (2 * h)

    for multiplier in (1.0, 0.5):
        h_s = inputs.S * 1e-3 * multiplier
        up = price(replace(inputs, S=inputs.S + h_s), option_type)
        down = price(replace(inputs, S=inputs.S - h_s), option_type)
        gamma_fd = (up - 2 * base + down) / h_s**2
        estimates = {
            "delta": first("S", h_s),
            "gamma": gamma_fd,
            "vega": first("sigma", inputs.sigma * 1e-3 * multiplier),
            "theta": -first("T", inputs.T * 1e-3 * multiplier),
            "rho": first("r", 1e-4 * multiplier),
        }
        for name, estimate in estimates.items():
            assert estimate == pytest.approx(getattr(analytic, name), rel=2e-4, abs=2e-5), name
