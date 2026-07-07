"""Abstract return-generator interface and the shared returns contract.

A generator maps ``(n_scenarios, horizon, asset definitions, inflation, seed, params)``
to aligned NumPy arrays. Efficient array representations only — never one Python object
per scenario-period.

:class:`ReturnsBundle` exposes the realized *return environment* (``nominal_total``) as a
first-class array so later sequence-of-returns analysis (Stage 8) can hold it fixed and
permute the time axis without re-running the generator.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from ..models import RunConfig


@dataclass(frozen=True)
class ReturnsBundle:
    """Per-scenario, per-period quarterly return arrays (``ASSET_CLASSES`` column order).

    Attributes
    ----------
    capital_return, income_yield, nominal_total : ndarray, shape (S, T, n_asset)
        Capital return applied to balances; deterministic income yield; and the realized
        nominal total return (the return environment). ``S`` may be 1 (deterministic,
        broadcast over scenarios) or the full scenario count.
    overall_inflation_q : float
        Constant quarterly overall inflation (V1).
    """

    capital_return: np.ndarray
    income_yield: np.ndarray
    nominal_total: np.ndarray
    overall_inflation_q: float

    @property
    def n_scenarios(self) -> int:
        return self.capital_return.shape[0]

    @property
    def n_periods(self) -> int:
        return self.capital_return.shape[1]


class ReturnGenerator(ABC):
    """Base class for return generators. Subclasses use the ``ReturnsBundle`` contract."""

    def __init__(self, config: RunConfig) -> None:
        self.config = config

    @abstractmethod
    def generate(self, n_scenarios: int) -> ReturnsBundle:
        """Produce a :class:`ReturnsBundle` for ``n_scenarios`` paths."""
        raise NotImplementedError
