"""External income (pensions / Social Security) schedules.

Streams are nested under their owning person; each is active while that person's age is
in ``[start_age, end_age)``. Annual real
amounts convert to quarterly (``/4``); inflation-linked streams grow with overall
inflation, others stay fixed in nominal terms (eroding in real terms).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import RunConfig


@dataclass(frozen=True)
class IncomePath:
    """Deterministic nominal external income over the horizon."""

    total: np.ndarray    # (T,) nominal cash in
    taxable: np.ndarray  # (T,) nominal taxable portion


def build_external_income(config: RunConfig, overall_inflation_q: float) -> IncomePath:
    """Build the summed nominal external-income path and its taxable portion.

    Parameters
    ----------
    overall_inflation_q : float
        Constant quarterly overall inflation, used to index inflation-linked streams.
    """
    T = config.household.n_periods

    total = np.zeros(T)
    taxable = np.zeros(T)
    t = np.arange(T)
    infl_factor = np.power(1.0 + overall_inflation_q, t)

    for person in config.household.people:
        age = person.current_age + t / 4.0
        for s in person.income_streams:
            active = age >= s.start_age
            if s.end_age is not None:
                active &= age < s.end_age
            q_real = s.annual_real / 4.0
            nominal = np.where(active, q_real, 0.0)
            if s.inflation_linked:
                nominal = nominal * infl_factor
            total += nominal
            taxable += nominal * s.taxable_fraction
    return IncomePath(total=total, taxable=taxable)
