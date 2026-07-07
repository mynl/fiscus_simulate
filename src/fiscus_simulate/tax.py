"""Flat marginal tax by income type (V1), with a transparent per-type breakdown.

Income tax is levied on **taxable-account** interest/dividends and on the taxable part
of external income. Tax-deferred and tax-free investment income is not taxed on accrual
(tax-deferred is taxed on withdrawal, handled in the sale gross-up; tax-free never).
"""
from __future__ import annotations

import numpy as np

from .models import TaxRates


def income_tax(
    interest_taxable,
    dividend_taxable,
    external_taxable,
    rates: TaxRates,
):
    """Accrual income tax for a period (vectorized over scenarios).

    Parameters
    ----------
    interest_taxable, dividend_taxable : array_like
        Taxable-account interest and dividend income this period.
    external_taxable : array_like
        Taxable portion of external (pension) income this period.
    rates : TaxRates
        Flat marginal rates by income type.

    Returns
    -------
    ndarray
        Total income tax per scenario.
    """
    interest_taxable = np.asarray(interest_taxable, dtype=float)
    dividend_taxable = np.asarray(dividend_taxable, dtype=float)
    external_taxable = np.asarray(external_taxable, dtype=float)
    return (
        rates.interest * interest_taxable
        + rates.dividend * dividend_taxable
        + rates.other_pension * external_taxable
    )
