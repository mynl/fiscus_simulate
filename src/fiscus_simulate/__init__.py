"""fiscus_simulate — retirement cash-flow and asset Monte-Carlo simulation.

A two-person-household retirement simulator: a vectorized NumPy engine (Stage 2+)
surrounded by typed configuration, persistence, and an optional Flask web layer. The
engine is the core asset and must never import Flask.

This package stands alone. ``fiscus_project`` may import it; it never imports
``fiscus_project``.
"""
from __future__ import annotations

__version__ = "1.8.0"

from .models import RunConfig  # noqa: E402  (re-export the top-level config model)

__all__ = ["RunConfig", "__version__"]
