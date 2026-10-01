from math import exp

import pytest

from derivatives_pricing.black_scholes import BSInputs, price as bs_price
from derivatives_pricing.heston import HestonParams, calibrate_heston, heston_price, heston_price_checked, heston_prices

pytest.importorskip("numpy")


def test_zero_vol_of_vol_reduces_to_bs_with_integrated_variance():
    p = HestonParams(kappa=2, theta=.05, xi=0, rho=-.4, v0=.02)
    T = .7
    average_variance = .05 + (.02-.05)*(1-exp(-2*T))/(2*T)
    h = heston_price(100, 97, T, .02, .01, p, "call")
    b = bs_price(BSInputs(100, 97, T, .02, average_variance**.5, .01), "call")
    assert h == pytest.approx(b, abs=1e-12)


def test_heston_put_call_parity_and_bounds():
    p = HestonParams()
    c, put = heston_prices(100, [100, 100], .5, .02, .01, p, ["call", "put"])
    assert c-put == pytest.approx(100*exp(-.01*.5)-100*exp(-.02*.5), abs=1e-7)
    assert 0 < c < 100*exp(-.01*.5)
    assert 0 < put < 100*exp(-.02*.5)
    assert heston_price(100, 100, 0, .02, .01, p, "call") == 0


def test_known_parameter_slice_calibrates_from_distinct_start():
    true = HestonParams()
    quotes = []
    for T in (.25, .5, 1.0):
        strikes = [85, 92.5, 100, 107.5, 115]
        prices = heston_prices(100, strikes, T, .02, .01, true, integration_points=512)
        quotes.extend(dict(K=K, T=T, price=price, option_type="call")
                      for K, price in zip(strikes, prices))
    fit = calibrate_heston(quotes, 100, .02, .01, max_evaluations=120)
    assert fit["status"] == "rmse_tolerance"
    assert fit["rmse"] < 1e-5
    assert fit["evaluations"] > 1
    assert fit["params"]["rho"] == pytest.approx(-.5, abs=.02)
    bounded = calibrate_heston(quotes, 100, .02, .01,
                               initial=HestonParams(kappa=10), max_evaluations=12)
    assert bounded["initial_params"]["kappa"] == 8.0
    assert bounded["calculation_config"]["max_evaluations"] == 12


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        HestonParams(rho=1)
    with pytest.raises(ValueError):
        HestonParams(v0=-.01)


def test_independent_quantlib_heston_reference_prices():
    # QuantLib's testAlanLewisReference, test-suite/hestonmodel.cpp.
    params = HestonParams(kappa=4, theta=.25, xi=1, rho=-.5, v0=.04)
    expected = [26.774758743998854, 20.93334900059671, 16.070154917028834,
                12.132211516709845, 9.024913483457836]
    actual = heston_prices(100, [80, 90, 100, 110, 120], 1, .01, .02, params)
    assert actual == pytest.approx(expected, abs=2e-6)
    put = heston_price(100, 100, 1, .05, .075,
                       HestonParams(kappa=4, theta=.05, xi=.4, rho=-.75, v0=.1), "put")
    assert put == pytest.approx(10.147041515497, abs=2e-6)


def test_quadrature_refinement_for_etf_price_unit():
    p = HestonParams()
    result = heston_price_checked(2.7, 2.7, .25, .02, 0, p)
    assert result["status"] == "ok"
    assert result["quadrature_difference"] < 1e-5
    assert result["price"] is not None
    with pytest.raises(ValueError):
        heston_price(2.7, 2.7, .25, .02, 0, p, integration_upper=float("nan"))
