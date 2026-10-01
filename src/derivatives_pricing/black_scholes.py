"""Black-Scholes with a continuously compounded dividend yield."""

from dataclasses import dataclass
from math import erfc, exp, fsum, isfinite, log, pi, sqrt
from numbers import Real
from typing import Literal

OptionType = Literal["call", "put"]
_SQRT_2 = sqrt(2.0)
_SQRT_2PI = sqrt(2.0 * pi)


def _number(name: str, value: Real) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite real number, excluding bool")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _finite(name: str, value: float) -> float:
    if not isfinite(value):
        raise OverflowError(f"{name} exceeds floating-point range")
    return value


def _exp(value: float) -> float:
    _finite("exponent", value)
    try:
        return exp(value)
    except OverflowError as exc:
        raise OverflowError("discount factor exceeds floating-point range") from exc


@dataclass(frozen=True)
class BSInputs:
    """S/K: currency per unit; T: years; r/q/sigma: annual decimal rates."""

    S: float
    K: float
    T: float
    r: float
    sigma: float
    q: float = 0.0

    def __post_init__(self) -> None:
        for name in ("S", "K", "T", "r", "sigma", "q"):
            object.__setattr__(self, name, _number(name, getattr(self, name)))
        if self.S <= 0 or self.K <= 0:
            raise ValueError("S and K must be positive")
        if self.T < 0 or self.sigma < 0:
            raise ValueError("T and sigma must be nonnegative")


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


def _inputs(inputs: BSInputs) -> None:
    if not isinstance(inputs, BSInputs):
        raise TypeError("inputs must be BSInputs")


def _option_type(option_type: OptionType) -> None:
    if option_type not in ("call", "put") or not isinstance(option_type, str):
        raise ValueError("option_type must be 'call' or 'put'")


def _cdf(x: float) -> float:
    return 0.5 * erfc(-x / _SQRT_2)


def _survival(x: float) -> float:
    return 0.5 * erfc(x / _SQRT_2)


def _terms(inputs: BSInputs):
    a = _finite("discounted spot", inputs.S * _exp(-inputs.q * inputs.T))
    b = _finite("discounted strike", inputs.K * _exp(-inputs.r * inputs.T))
    return a, b


def _d_values(inputs: BSInputs):
    sqrt_t = sqrt(inputs.T)
    volatility_time = _finite("sigma * sqrt(T)", inputs.sigma * sqrt_t)
    if volatility_time == 0:
        raise OverflowError("sigma * sqrt(T) is below floating-point range")
    drift = _finite("forward drift", (inputs.r - inputs.q) * inputs.T)
    m = _finite("log forward moneyness", fsum((log(inputs.S), -log(inputs.K), drift)))
    d1 = _finite("d1", (m + 0.5 * volatility_time * volatility_time) / volatility_time)
    d2 = _finite("d2", d1 - volatility_time)
    return d1, d2, m, sqrt_t


def price(inputs: BSInputs, option_type: OptionType) -> float:
    """Price one European call or put in the same currency unit as S and K."""
    _inputs(inputs)
    _option_type(option_type)
    if inputs.T == 0:
        payoff = inputs.S - inputs.K if option_type == "call" else inputs.K - inputs.S
        return max(payoff, 0.0)

    a, b = _terms(inputs)
    if inputs.sigma == 0:
        value = a - b if option_type == "call" else b - a
        return max(_finite("price", value), 0.0)

    d1, d2, m, _ = _d_values(inputs)
    if m <= 0:
        call = _finite("call price", fsum((a * _cdf(d1), -b * _cdf(d2))))
        if option_type == "call":
            return max(call, 0.0)
        return _finite("put price", fsum((call, b, -a)))
    put = _finite("put price", fsum((b * _survival(d2), -a * _survival(d1))))
    if option_type == "put":
        return max(put, 0.0)
    return _finite("call price", fsum((put, a, -b)))


def greeks(inputs: BSInputs, option_type: OptionType) -> Greeks:
    """Analytic sensitivities; theta is annual calendar-time decay (-dV/dT)."""
    _inputs(inputs)
    _option_type(option_type)
    if inputs.T == 0 or inputs.sigma == 0:
        raise ValueError("Greeks require T > 0 and sigma > 0")

    a, b = _terms(inputs)
    d1, d2, _, sqrt_t = _d_values(inputs)
    discount_q = _exp(-inputs.q * inputs.T)
    pdf_d1 = exp(-0.5 * d1 * d1) / _SQRT_2PI
    gamma_denominator = _finite("Gamma denominator", inputs.S * inputs.sigma * sqrt_t)
    if gamma_denominator == 0:
        raise OverflowError("Gamma denominator is below floating-point range")
    gamma = discount_q * pdf_d1 / gamma_denominator
    vega = a * pdf_d1 * sqrt_t
    common_theta = -a * pdf_d1 * inputs.sigma / (2.0 * sqrt_t)

    if option_type == "call":
        delta = discount_q * _cdf(d1)
        theta = fsum((common_theta, inputs.q * a * _cdf(d1),
                      -inputs.r * b * _cdf(d2)))
        rho = inputs.T * b * _cdf(d2)
    else:
        delta = -discount_q * _survival(d1)
        theta = fsum((common_theta, -inputs.q * a * _survival(d1),
                      inputs.r * b * _survival(d2)))
        rho = -inputs.T * b * _survival(d2)

    values = (delta, gamma, vega, theta, rho)
    return Greeks(*(_finite("Greek", value) for value in values))


def parity_gap(call_price: float, put_price: float, inputs: BSInputs) -> float:
    """Return C - P - S*exp(-q*T) + K*exp(-r*T)."""
    _inputs(inputs)
    call = _number("call_price", call_price)
    put = _number("put_price", put_price)
    a, b = _terms(inputs)
    return _finite("parity gap", fsum((call, -put, -a, b)))
