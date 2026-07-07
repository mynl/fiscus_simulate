"""V1 correlated GBM / lognormal return generator for stocks, bonds, cash.

Real expected returns are primary; nominal derived via ``1+R = (1+r)(1+pi)``. Income
yield and capital return kept separate. In V1 inflation is constant (deterministic),
so the generator emits constant inflation arrays.

Placeholder for Stage 3 — see ``dev/plan-overview.md``.
"""
from __future__ import annotations
