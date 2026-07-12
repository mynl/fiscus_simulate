"""Quarterly retirement simulation engine (vectorized NumPy).

Stage 2: a deterministic single-path engine (scenario axis present, size 1) that becomes
the correctness backbone. The period loop is Python (160 quarters); everything inside is
vectorized over the scenario axis so Stage 4 scales to many paths unchanged. This module
never imports Flask; the web layer reaches it via :mod:`fiscus_simulate.service`.

Order of operations (1.9.0, standard life-actuarial timing — **expense BOP, income EOP**):
spending is paid at the start of the quarter from taxable cash (targeted by the prior
quarter, so no start-of-quarter sale is normally needed); investment income, capital
return and external income (pensions / Social Security) land at end of quarter; RMDs are
forced from tax-deferred accounts once the elder person reaches ``rmd_start_age``; then a
single end-of-quarter reconciliation refills cash to *next* quarter's spend — investing
any surplus in taxable stocks/bonds, or selling (ordered, tax-efficient) any shortfall —
and all tax is settled. The reconciliation identity is unchanged in form and checked by
tests:

    W_end = W_begin + external_income + investment_income + capital_return
            + savings - spending - tax
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .assets import BONDS, CASH, STOCKS, TAX_DEFERRED, TAXABLE, ordered_sale, proportional_sale
from .income import build_external_income
from .models import ACCOUNT_TYPES, ASSET_CLASSES, RunConfig
from .returns.base import ReturnsBundle
from .returns.deterministic import build_deterministic_returns
from .rmd import rmd_fraction
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
    # Per-account detail for the "By account" walk (S, T, n_acct[, n_asset]).
    balances_begin_acct: np.ndarray | None = None  # (S, T, n_acct, n_asset) beginning
    income_acct: np.ndarray | None = None          # (S, T, n_acct) investment income
    capital_acct: np.ndarray | None = None         # (S, T, n_acct) capital return

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
    # End-of-quarter cash target = *next* quarter's planned spend (0 past the horizon).
    next_plan = np.zeros(T)
    next_plan[:-1] = plan[1:]

    # Liquidation strategy + RMD settings.
    wp = config.withdrawal_policy
    order_idx = tuple(ACCOUNT_TYPES.index(a) for a in wp.order)
    elder_age0 = max(p.current_age for p in config.household.people)

    def raise_cash(bal, bas, d):
        """Raise ``d`` net cash from non-cash assets (ordered or proportional)."""
        if wp.kind == "ordered":
            return ordered_sale(bal, bas, d, td_rate, gain_rate, order=order_idx)
        return proportional_sale(bal, bas, d, td_rate, gain_rate)

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
    bal_begin_acct = np.zeros((S, T, n_acct, n_asset)) if capture_balances else None
    income_acct_a = np.zeros((S, T, n_acct)) if capture_balances else None
    capital_acct_a = np.zeros((S, T, n_acct)) if capture_balances else None

    for t in range(T):
        if capture_balances:
            bal_begin[:, t, :] = B.sum(axis=1)     # beginning = end of previous period
            bal_begin_acct[:, t, :, :] = B         # per-account beginning balances

        yld_t = returns.income_yield[:, t, :]      # (Sr, n_asset), Sr in {1, S}
        cap_t = returns.capital_return[:, t, :]    # (Sr, n_asset)

        # --- BOP: pay the FULL planned spend from taxable cash (targeted by the prior
        #     quarter). V1 keeps spending even when assets run out: the shortfall becomes
        #     negative cash (debt) and the EOP reconciliation sells what it can — so ruin
        #     is exposed as a negative net worth, not smoothed by cutting the plan. ---
        B[:, TAXABLE, CASH] -= plan[t]
        spending_funded = plan[t]

        # --- Through the quarter: income accrues on the invested (post-spend) balances,
        #     then capital return applies; income is credited as cash. ---
        income_cell = B * yld_t[:, None, :]            # (S, acct, asset)
        acct_income = income_cell.sum(axis=2)          # (S, acct)
        inv_income = income_cell.sum(axis=(1, 2))      # (S,)
        interest_taxable = (B[:, TAXABLE, BONDS] * yld_t[:, BONDS]
                            + B[:, TAXABLE, CASH] * yld_t[:, CASH])
        dividend_taxable = B[:, TAXABLE, STOCKS] * yld_t[:, STOCKS]

        cap_cell = B * cap_t[:, None, :]
        cap_amt = cap_cell.sum(axis=(1, 2))
        if capture_balances:
            income_acct_a[:, t, :] = acct_income        # investment income per account
            capital_acct_a[:, t, :] = cap_cell.sum(axis=2)  # capital return per account
        B *= 1.0 + cap_t[:, None, :]                    # EOP capital return
        B[:, :, CASH] += acct_income                    # income becomes cash in-account

        # --- EOP: external income + pre-retirement savings arrive as taxable cash. ---
        B[:, TAXABLE, CASH] += inc.total[t] + savings[t]

        tax_inc = income_tax(interest_taxable, dividend_taxable, inc.taxable[t], config.tax_rates)

        # --- RMD: force a tax-deferred withdrawal once the elder reaches rmd_start_age. ---
        rmd_tax = np.zeros(S)
        if wp.rmd_enabled:
            age = elder_age0 + t / 4.0
            frac = rmd_fraction(age)
            if age >= wp.rmd_start_age and frac > 0.0:
                td_total = B[:, TAX_DEFERRED, :].sum(axis=1)
                rmd = td_total * (frac / 4.0)           # quarterly slice of the annual RMD
                safe_td = np.where(td_total > 1e-12, td_total, 1.0)
                w_td = B[:, TAX_DEFERRED, :] / safe_td[:, None]
                B[:, TAX_DEFERRED, :] -= w_td * rmd[:, None]
                B[:, TAXABLE, CASH] += rmd              # withdrawn to spendable cash
                rmd_tax = td_rate * rmd

        t0 = tax_inc + rmd_tax                          # tax owed before the cash-target sale

        # --- EOP reconciliation to next quarter's cash target. Set the buffer aside so it
        #     is not "sold", then raise a shortfall (ordered) or invest a surplus. ---
        target = next_plan[t]
        buffer = B[:, TAXABLE, CASH].copy()
        B[:, TAXABLE, CASH] = 0.0
        need = t0 + target - buffer                     # net cash to raise (< 0 = surplus)

        sale = raise_cash(B, basis, np.maximum(need, 0.0))  # no-op where need <= 0
        B, basis = sale.balances, sale.basis
        raised = sale.gross - sale.tax                  # net raised (== need if funded)
        # Not floored at zero: when assets are exhausted this stays negative (debt).
        final_cash = buffer + raised - t0

        # Surplus: invest what exceeds the target in taxable stocks/bonds at the overall
        # stock:bond mix (cash-only portfolio has nowhere to invest -> surplus stays cash).
        surplus = np.where(need < 0.0, np.maximum(final_cash - target, 0.0), 0.0)
        tot_s, tot_b = B[:, :, STOCKS].sum(axis=1), B[:, :, BONDS].sum(axis=1)
        sb = tot_s + tot_b
        safe_sb = np.where(sb > 1e-12, sb, 1.0)
        inv_s = surplus * np.where(sb > 1e-12, tot_s / safe_sb, 0.0)
        inv_b = surplus * np.where(sb > 1e-12, tot_b / safe_sb, 0.0)
        B[:, TAXABLE, STOCKS] += inv_s
        B[:, TAXABLE, BONDS] += inv_b
        basis[:, STOCKS] += inv_s
        basis[:, BONDS] += inv_b
        final_cash = np.where(need < 0.0, target + (surplus - inv_s - inv_b), final_cash)
        B[:, TAXABLE, CASH] = final_cash

        # --- Record. ---
        if capture_balances:
            bal_end[:, t, :] = B.sum(axis=1)       # consolidated end-of-period by asset
        net_worth[:, t] = B.sum(axis=(1, 2))
        spending_funded_a[:, t] = spending_funded
        inv_income_a[:, t] = inv_income
        cap_return_a[:, t] = cap_amt
        tax_income_a[:, t] = tax_inc
        tax_sale_a[:, t] = rmd_tax + sale.tax
        sales_gross_a[:, t] = sale.gross
        realized_gain_a[:, t] = sale.realized_gain
        # "Funded" = solvent: spending is always fully paid (via debt if needed), so the
        # meaningful failure is net worth going negative.
        funded_a[:, t] = net_worth[:, t] >= -1e-6

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
        balances_begin_acct=bal_begin_acct,
        income_acct=income_acct_a,
        capital_acct=capital_acct_a,
    )
