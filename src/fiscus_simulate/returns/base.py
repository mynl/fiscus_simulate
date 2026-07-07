"""Abstract return-generator interface.

A generator maps (n_scenarios, n_periods, asset definitions, inflation, RNG/seed,
params) to aligned arrays for nominal/real total return, income yield, capital return,
overall inflation and category inflation. Efficient array representations only — never
one Python object per scenario-period.

The interface exposes the realized *return environment* per path as a first-class
object so later sequence-of-returns analysis (Stage 8) can hold it fixed and permute
its order without re-running the generator.

Placeholder for Stage 3 — see ``dev/plan-overview.md``.
"""
from __future__ import annotations
