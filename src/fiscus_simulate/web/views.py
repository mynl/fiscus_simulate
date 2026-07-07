"""Small presentation helpers for the web layer (formatting, error rendering).

Kept separate from routes so view logic doesn't accrete in request handlers.
"""
from __future__ import annotations

import yaml
from pydantic import ValidationError


def fmt_money(x: float) -> str:
    """Format a number as a thousands-separated integer amount (e.g. ``1,234``)."""
    return f"{x:,.0f}"


def fmt_pct(x: float) -> str:
    """Format a 0-1 fraction as a one-decimal percentage (e.g. ``52.3%``)."""
    return f"{100 * x:.1f}%"


def format_config_error(exc: Exception) -> list[str]:
    """Render a config-parse/validation failure as a list of readable messages.

    Parameters
    ----------
    exc : Exception
        Typically a pydantic ``ValidationError`` (field-level), a ``yaml.YAMLError``
        (malformed YAML), or a plain ``ValueError`` from the schema check.

    Returns
    -------
    list of str
        One human-readable line per problem, suitable for a Bootstrap alert list.
    """
    if isinstance(exc, ValidationError):
        out = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(root)"
            out.append(f"{loc}: {err['msg']}")
        return out
    if isinstance(exc, yaml.YAMLError):
        return [f"YAML syntax error: {exc}"]
    return [str(exc)]
