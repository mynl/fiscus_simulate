"""Small presentation helpers for the web layer (formatting, etc.).

Kept separate from routes so view logic doesn't accrete in request handlers. Grows in
Stage 6/7; intentionally thin in Stage 1.
"""
from __future__ import annotations


def fmt_money(x: float) -> str:
    """Format a number as a thousands-separated integer amount (e.g. ``1,234``)."""
    return f"{x:,.0f}"
