"""Deterministic engine: reconciliation identity + hand-verifiable micro-cases."""
from __future__ import annotations

import numpy as np

from fiscus_simulate.assets import proportional_sale
from fiscus_simulate.engine import simulate
from fiscus_simulate.models import (
    ASSET_CLASSES,
    AccountType,
    AssetClass,
    IncomeStream,
    RunConfig,
)


# --------------------------------------------------------------------------- helpers
def _flat_cfg(horizon_years=1):
    """A clean deterministic config: zero returns/yields/inflation/tax, no income.

    Balances hold only taxable cash, so the engine reduces to pure drawdown — every
    number is checkable by hand.
    """
    cfg = RunConfig.default().clone()
    cfg.household.horizon_years = horizon_years
    cfg.inflation.overall_mean = 0.0
    for c in cfg.inflation.category_excess_mean:
        cfg.inflation.category_excess_mean[c] = 0.0
    for a in ASSET_CLASSES:
        cfg.return_generator.real_return[a] = 0.0
        cfg.return_generator.income_yield[a] = 0.0
    cfg.tax_rates.tax_deferred_withdrawal = 0.0
    cfg.tax_rates.interest = 0.0
    cfg.tax_rates.dividend = 0.0
    cfg.tax_rates.realized_gain = 0.0
    cfg.tax_rates.other_pension = 0.0
    for person in cfg.household.people:
        person.income_streams = []
        person.retirement_age = None       # already retired: spend from t0, no savings
        person.annual_real_savings = 0.0
    cfg.spending.total_annual_real = 40_000  # 10,000 / quarter
    cfg.balances.balances = {
        AccountType.taxable: {AssetClass.stocks: 0.0, AssetClass.bonds: 0.0, AssetClass.cash: 100_000.0},
        AccountType.tax_deferred: {AssetClass.stocks: 0.0, AssetClass.bonds: 0.0, AssetClass.cash: 0.0},
        AccountType.tax_free: {AssetClass.stocks: 0.0, AssetClass.bonds: 0.0, AssetClass.cash: 0.0},
    }
    cfg.balances.taxable_basis = None
    return cfg


def _reconciles(res, initial_wealth):
    S, T = res.net_worth.shape
    w_begin = np.empty((S, T))
    w_begin[:, 0] = initial_wealth
    w_begin[:, 1:] = res.net_worth[:, :-1]
    rhs = (
        w_begin
        + res.external_income[None, :]
        + res.savings[None, :]
        + res.investment_income
        + res.capital_return
        - res.spending_funded
        - res.tax_total
    )
    return np.allclose(res.net_worth, rhs, atol=1e-6)


# ---------------------------------------------------------------------- identity tests
def test_reconciliation_identity_default():
    cfg = RunConfig.default()
    res = simulate(cfg)
    assert _reconciles(res, cfg.balances.total())


def test_zero_everything_pure_drawdown():
    cfg = _flat_cfg(horizon_years=1)
    res = simulate(cfg)
    np.testing.assert_allclose(res.net_worth[0], [90_000, 80_000, 70_000, 60_000])
    assert _reconciles(res, 100_000)
    assert res.funded.all()


def test_surplus_income_accumulates_as_cash():
    cfg = _flat_cfg(horizon_years=1)
    cfg.household.people[0].income_streams = [
        IncomeStream(annual_real=80_000, start_age=0, inflation_linked=False,
                     taxable_fraction=0.0)]
    res = simulate(cfg)  # income 20k/q, spend 10k/q -> +10k/q
    np.testing.assert_allclose(res.net_worth[0], [110_000, 120_000, 130_000, 140_000])
    assert _reconciles(res, 100_000)
    assert res.funded.all()


