"""Config-derived preview: closed-form plausibility figures (no engine run)."""
from __future__ import annotations

import math

from fiscus_simulate.models import RunConfig
from fiscus_simulate.preview import config_preview


def test_default_preview_figures():
    p = config_preview(RunConfig.default())

    # Wealth: 300+100+50 + 400+200+0 + 150+50+0 = 1,250,000.
    assert p.wealth_total == 1_250_000

    # Gross portfolio income: stocks 2%*850k + bonds 3%*350k + cash 1%*50k = 28,000.
    assert math.isclose(p.portfolio_income_annual, 28_000, rel_tol=1e-9)

    # Taxable-account accrual tax now: div 0.15*(300k*2%) + int 0.20*(100k*3% + 50k*1%).
    assert math.isclose(p.portfolio_income_tax_annual, 900 + 700, rel_tol=1e-9)

    # Default is retired (both 62): A's Social Security starts at 67, B has none.
    assert p.external_income_now_annual == 0                 # SS not active until 67
    assert p.pension_income_total_annual == 40_000           # A's SS only
    assert p.years_to_first_pension == 5                     # 67 - 62

    # Withdrawal rates: gross 60k/1.25M = 4.8%; net (60k-28k)/1.25M = 2.56%.
    assert math.isclose(p.gross_withdrawal_rate, 0.048, rel_tol=1e-9)
    assert math.isclose(p.net_withdrawal_rate, 0.0256, rel_tol=1e-9)


def test_account_matrix_reconciles():
    p = config_preview(RunConfig.default())
    rows = {r["account"]: r for r in p.account_matrix}
    assert set(rows) == {"taxable", "tax_deferred", "tax_free", "Total"}
    # Total row = column sums; expected income = gross portfolio income (28k).
    assert rows["Total"]["balance_total"] == 1_250_000
    assert math.isclose(rows["Total"]["expected_income"], 28_000, rel_tol=1e-9)
    # After-tax total = taxable net of div/interest tax + tax-deferred×0.8 + tax-free.
    assert rows["Total"]["after_tax_income"] < rows["Total"]["expected_income"]


def test_retirement_projection_zero_return():
    # The retired default has no accumulation phase; use the generic (still-saving) preset.
    cfg = RunConfig.generic()
    for a in cfg.return_generator.real_return:
        cfg.return_generator.real_return[a] = 0.0  # r=0 -> closed form is exact & simple
    p = config_preview(cfg)

    people = cfg.household.people
    years = max(pp.retirement_age - pp.current_age for pp in people)
    assert p.years_to_retirement == years
    assert p.annual_real_savings_total == sum(pp.annual_real_savings for pp in people)

    # r=0: assets = wealth + Σ (savings_i × own working years).
    sav = sum(pp.annual_real_savings * (pp.retirement_age - pp.current_age) for pp in people)
    expected = cfg.balances.total() + sav
    assert math.isclose(p.est_real_assets_at_retirement, expected, rel_tol=1e-9)


def test_active_pension_counts_as_income_now():
    cfg = RunConfig.default()
    cfg.household.people[0].income_streams[0].start_age = 50  # already started at 62
    p = config_preview(cfg)
    assert p.external_income_now_annual == 40_000
    assert p.years_to_first_pension is None  # B has no streams; A's is now active
