"""Quarterly retirement simulation engine (vectorized NumPy).

Stage 2: a deterministic single-path engine (scenario axis present, size 1) that becomes
the correctness backbone. The period loop is Python (160 quarters); everything inside is
vectorized over the scenario axis so Stage 4 scales to many paths unchanged. This module
never imports Flask; the web layer reaches it via :mod:`fiscus_simulate.service`.

Order of operations and the reconciliation identity are documented in
``dev/plan-1.1-stage2-engine.md`` (income-first model). The identity, checked by tests:

    W_end = W_begin + external_income + investment_income + capital_return
            + savings - spending - tax
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .assets import BONDS, CASH, STOCKS, TAXABLE, proportional_sale
from .income import build_external_income
from .models import ACCOUNT_TYPES, ASSET_CLASSES, RunConfig
from .returns.base import ReturnsBundle
from .returns.deterministic import build_deterministic_returns
from .savings import build_savings_path
from .spending import build_spending_path
from .tax import income_tax


@dataclass
class EngineResult:
    """Per-period arrays (S, T) and per-path outcome measures from a simulation.

    Notes
    -----
    Arrays that are deterministic across scenarios (spending, external income) are stored
    once as ``(T,)``. Scenario-varying arrays are ``(S, T)``.
    """

    config: RunConfig
    net_worth: np.ndarray          # (S, T) end-of-period net worth
    spending: np.ndarray           # (T,) active planned nominal spending (0 pre-retirement)
    spending_funded: np.ndarray    # (S, T) actually-funded spending (< planned on failure)
    external_income: np.ndarray    # (T,)
    savings: np.ndarray            # (T,) nominal pre-retirement savings contributions
    investment_income: np.ndarray  # (S, T)
    capital_return: np.ndarray     # (S, T)
    tax_income: np.ndarray         # (S, T)
    tax_sale: np.ndarray           # (S, T)
    sales_gross: np.ndarray        # (S, T)
    realized_gain: np.ndarray      # (S, T)
    funded: np.ndarray             # (S, T) bool

    # --- optional per-period balance capture (only when capture_balances=True) ---
    # Consolidated-over-accounts asset balances, (S, T, n_asset): beginning-of-period and
    # end-of-period. None on the hot path so the 100k run allocates nothing extra.
    balances_begin: np.ndarray | None = None
    balances_end: np.ndarray | None = None

    # --- per-path outcome measures (computed in __post_init__) ---
    first_failure_period: np.ndarray = None  # type: ignore[assignment]
    years_funded: np.ndarray = None          # type: ignore[assignment]
    min_net_worth: np.ndarray = None         # type: ignore[assignment]
    terminal_net_worth: np.ndarray = None    # type: ignore[assignment]
    total_tax: np.ndarray = None             # type: ignore[assignment]
    total_sales: np.ndarray = None           # type: ignore[assignment]

    def __post_init__(self) -> None:
        S, T = self.net_worth.shape
        not_funded = ~self.funded
        any_fail = not_funded.any(axis=1)
        first = np.where(any_fail, not_funded.argmax(axis=1), T)
        self.first_failure_period = np.where(any_fail, first, -1)
        self.years_funded = first / 4.0
        self.min_net_worth = self.net_worth.min(axis=1)
        self.terminal_net_worth = self.net_worth[:, -1]
        self.total_tax = (self.tax_income + self.tax_sale).sum(axis=1)
        self.total_sales = self.sales_gross.sum(axis=1)

    @property
    def tax_total(self) -> np.ndarray:
        """Per-period total tax (income + sale), ``(S, T)``."""
        return self.tax_income + self.tax_sale

    def success(self, terminal_threshold: float | None = None) -> dict[str, np.ndarray]:
        """Boolean success measures per path (criteria 1-4; several coincide in V1)."""
        thr = self.config.simulation.terminal_threshold if terminal_threshold is None \
            else terminal_threshold
        all_funded = self.funded.all(axis=1)
        return {
            "portfolio_non_negative": (self.net_worth >= -1e-6).all(axis=1),
            "essential_funded": all_funded,       # coincides with all-funded in V1
            "all_planned_funded": all_funded,
            "terminal_above_threshold": self.terminal_net_worth > thr,
        }


def simulate(config: RunConfig, returns: ReturnsBundle | None = None,
             n_scenarios: int = 1, capture_balances: bool = False) -> EngineResult:
    """Run the quarterly engine.

    Parameters
    ----------
    config : RunConfig
        The run configuration (single source of truth).
    returns : ReturnsBundle, optional
        Per-period return arrays ``(Sr, T, n_asset)``. Defaults to the deterministic
        provider (``Sr = 1``, broadcast over scenarios). When a bundle is supplied its
        scenario count sets ``S``.
    n_scenarios : int
        Scenario-axis size when ``returns`` is None (deterministic). Ignored otherwise.
    capture_balances : bool
        When True, additionally record consolidated-over-accounts asset balances at the
        start and end of every period (``(S, T, n_asset)``) — used by the single-scenario
        "walk" replay. Off by default so the 100k hot path allocates nothing extra.
    """
    if returns is None:
        returns = build_deterministic_returns(config)  # (1, T, n_asset)
        S = n_scenarios
    else:
        S = returns.n_scenarios

    T = config.household.n_periods
    n_acct, n_asset = len(ACCOUNT_TYPES), len(ASSET_CLASSES)
    td_rate = config.tax_rates.tax_deferred_withdrawal
    gain_rate = config.tax_rates.realized_gain

    # Initial state (broadcast the single config over S). Reconstruct the account x asset
    # dollar matrix from the proportional config (taxable = implied remainder).
    amounts = config.balances.amounts()
    B = np.zeros((S, n_acct, n_asset))
    for ai, acct in enumerate(ACCOUNT_TYPES):
        for si, asset in enumerate(ASSET_CLASSES):
            B[:, ai, si] = amounts[acct][asset]
    basis0 = config.balances.resolved_taxable_basis()
    basis = np.tile(np.array([basis0[a] for a in ASSET_CLASSES]), (S, 1))

    spend = build_spending_path(config)
    inc = build_external_income(config, returns.overall_inflation_q)
    savings = build_savings_path(config, returns.overall_inflation_q)
    p_spend_start = config.household.spending_start_period
    # Active planned spending: zero during the pre-retirement accumulation phase.
    plan = np.where(np.arange(T) >= p_spend_start, spend.total, 0.0)

    # Output buffers
    net_worth = np.zeros((S, T))
    spending_funded_a = np.zeros((S, T))
    inv_income_a = np.zeros((S, T))
    cap_return_a = np.zeros((S, T))
    tax_income_a = np.zeros((S, T))
    tax_sale_a = np.zeros((S, T))
    sales_gross_a = np.zeros((S, T))
    realized_gain_a = np.zeros((S, T))
    funded_a = np.zeros((S, T), dtype=bool)
    bal_begin = np.zeros((S, T, n_asset)) if capture_balances else None
    bal_end = np.zeros((S, T, n_asset)) if capture_balances else None

    for t in range(T):
        if capture_balances:
            bal_begin[:, t, :] = B.sum(axis=1)     # beginning = end of previous period

        yld_t = returns.income_yield[:, t, :]      # (Sr, n_asset), Sr in {1, S}
        cap_t = returns.capital_return[:, t, :]    # (Sr, n_asset)

        # 4. Investment income on beginning balances, paid into each account's cash.
        income_cell = B * yld_t[:, None, :]            # (S, acct, asset)
        acct_income = income_cell.sum(axis=2)          # (S, acct)
        inv_income = income_cell.sum(axis=(1, 2))      # (S,)
        # Taxable-account income split (from BEGINNING balances) for tax.
        interest_taxable = (B[:, TAXABLE, BONDS] * yld_t[:, BONDS]
                            + B[:, TAXABLE, CASH] * yld_t[:, CASH])
        dividend_taxable = B[:, TAXABLE, STOCKS] * yld_t[:, STOCKS]

        B[:, :, CASH] += acct_income                   # income becomes cash in-account

        # 5. Income tax (accrual).
        tax_inc = income_tax(interest_taxable, dividend_taxable, inc.taxable[t], config.tax_rates)

        # 5b. Pre-retirement savings: invest the contribution in the taxable account at the
        # current portfolio allocation (bought at market, so basis steps up by the amount).
        sv = savings[t]
        if sv > 0.0:
            asset_tot = B.sum(axis=1)                        # (S, n_asset) across accounts
            port = asset_tot.sum(axis=1, keepdims=True)      # (S, 1)
            weights = np.divide(asset_tot, port, out=np.zeros_like(asset_tot), where=port > 0)
            contrib = sv * weights                           # (S, n_asset)
            contrib[(port[:, 0] == 0.0), CASH] += sv         # nothing invested yet -> cash
            B[:, TAXABLE, :] += contrib
            basis += contrib

        # 6. Fund from the spendable pool (external + taxable cash) first.
        taxable_cash = B[:, TAXABLE, CASH]
        pool = inc.total[t] + taxable_cash
        need = plan[t] + tax_inc
        B[:, TAXABLE, CASH] = np.maximum(pool - need, 0.0)   # surplus accumulates as cash
        delta = np.maximum(need - pool, 0.0)                 # shortfall to raise by selling

        # 7-8. Proportional sale with analytic gross-up (no-op where delta == 0).
        sale = proportional_sale(B, basis, delta, td_rate, gain_rate)
        B, basis = sale.balances, sale.basis

        # Actual spending funded: full plan when funded, else whatever the exhausted
        # resources cover (the shortfall is the failure). Keeps the reconciliation exact.
        net_sale = sale.gross - sale.tax
        spending_funded = np.where(
            sale.funded, plan[t], np.maximum(pool + net_sale - tax_inc, 0.0)
        )

        # 9. Apply capital returns to end-of-period balances.
        cap_amt = (B * cap_t[:, None, :]).sum(axis=(1, 2))
        B *= 1.0 + cap_t[:, None, :]

        # 10. Record.
        if capture_balances:
            bal_end[:, t, :] = B.sum(axis=1)       # consolidated end-of-period by asset
        net_worth[:, t] = B.sum(axis=(1, 2))
        spending_funded_a[:, t] = spending_funded
        inv_income_a[:, t] = inv_income
        cap_return_a[:, t] = cap_amt
        tax_income_a[:, t] = tax_inc
        tax_sale_a[:, t] = sale.tax
        sales_gross_a[:, t] = sale.gross
        realized_gain_a[:, t] = sale.realized_gain
        funded_a[:, t] = sale.funded

    return EngineResult(
        config=config,
        net_worth=net_worth,
        spending=plan,
        spending_funded=spending_funded_a,
        external_income=inc.total,
        savings=savings,
        investment_income=inv_income_a,
        capital_return=cap_return_a,
        tax_income=tax_income_a,
        tax_sale=tax_sale_a,
        sales_gross=sales_gross_a,
        realized_gain=realized_gain_a,
        funded=funded_a,
        balances_begin=bal_begin,
        balances_end=bal_end,
    )
