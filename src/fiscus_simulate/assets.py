"""Account/asset balance mechanics: the proportional sale with analytic tax gross-up.

Array layout (matches enum order, see ``models``):
accounts ``taxable=0, tax_deferred=1, tax_free=2``; assets ``stocks=0, bonds=1, cash=2``.
Balances are ``(S, 3, 3)`` = ``(scenario, account, asset)``; taxable cost basis is
``(S, 3)`` per asset.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Account indices
TAXABLE, TAX_DEFERRED, TAX_FREE = 0, 1, 2
# Asset indices
STOCKS, BONDS, CASH = 0, 1, 2

_EPS = 1e-9


@dataclass
class SaleResult:
    """Outcome of a proportional sale raising ``delta`` net-of-tax cash per scenario."""

    balances: np.ndarray      # (S, 3, 3) after the sale
    basis: np.ndarray         # (S, 3) taxable basis after the sale
    gross: np.ndarray         # (S,) gross amount sold, G
    tax: np.ndarray           # (S,) sale tax
    realized_gain: np.ndarray  # (S,) realized taxable capital gain
    funded: np.ndarray        # (S,) bool: was delta fully raised?


def proportional_sale(
    balances: np.ndarray,
    basis: np.ndarray,
    delta: np.ndarray,
    td_rate: float,
    gain_rate: float,
) -> SaleResult:
    """Sell proportionally across all cells to raise ``delta`` net-of-tax cash.

    The sale is spread across every cell by its share of sellable wealth. Because the
    weights are fixed, the sale tax is linear in the gross amount ``G``: ``tax = G*tau``
    with ``tau`` the wealth-weighted per-cell tax rate (tax-deferred withdrawal rate for
    tax-deferred cells; ``gain_rate * embedded_gain_ratio`` for taxable stock/bond cells;
    zero for tax-free cells and cash). Solving ``G*(1-tau) = delta`` gives ``G`` in closed
    form — no iteration. If ``tau >= 1`` or the portfolio cannot cover ``G``, everything
    sellable is sold and the scenario is flagged unfunded for the period.

    Parameters
    ----------
    balances : ndarray, shape (S, 3, 3)
        Current balances (taxable cash already applied to the pool by the caller).
    basis : ndarray, shape (S, 3)
        Taxable-account cost basis by asset.
    delta : ndarray, shape (S,)
        Net cash still needed per scenario (0 where nothing must be sold).
    td_rate, gain_rate : float
        Tax-deferred withdrawal rate; realized capital-gain rate.
    """
    balances = balances.astype(float, copy=True)
    basis = basis.astype(float, copy=True)
    delta = np.asarray(delta, dtype=float)
    S = balances.shape[0]

    # Embedded gain ratio for taxable stocks & bonds (cash never has a gain).
    market_tx = balances[:, TAXABLE, :]              # (S, 3)
    with np.errstate(divide="ignore", invalid="ignore"):
        gain_ratio = np.where(
            market_tx > _EPS, (market_tx - basis) / np.where(market_tx > _EPS, market_tx, 1.0), 0.0
        )
    gain_ratio = np.clip(gain_ratio, 0.0, 1.0)
    gain_ratio[:, CASH] = 0.0

    # Per-cell effective tax rate on a sale.
    r = np.zeros_like(balances)
    r[:, TAXABLE, STOCKS] = gain_rate * gain_ratio[:, STOCKS]
    r[:, TAXABLE, BONDS] = gain_rate * gain_ratio[:, BONDS]
    r[:, TAX_DEFERRED, :] = td_rate

    sellable_total = balances.sum(axis=(1, 2))       # (S,)
    safe_total = np.where(sellable_total > _EPS, sellable_total, 1.0)
    weights = balances / safe_total[:, None, None]
    tau = (weights * r).sum(axis=(1, 2))             # (S,)

    denom = 1.0 - tau
    needed_g = np.where(denom > _EPS, delta / np.where(denom > _EPS, denom, 1.0), np.inf)
    needs_sale = delta > _EPS
    capped = needs_sale & (needed_g > sellable_total + _EPS)
    gross = np.where(needs_sale, np.minimum(needed_g, sellable_total), 0.0)
    funded = ~capped

    sold = weights * gross[:, None, None]            # (S, 3, 3)
    tax = (sold * r).sum(axis=(1, 2))
    realized_gain = (
        sold[:, TAXABLE, STOCKS] * gain_ratio[:, STOCKS]
        + sold[:, TAXABLE, BONDS] * gain_ratio[:, BONDS]
    )

    # Reduce taxable stock/bond basis in proportion to the fraction sold.
    sold_sb = sold[:, TAXABLE, STOCKS:BONDS + 1]     # (S, 2)
    market_sb = market_tx[:, STOCKS:BONDS + 1]
    sold_frac = np.where(market_sb > _EPS, sold_sb / np.where(market_sb > _EPS, market_sb, 1.0), 0.0)
    basis[:, STOCKS:BONDS + 1] *= 1.0 - sold_frac

    balances -= sold
    return SaleResult(
        balances=balances, basis=basis, gross=gross, tax=tax,
        realized_gain=realized_gain, funded=funded.astype(bool).reshape(S),
    )


# Default liquidation priority: spend taxable first, then tax-deferred, preserve tax-free.
DEFAULT_SALE_ORDER: tuple[int, ...] = (TAXABLE, TAX_DEFERRED, TAX_FREE)


def ordered_sale(
    balances: np.ndarray,
    basis: np.ndarray,
    delta: np.ndarray,
    td_rate: float,
    gain_rate: float,
    order: tuple[int, ...] = DEFAULT_SALE_ORDER,
) -> SaleResult:
    """Sell to raise ``delta`` net-of-tax cash, draining accounts in priority ``order``.

    The conventional tax-efficient sequence (default taxable → tax-deferred → tax-free):
    fully exhaust each account before touching the next, selling *proportionally across
    assets within* an account. Because each account has a single blended sale-tax rate
    ``tau_acct`` (fixed weights within the account), the gross-up stays closed-form —
    ``G = remaining / (1 - tau_acct)`` per tranche, no iteration — so the whole strategy
    solves for tax analytically, one account at a time.

    Parameters
    ----------
    balances : ndarray, shape (S, 3, 3)
        Current balances (spendable cash already applied to the pool by the caller).
    basis : ndarray, shape (S, 3)
        Taxable-account cost basis by asset.
    delta : ndarray, shape (S,)
        Net cash still needed per scenario (0 where nothing must be sold).
    td_rate, gain_rate : float
        Tax-deferred withdrawal rate; realized capital-gain rate.
    order : tuple of int
        Account indices in draw-down priority (default :data:`DEFAULT_SALE_ORDER`).

    Notes
    -----
    Returns the same :class:`SaleResult` as :func:`proportional_sale`; ``funded`` is False
    where the ordered accounts cannot raise ``delta``. Realized gain and basis step-down
    apply to the taxable account only.
    """
    balances = balances.astype(float, copy=True)
    basis = basis.astype(float, copy=True)
    S = balances.shape[0]
    remaining = np.maximum(np.asarray(delta, dtype=float), 0.0)

    gross = np.zeros(S)
    tax = np.zeros(S)
    realized_gain = np.zeros(S)

    for acct in order:
        market = balances[:, acct, :]                    # (S, 3) view
        # Per-asset effective sale-tax rate within this account.
        r = np.zeros((S, 3))
        gain_ratio = np.zeros((S, 3))
        if acct == TAXABLE:
            with np.errstate(divide="ignore", invalid="ignore"):
                gain_ratio = np.where(
                    market > _EPS, (market - basis) / np.where(market > _EPS, market, 1.0), 0.0
                )
            gain_ratio = np.clip(gain_ratio, 0.0, 1.0)
            gain_ratio[:, CASH] = 0.0
            r[:, STOCKS] = gain_rate * gain_ratio[:, STOCKS]
            r[:, BONDS] = gain_rate * gain_ratio[:, BONDS]
        elif acct == TAX_DEFERRED:
            r[:] = td_rate
        # TAX_FREE: rate stays zero.

        acct_total = market.sum(axis=1)                  # (S,)
        safe = np.where(acct_total > _EPS, acct_total, 1.0)
        weights = market / safe[:, None]
        tau = (weights * r).sum(axis=1)                  # (S,)

        need_here = remaining > _EPS
        denom = 1.0 - tau
        g_full = np.where(denom > _EPS, remaining / np.where(denom > _EPS, denom, 1.0), np.inf)
        g = np.where(need_here, np.minimum(g_full, acct_total), 0.0)

        sold = weights * g[:, None]                      # (S, 3)
        t_here = (sold * r).sum(axis=1)
        net_here = g - t_here

        if acct == TAXABLE:
            realized_gain += (sold[:, STOCKS] * gain_ratio[:, STOCKS]
                              + sold[:, BONDS] * gain_ratio[:, BONDS])
            sold_sb = sold[:, STOCKS:BONDS + 1]
            market_sb = market[:, STOCKS:BONDS + 1]
            sold_frac = np.where(
                market_sb > _EPS, sold_sb / np.where(market_sb > _EPS, market_sb, 1.0), 0.0
            )
            basis[:, STOCKS:BONDS + 1] *= 1.0 - sold_frac

        balances[:, acct, :] = market - sold
        gross += g
        tax += t_here
        remaining = np.maximum(remaining - net_here, 0.0)

    funded = remaining <= _EPS
    return SaleResult(
        balances=balances, basis=basis, gross=gross, tax=tax,
        realized_gain=realized_gain, funded=funded.astype(bool).reshape(S),
    )
