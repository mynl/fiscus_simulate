"""Stochastic return generator: shapes, seeding, zero-vol equivalence, recovery."""
from __future__ import annotations

import numpy as np

from fiscus_simulate.engine import simulate
from fiscus_simulate.models import ASSET_CLASSES, RunConfig
from fiscus_simulate.rates import annual_to_quarterly_return
from fiscus_simulate.returns.deterministic import build_deterministic_returns
from fiscus_simulate.returns.gbm import GBMReturns


def test_shapes_and_axis():
    cfg = RunConfig.default()
    rb = GBMReturns(cfg).generate(7)
    T = cfg.household.n_periods
    n = len(ASSET_CLASSES)
    assert rb.capital_return.shape == (7, T, n)
    assert rb.income_yield.shape == (7, T, n)
    assert rb.nominal_total.shape == (7, T, n)


def test_seed_reproducibility():
    cfg = RunConfig.default()
    a = GBMReturns(cfg).generate(20)
    b = GBMReturns(cfg).generate(20)
    assert np.array_equal(a.nominal_total, b.nominal_total)

    cfg2 = cfg.clone()
    cfg2.simulation.seed = cfg.simulation.seed + 1
    c = GBMReturns(cfg2).generate(20)
    assert not np.allclose(a.nominal_total, c.nominal_total)


def test_zero_vol_equals_deterministic():
    cfg = RunConfig.default().clone()
    for a in ASSET_CLASSES:
        cfg.return_generator.volatility[a] = 0.0
    gbm = GBMReturns(cfg).generate(4)
    det = build_deterministic_returns(cfg)
    assert np.allclose(gbm.nominal_total[0], det.nominal_total[0])
    assert np.allclose(gbm.capital_return[0], det.capital_return[0])


def test_income_capital_split():
    cfg = RunConfig.default()
    rb = GBMReturns(cfg).generate(5)
    assert np.allclose(rb.capital_return + rb.income_yield, rb.nominal_total)


def test_statistical_recovery():
    cfg = RunConfig.default()
    rb = GBMReturns(cfg).generate(3000)
    q_real = (1.0 + rb.nominal_total) / (1.0 + rb.overall_inflation_q) - 1.0
    x = np.log1p(q_real).reshape(-1, len(ASSET_CLASSES))

    real = np.array([cfg.return_generator.real_return[a] for a in ASSET_CLASSES])
    sigma = np.array([cfg.return_generator.volatility[a] for a in ASSET_CLASSES])
    m_expected = np.log1p(annual_to_quarterly_return(real))
    s_expected = sigma * np.sqrt(0.25)

    assert np.allclose(x.mean(axis=0), m_expected, atol=5e-3)
    assert np.allclose(x.std(axis=0), s_expected, rtol=0.05)

    corr = np.array(cfg.return_generator.correlations)
    sample_corr = np.corrcoef(x, rowvar=False)
    assert np.allclose(sample_corr, corr, atol=0.03)


def test_engine_reconciles_on_stochastic_run():
    cfg = RunConfig.default()
    rb = GBMReturns(cfg).generate(40)
    res = simulate(cfg, returns=rb)
    S, T = res.net_worth.shape
    w_begin = np.empty((S, T))
    w_begin[:, 0] = cfg.balances.total()
    w_begin[:, 1:] = res.net_worth[:, :-1]
    rhs = (w_begin + res.external_income[None, :] + res.savings[None, :]
           + res.investment_income + res.capital_return
           - res.spending_funded - res.tax_total)
    assert np.allclose(res.net_worth, rhs, atol=1e-6)
    assert res.net_worth.shape[0] == 40
