"""Quarterly retirement simulation engine (vectorized NumPy).

Stage 2 (deterministic engine) and Stage 4 (vectorized multi-path) land here. This
module must never import Flask. The web layer reaches the engine only via
:mod:`fiscus_simulate.service`.

Placeholder for Stage 2 — see ``dev/plan-overview.md``.
"""
from __future__ import annotations
