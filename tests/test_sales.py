"""Ordered (tax-efficient) liquidation strategy — 1.9.0 sale primitive.

Hand-checkable micro-cases for `ordered_sale`: draw-down priority, analytic gross-up,
tax-free preservation, and the unfunded flag. Not yet wired into the engine.
"""
from __future__ import annotations

import numpy as np

from fiscus_simulate.assets import (
    BONDS,
    CASH,
    STOCKS,
    TAX_DEFERRED,
    TAX_FREE,
    TAXABLE,
    ordered_sale,
)


def _balances(taxable, tax_deferred, tax_free):
    """(1,3,3) balances from three (stocks, bonds, cash) triples."""
    b = np.zeros((1, 3, 3))
    b[0, TAXABLE, :] = taxable
    b[0, TAX_DEFERRED, :] = tax_deferred
    b[0, TAX_FREE, :] = tax_free
    return b


def test_gross_up_nets_exactly_delta():
    # Taxable stocks 100, basis 50 -> gain ratio 0.5; gain_rate 0.15 -> tau 0.075.
    bal = _balances((100.0, 0, 0), (0, 0, 0), (0, 0, 0))
    basis = np.array([[50.0, 0.0, 0.0]])
    res = ordered_sale(bal, basis, np.array([10.0]), td_rate=0.2, gain_rate=0.15)
    assert res.funded[0]
    # G = 10/(1-0.075); tax = G*0.075; net proceeds == 10.
    g = 10.0 / (1 - 0.075)
    assert np.isclose(res.gross[0], g)
    assert np.isclose(res.tax[0], g * 0.075)
    assert np.isclose(res.gross[0] - res.tax[0], 10.0)
    assert np.isclose(res.realized_gain[0], (g) * 0.5)  # all sold is stock, gain ratio 0.5


def test_draws_taxable_before_tax_deferred_before_tax_free():
    # Taxable only 5 (no gain), then tax-deferred (20% rate), tax-free untouched.
    bal = _balances((5.0, 0, 0), (100.0, 0, 0), (100.0, 0, 0))
    basis = np.array([[5.0, 0.0, 0.0]])
    res = ordered_sale(bal, basis, np.array([10.0]), td_rate=0.2, gain_rate=0.15)
    assert res.funded[0]
    # Taxable fully drained; tax-deferred grosses up 5/(1-0.2)=6.25; tax-free intact.
    assert np.isclose(res.balances[0, TAXABLE].sum(), 0.0)
    assert np.isclose(res.balances[0, TAX_DEFERRED, STOCKS], 100.0 - 6.25)
    assert np.isclose(res.balances[0, TAX_FREE].sum(), 100.0)
    assert np.isclose(res.tax[0], 6.25 * 0.2)          # only the tax-deferred tranche is taxed


def test_tax_free_has_no_sale_tax():
    # Force into tax-free: taxable+tax-deferred empty.
    bal = _balances((0, 0, 0), (0, 0, 0), (0, 0, 40.0))
    basis = np.zeros((1, 3))
    res = ordered_sale(bal, basis, np.array([30.0]), td_rate=0.2, gain_rate=0.15)
    assert res.funded[0]
    assert np.isclose(res.tax[0], 0.0)
    assert np.isclose(res.gross[0], 30.0)
    assert np.isclose(res.balances[0, TAX_FREE, CASH], 10.0)


def test_unfunded_when_insufficient():
    bal = _balances((1.0, 0, 0), (0, 0, 0), (0, 0, 0))
    basis = np.array([[1.0, 0.0, 0.0]])
    res = ordered_sale(bal, basis, np.array([50.0]), td_rate=0.2, gain_rate=0.15)
    assert not res.funded[0]
    assert np.isclose(res.balances[0].sum(), 0.0)      # everything sellable was sold


def test_zero_delta_is_a_noop():
    bal = _balances((100.0, 50, 10), (100.0, 0, 0), (100.0, 0, 0))
    basis = np.array([[70.0, 45.0, 10.0]])
    res = ordered_sale(bal, basis, np.array([0.0]), td_rate=0.2, gain_rate=0.15)
    assert res.funded[0]
    assert np.allclose(res.balances, bal)
    assert np.isclose(res.gross[0], 0.0) and np.isclose(res.tax[0], 0.0)


def test_proportional_within_account():
    # Within an account, the sale spreads across assets by market weight.
    bal = _balances((60.0, 40.0, 0.0), (0, 0, 0), (0, 0, 0))
    basis = np.array([[60.0, 40.0, 0.0]])   # no embedded gain -> tau 0, gross == net
    res = ordered_sale(bal, basis, np.array([50.0]), td_rate=0.2, gain_rate=0.15)
    assert res.funded[0]
    # 60/40 split of a 50 sale: stocks 30, bonds 20 sold.
    assert np.isclose(res.balances[0, TAXABLE, STOCKS], 30.0)
    assert np.isclose(res.balances[0, TAXABLE, BONDS], 20.0)
