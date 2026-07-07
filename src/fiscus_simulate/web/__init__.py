"""Flask web layer for fiscus_simulate (optional ``web`` extra).

Standalone: this app clones the Fiscus house style but never imports ``fiscus_project``.
It talks to the engine only through :mod:`fiscus_simulate.service`.
"""
from __future__ import annotations
