"""Server-side table rendering via csv-grid, with a graceful fallback.

csv-grid (``from csv_grid import to_html``) renders a DataFrame as a self-contained,
interactive grid — sort, filter, fzf search, export — and is built to handle large CSVs.
It is a normal PyPI dependency of the ``web`` extra (``csv-grid``). The static
Bootstrap-table fallback here is defensive only — for a headless install that pulled the
engine without the ``web`` extra — so the page still renders and tests stay hermetic.

Kept out of the engine import path; the web layer is the only caller.
"""
from __future__ import annotations

import pandas as pd
from markupsafe import Markup


def has_csv_grid() -> bool:
    """Return True if csv-grid is importable in this environment."""
    try:
        import csv_grid  # noqa: F401

        return True
    except ImportError:
        return False


def render_table(df: pd.DataFrame, *, name: str | None = None) -> Markup:
    """Render ``df`` as an interactive csv-grid, or a static table if unavailable."""
    try:
        from csv_grid import to_html
    except ImportError:
        return Markup(_bootstrap_table(df))
    return Markup(to_html(df, name=name, theme="auto"))


def _bootstrap_table(df: pd.DataFrame) -> str:
    """Static fallback: a plain Bootstrap table (no JS)."""
    html = df.to_html(
        index=False,
        border=0,
        classes="table table-sm table-striped align-middle",
        float_format=lambda x: f"{x:,.1f}",
        na_rep="",
    )
    return f'<div class="table-responsive">{html}</div>'
