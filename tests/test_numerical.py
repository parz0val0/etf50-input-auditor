"""Numerical convergence and failure-mode tests under synthetic inputs."""

from math import exp, isfinite, sqrt

import pytest

from derivatives_pricing import BSInputs, binomial_price, monte_carlo_price, price

INPUTS = BSInputs(100, 100, 1, 0.05, 0.2, 0.03)


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_crr_converges_to_black_scholes(option_type):
    benchmark = price(INPUTS, option_type)
    errors = [abs(binomial_price(INPUTS, option_type, n) - benchmark)
              for n in (50, 100, 200, 400, 800)]
    assert all(later < earlier for earlier, later in zip(errors, errors[1:]))
    assert errors[-1] < 0.003


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_tree_parity_with_dividends_and_negative_rate(option_type):
    inputs = BSInputs(90, 110, 2, -0.01, 0.3, 0.04)
    call = binomial_price(inputs, "call", 400)
    put = binomial_price(inputs, "put", 400)
    assert isfinite(binomial_price(inputs, option_type, 400))
    expected = inputs.S * exp(-inputs.q * inputs.T) - inputs.K * exp(-inputs.r * inputs.T)
    assert call - put == pytest.approx(expected, abs=1e-10)


def test_too_few_tree_steps_reject_invalid_probability():
    inputs = BSInputs(100, 100, 1, 0.2, 0.05)
    with pytest.raises(ValueError, match="increase steps"):
        binomial_price(inputs, "call", 1)
    assert isfinite(binomial_price(inputs, "call", 64))


def test_crr_one_step_matches_independent_calculation():
    inputs = BSInputs(100, 100, 1, 0.05, 0.2, 0.03)
    up = exp(0.2)
    down = exp(-0.2)
    p = (exp(0.02) - down) / (up - down)
    expected = exp(-0.05) * p * (100 * up - 100)
    assert binomial_price(inputs, "call", 1) == pytest.approx(expected)


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_monte_carlo_seed_and_convergence(option_type):
    small = monte_carlo_price(INPUTS, option_type, 2000, 20260928)
    large = monte_carlo_price(INPUTS, option_type, 128000, 20260928)
    benchmark = price(INPUTS, option_type)
    assert small == monte_carlo_price(INPUTS, option_type, 2000, 20260928)
    assert large.standard_error < small.standard_error / 4
    assert abs(large.price - benchmark) < abs(small.price - benchmark)
    assert large.ci_lower <= benchmark <= large.ci_upper
    assert large.ci_upper - large.ci_lower == pytest.approx(
        2 * 1.959963984540054 * large.standard_error
    )
    assert large.paths == 128000 and large.seed == 20260928


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize("T,sigma", [(0, 0.2), (1, 0)])
def test_numerical_methods_return_exact_boundary_price(option_type, T, sigma):
    inputs = BSInputs(110, 100, T, 0.05, sigma, 0.03)
    exact = price(inputs, option_type)
    assert binomial_price(inputs, option_type, 1) == exact
    result = monte_carlo_price(inputs, option_type, 4, 0)
    assert (result.price, result.standard_error, result.ci_lower, result.ci_upper) == (
        exact, 0.0, exact, exact
    )


@pytest.mark.parametrize("steps,error", [(0, ValueError), (1.5, TypeError), (True, TypeError)])
def test_invalid_tree_steps(steps, error):
    with pytest.raises(error):
        binomial_price(INPUTS, "call", steps)


@pytest.mark.parametrize("paths,seed,error", [
    (2, 1, ValueError), (5, 1, ValueError), (4.0, 1, TypeError),
    (4, True, TypeError), (True, 1, TypeError),
])
def test_invalid_monte_carlo_controls(paths, seed, error):
    with pytest.raises(error):
        monte_carlo_price(INPUTS, "put", paths, seed)


def test_numerical_option_type_validation():
    with pytest.raises(ValueError, match="option_type"):
        binomial_price(INPUTS, "digital", 10)
    with pytest.raises(ValueError, match="option_type"):
        monte_carlo_price(INPUTS, "digital", 10, 1)
