"""Config-derived sanity preview — a plausibility check without running the engine.

Every figure here is computed directly from a :class:`~fiscus_simulate.models.RunConfig`
in closed form, so it is instant and deterministic. The intent is the actuary's
back-of-envelope: household wealth, the income the portfolio throws off today, pensions
still to come, and the implied initial withdrawal rate — enough to say "plausible" or
"that can't be right" before committing to a full Monte-Carlo run.

Notes
-----
The **gross** withdrawal rate is planned spending over initial wealth (the classic
Bengen-style anchor). The **net** rate subtracts income available at t=0 (external
income plus gross portfolio income); before pensions start this is the real early
drawdown on the portfolio. Both are approximate: the net rate uses *gross* portfolio
income across all accounts and ignores that tax-deferred income is not freely spendable
until sold — it is a sanity gauge, not the engine's cash-flow logic.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import (
    ASSET_CLASSES,
    AccountType,
    AssetClass,
    RunConfig,
)


@dataclass
class ConfigPreview:
    """Closed-form summary of a configuration (see module docstring)."""

    wealth_total: float
    wealth_by_account: dict[str, float]
    wealth_by_asset: dict[str, float]
    portfolio_income_annual: float          # gross investment income, all accounts
    portfolio_income_tax_annual: float      # taxable-account accrual tax at t=0
    external_income_now_annual: float       # streams already active at t=0
    pension_income_total_annual: float      # sum of all streams' real amounts
    years_to_first_pension: float | None    # None if all streams already active / none
    planned_spending_annual: float
    gross_withdrawal_rate: float            # spending / wealth
    net_withdrawal_rate: float              # (spending - income now) / wealth
    # --- pre-retirement projection (real terms, closed form) ---
    years_to_retirement: float              # household: latest person's years to retire
    annual_real_savings_total: float        # summed across still-working people
    est_real_assets_at_retirement: float    # projected pooled wealth at retirement
    est_real_retirement_income: float       # pensions + portfolio income at retirement
    retirement_withdrawal_rate: float       # spending / assets at retirement
    retirement_income_coverage: float       # retirement income / spending


def config_preview(cfg: RunConfig) -> ConfigPreview:
    """Compute a :class:`ConfigPreview` from a configuration (no simulation)."""
    bal = cfg.balances
    wealth = bal.total()
    yields = cfg.return_generator.income_yield  # annual, by asset class

    # Gross portfolio income (all accounts): balance x income yield, summed.
    by_asset = bal.by_asset()
    portfolio_income = sum(by_asset[a] * yields[a] for a in ASSET_CLASSES)

    # Taxable-account accrual tax at t=0: stocks -> dividend, bonds/cash -> interest.
    taxable_row = bal.amounts()[AccountType.taxable]
    rates = cfg.tax_rates
    dividend_income = taxable_row[AssetClass.stocks] * yields[AssetClass.stocks]
    interest_income = (
        taxable_row[AssetClass.bonds] * yields[AssetClass.bonds]
        + taxable_row[AssetClass.cash] * yields[AssetClass.cash]
    )
    income_tax_now = rates.dividend * dividend_income + rates.interest * interest_income

    # External income: active-now vs total, and time to the first not-yet-started stream.
    external_now = 0.0
    pension_total = 0.0
    waits: list[float] = []
    for person in cfg.household.people:
        for s in person.income_streams:
            pension_total += s.annual_real
            active_now = person.current_age >= s.start_age and (
                s.end_age is None or person.current_age < s.end_age
            )
            if active_now:
                external_now += s.annual_real
            elif person.current_age < s.start_age:
                waits.append(s.start_age - person.current_age)
    years_to_first = min(waits) if waits else None

    spending = cfg.spending.total_annual_real
    gross_rate = spending / wealth if wealth > 0 else 0.0
    net_rate = max(spending - external_now - portfolio_income, 0.0) / wealth if wealth > 0 else 0.0

    # --- Pre-retirement projection (real terms; no inflation, no PV) ---
    real_returns = cfg.return_generator.real_return
    weights = {a: (by_asset[a] / wealth if wealth > 0 else 0.0) for a in ASSET_CLASSES}
    r = sum(weights[a] * real_returns[a] for a in ASSET_CLASSES)      # portfolio real return
    y = portfolio_income / wealth if wealth > 0 else 0.0             # portfolio income yield

    def _annuity_fv(rate: float, n: float) -> float:
        """Future value of 1/yr saved for ``n`` years, compounding at real ``rate``."""
        if n <= 0:
            return 0.0
        return n if abs(rate) < 1e-12 else ((1.0 + rate) ** n - 1.0) / rate

    horizons = [
        max(0.0, p.retirement_age - p.current_age)
        for p in cfg.household.people
        if p.retirement_age is not None and p.retirement_age > p.current_age
    ]
    years_to_ret = max(horizons) if horizons else 0.0

    savings_total = sum(
        p.annual_real_savings for p in cfg.household.people
        if p.retirement_age is not None and p.retirement_age > p.current_age
    )
    # Each person's contributions compound over their own working years, then sit invested
    # to the household retirement date.
    savings_fv = 0.0
    for p in cfg.household.people:
        if p.retirement_age is None or p.retirement_age <= p.current_age or p.annual_real_savings <= 0:
            continue
        n_i = p.retirement_age - p.current_age
        savings_fv += p.annual_real_savings * _annuity_fv(r, n_i) * (1.0 + r) ** (years_to_ret - n_i)
    est_assets_ret = wealth * (1.0 + r) ** years_to_ret + savings_fv

    est_ret_income = pension_total + est_assets_ret * y
    ret_wd_rate = spending / est_assets_ret if est_assets_ret > 0 else 0.0
    ret_coverage = est_ret_income / spending if spending > 0 else 0.0

    return ConfigPreview(
        wealth_total=wealth,
        wealth_by_account={k.value: v for k, v in bal.by_account().items()},
        wealth_by_asset={k.value: v for k, v in by_asset.items()},
        portfolio_income_annual=portfolio_income,
        portfolio_income_tax_annual=income_tax_now,
        external_income_now_annual=external_now,
        pension_income_total_annual=pension_total,
        years_to_first_pension=years_to_first,
        planned_spending_annual=spending,
        gross_withdrawal_rate=gross_rate,
        net_withdrawal_rate=net_rate,
        years_to_retirement=years_to_ret,
        annual_real_savings_total=savings_total,
        est_real_assets_at_retirement=est_assets_ret,
        est_real_retirement_income=est_ret_income,
        retirement_withdrawal_rate=ret_wd_rate,
        retirement_income_coverage=ret_coverage,
    )
