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

    # Pensions start at 67; owners are 60 and 58 -> none active now, total 20k.
    assert p.external_income_now_annual == 0
    assert p.pension_income_total_annual == 20_000
    assert p.years_to_first_pension == 7  # min(67-60, 67-58)

    # Withdrawal rates: gross 60k/1.25M = 4.8%; net (60k-28k)/1.25M = 2.56%.
    assert math.isclose(p.gross_withdrawal_rate, 0.048, rel_tol=1e-9)
    assert math.isclose(p.net_withdrawal_rate, 0.0256, rel_tol=1e-9)


def test_retirement_projection_zero_return():
    cfg = RunConfig.default()
    for a in cfg.return_generator.real_return:
        cfg.return_generator.real_return[a] = 0.0  # r=0 -> closed form is exact & simple
    p = config_preview(cfg)

    # Household retires with the later person: B is 58, retires 67 -> 9 years.
    assert p.years_to_retirement == 9
    assert p.annual_real_savings_total == 55_000  # 30k + 25k

    # r=0: assets = wealth + Σ (savings_i × years_i). A saves 7y, B saves 9y.
    expected = 1_250_000 + 30_000 * 7 + 25_000 * 9
    assert math.isclose(p.est_real_assets_at_retirement, expected, rel_tol=1e-9)

    # Retirement income = real pensions (20k) + assets × portfolio yield (28k/1.25M).
    y = 28_000 / 1_250_000
    assert math.isclose(p.est_real_retirement_income, 20_000 + expected * y, rel_tol=1e-9)
    assert math.isclose(p.retirement_withdrawal_rate, 60_000 / expected, rel_tol=1e-9)


def test_active_pension_counts_as_income_now():
    cfg = RunConfig.default()
    cfg.household.people[0].income_streams[0].start_age = 50  # already started at 60
    p = config_preview(cfg)
    assert p.external_income_now_annual == 11_000
    assert p.years_to_first_pension == 9  # only B's pension still pending (67-58)
