import math
import pytest
from derivatives_pricing.black_scholes import BSInputs, price
from derivatives_pricing.implied_volatility import implied_volatility


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("sigma", [0.12, 0.3, 0.9, 2.0])
def test_roundtrip(kind,sigma):
    inputs=BSInputs(2.8,2.7,0.4,0.02,sigma,0.01)
    actual,status=implied_volatility(price(inputs,kind),2.8,2.7,0.4,0.02,kind,0.01)
    assert status=="ok"
    assert actual==pytest.approx(sigma,abs=1e-8)


@pytest.mark.parametrize("market,T,expected",[(0,1,"nonpositive_price"),
    (4,1,"outside_model_bounds"),(0.1,0,"expiry_no_identifiable_iv"),
    (float("nan"),1,"invalid_input"),(-1,1,"nonpositive_price")])
def test_no_fake_zero_iv(market,T,expected):
    iv,status=implied_volatility(market,2.8,2.8,T,0.02,"call")
    assert iv is None
    assert status==expected


def test_lower_boundary():
    lower=3-2*math.exp(-0.02)
    assert implied_volatility(lower,3,2,1,0.02,"call")== (None,"lower_bound_unidentified")
