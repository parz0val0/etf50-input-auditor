"""Numerical prices for European options under the stage 1 GBM assumptions."""

from dataclasses import dataclass
from math import exp, isfinite, log, sqrt
from random import Random

from .black_scholes import BSInputs, OptionType, _inputs, _option_type, price

_NORMAL_975 = 1.959963984540054


def _positive_int(name: str, value: int, minimum: int = 1) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _finite(name: str, value: float) -> float:
    if not isfinite(value):
        raise OverflowError(f"{name} exceeds floating-point range")
    return value


def _exp(name: str, exponent: float) -> float:
    _finite(name, exponent)
    try:
        return exp(exponent)
    except OverflowError as exc:
        raise OverflowError(f"{name} exceeds floating-point range") from exc


def binomial_price(inputs: BSInputs, option_type: OptionType, steps: int) -> float:
    """Cox-Ross-Rubinstein European price with ``steps`` time intervals."""
    _inputs(inputs)
    _option_type(option_type)
    _positive_int("steps", steps)
    if inputs.T == 0 or inputs.sigma == 0:
        return price(inputs, option_type)

    dt = inputs.T / steps
    up_log = inputs.sigma * sqrt(dt)
    if not isfinite(up_log) or up_log == 0:
        raise OverflowError("tree up factor is outside floating-point resolution")
    up = _exp("tree up factor", up_log)
    down = 1.0 / up
    denominator = up - down
    if denominator == 0:
        raise OverflowError("tree up/down factors are indistinguishable")
    growth = _exp("tree growth", (inputs.r - inputs.q) * dt)
    probability = (growth - down) / denominator
    if not isfinite(probability):
        raise OverflowError("risk-neutral probability is not finite")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("invalid risk-neutral probability; increase steps")

    discount = _exp("tree discount", -inputs.r * dt)
    log_spot = log(inputs.S)
    terminal = []
    for up_moves in range(steps + 1):
        terminal_spot = _exp("terminal spot", log_spot + (2 * up_moves - steps) * up_log)
        payoff = (terminal_spot - inputs.K if option_type == "call"
                  else inputs.K - terminal_spot)
        terminal.append(max(payoff, 0.0))

    for remaining in range(steps, 0, -1):
        for node in range(remaining):
            terminal[node] = _finite(
                "tree price",
                discount * ((1.0 - probability) * terminal[node]
                            + probability * terminal[node + 1]),
            )
    return terminal[0]


@dataclass(frozen=True)
class MonteCarloResult:
    price: float
    standard_error: float
    ci_lower: float
    ci_upper: float
    paths: int
    seed: int


def monte_carlo_price(
    inputs: BSInputs, option_type: OptionType, paths: int, seed: int
) -> MonteCarloResult:
    """Antithetic terminal-GBM simulation with an approximate 95% normal CI.

    ``paths`` counts terminal payoffs, so it must be even. One antithetic
    payoff pair is one independent observation for the sample variance.
    """
    _inputs(inputs)
    _option_type(option_type)
    _positive_int("paths", paths, minimum=4)
    if paths % 2:
        raise ValueError("paths must be even for antithetic sampling")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer, excluding bool")
    if inputs.T == 0 or inputs.sigma == 0:
        exact = price(inputs, option_type)
        return MonteCarloResult(exact, 0.0, exact, exact, paths, seed)

    drift = _finite("simulation drift", (inputs.r - inputs.q - 0.5 * inputs.sigma**2) * inputs.T)
    diffusion = _finite("simulation diffusion", inputs.sigma * sqrt(inputs.T))
    discount = _exp("simulation discount", -inputs.r * inputs.T)
    log_spot = log(inputs.S)
    rng = Random(seed)
    pairs = paths // 2
    mean = 0.0
    m2 = 0.0

    for index in range(1, pairs + 1):
        z = rng.gauss(0.0, 1.0)
        positive_spot = _exp("simulated spot", log_spot + drift + diffusion * z)
        negative_spot = _exp("simulated spot", log_spot + drift - diffusion * z)
        if option_type == "call":
            pair_payoff = (max(positive_spot - inputs.K, 0.0)
                           + max(negative_spot - inputs.K, 0.0)) / 2.0
        else:
            pair_payoff = (max(inputs.K - positive_spot, 0.0)
                           + max(inputs.K - negative_spot, 0.0)) / 2.0
        observation = _finite("discounted payoff", discount * pair_payoff)
        difference = observation - mean
        mean += difference / index
        m2 += difference * (observation - mean)

    standard_error = _finite("standard error", sqrt(m2 / (pairs - 1) / pairs))
    half_width = _NORMAL_975 * standard_error
    return MonteCarloResult(
        _finite("Monte Carlo price", mean), standard_error,
        _finite("CI lower", mean - half_width),
        _finite("CI upper", mean + half_width), paths, seed,
    )
