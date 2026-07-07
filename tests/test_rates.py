"""Annual->quarterly conversion and real->nominal identity."""
from __future__ import annotations

import numpy as np

from fiscus_simulate.rates import (
    annual_to_quarterly_return,
    annual_to_quarterly_yield,
    real_to_nominal,
)


def test_quarterly_return_compounds_to_annual():
    for annual in (0.0, 0.02, 0.07, -0.03):
        q = annual_to_quarterly_return(annual)
        assert np.isclose((1 + q) ** 4, 1 + annual)


def test_quarterly_yield_is_simple_quarter():
    assert np.isclose(annual_to_quarterly_yield(0.04), 0.01)
    assert np.allclose(annual_to_quarterly_yield(np.array([0.04, 0.08])), [0.01, 0.02])


def test_real_to_nominal_identity():
    r, pi = 0.05, 0.025
    assert np.isclose(real_to_nominal(r, pi), (1 + r) * (1 + pi) - 1)
    # zero inflation -> nominal equals real
    assert np.isclose(real_to_nominal(0.05, 0.0), 0.05)