def test_pre_retirement_savings_accumulate_no_spending():
    """Before retirement: contributions grow the pool and no spending is drawn."""
    cfg = _flat_cfg(horizon_years=1)               # zero returns/inflation/yield/tax
    cfg.household.people[0].current_age = 60
    cfg.household.people[0].retirement_age = 61    # retires at period 4 (past this horizon)
    cfg.household.people[0].annual_real_savings = 40_000  # 10,000 / quarter
    res = simulate(cfg)
    # No spending drawn during accumulation; +10k/q contributions on 100k cash.
    np.testing.assert_allclose(res.net_worth[0], [110_000, 120_000, 130_000, 140_000])
    np.testing.assert_allclose(res.spending, [0, 0, 0, 0])       # spending deferred
    np.testing.assert_allclose(res.savings, [10_000, 10_000, 10_000, 10_000])
    assert _reconciles(res, 100_000)
    assert res.funded.all()


def test_exhaustion_failure_detected():
    cfg = _flat_cfg(horizon_years=1)
    cfg.balances.balances[AccountType.taxable][AssetClass.cash] = 15_000.0
    res = simulate(cfg)
    # q0 funds 10k (5k left); q1 needs 10k, only 5k available -> fails from q1.
    assert res.funded[0, 0]
    assert not res.funded[0, 1:].any()
    assert res.first_failure_period[0] == 1
    np.testing.assert_allclose(res.net_worth[0, 0], 5_000)
    np.testing.assert_allclose(res.net_worth[0, 1:], 0.0)
    assert _reconciles(res, 15_000)


# ------------------------------------------------------------------ gross-up unit tests
def test_grossup_tax_deferred_only():
    B = np.zeros((1, 3, 3))
    B[0, 1, 0] = 100_000  # tax_deferred stocks
    basis = np.zeros((1, 3))
    res = proportional_sale(B, basis, np.array([10_000.0]), td_rate=0.2, gain_rate=0.15)
    assert np.isclose(res.gross[0], 12_500)          # 10000 / (1 - 0.2)
    assert np.isclose(res.tax[0], 2_500)
    assert np.isclose(res.gross[0] - res.tax[0], 10_000)  # net raised == delta
    assert res.funded[0]


def test_grossup_taxable_gain():
    B = np.zeros((1, 3, 3))
    B[0, 0, 0] = 100_000  # taxable stocks
    basis = np.array([[60_000.0, 0.0, 0.0]])  # embedded gain ratio 0.4
    res = proportional_sale(B, basis, np.array([10_000.0]), td_rate=0.2, gain_rate=0.15)
    tau = 0.15 * 0.4
    assert np.isclose(res.gross[0], 10_000 / (1 - tau))
    assert np.isclose(res.gross[0] - res.tax[0], 10_000)
    assert np.isclose(res.realized_gain[0], res.gross[0] * 0.4)
    # basis reduced in proportion to fraction sold
    sold_frac = res.gross[0] / 100_000
    assert np.isclose(res.basis[0, 0], 60_000 * (1 - sold_frac))


def test_grossup_unfunded_when_portfolio_too_small():
    B = np.zeros((1, 3, 3))
    B[0, 1, 0] = 5_000  # only 5k, need 10k net
    res = proportional_sale(B, np.zeros((1, 3)), np.array([10_000.0]), td_rate=0.2, gain_rate=0.15)
    assert not res.funded[0]
    assert np.isclose(res.gross[0], 5_000)  # sells everything it can


# ----------------------------------------------------------------- outcome / success
def test_success_criteria_and_terminal_threshold():
    cfg = RunConfig.default()
    res = simulate(cfg)
    s = res.success()
    assert set(s) == {"portfolio_non_negative", "essential_funded",
                      "all_planned_funded", "terminal_above_threshold"}
    # a threshold above terminal wealth flips criterion 4 off
    high = res.terminal_net_worth[0] + 1
    assert not res.success(terminal_threshold=high)["terminal_above_threshold"][0]


def test_scenario_axis_broadcasts_identically():
    cfg = RunConfig.default()
    res = simulate(cfg, n_scenarios=3)
    assert res.net_worth.shape[0] == 3
    assert np.allclose(res.net_worth[0], res.net_worth[1])
    assert np.allclose(res.net_worth[0], res.net_worth[2])
