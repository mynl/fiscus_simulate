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


def config_preview(cfg: RunConfig) -> ConfigPreview:
    """Compute a :class:`ConfigPreview` from a configuration (no simulation)."""
    bal = cfg.balances
    wealth = bal.total()
    yields = cfg.return_generator.income_yield  # annual, by asset class

    # Gross portfolio income (all accounts): balance x income yield, summed.
    by_asset = bal.by_asset()
    portfolio_income = sum(by_asset[a] * yields[a] for a in ASSET_CLASSES)

    # Taxable-account accrual tax at t=0: stocks -> dividend, bonds/cash -> interest.
    taxable_row = bal.balances[AccountType.taxable]
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
    )
