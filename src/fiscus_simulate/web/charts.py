"""Server-side uPlot chart blocks for the results view.

The Python side builds JSON-serializable ``data`` (uPlot's ``[xs, ys...]`` form) and a
``spec`` describing series/type/formatting; the JS helper ``fiscusChart`` (defined once in
``base.html``, after the uPlot CDN load) turns them into a chart, adding the hover/axis
formatter *functions* that can't ride in JSON. This mirrors ``fiscus_project``'s inline
``new uPlot(...)`` pattern. Charts are presentation-only — fed from persisted summaries.
"""
from __future__ import annotations

import json

from markupsafe import Markup

# Colorblind-friendly, works in light/dark. Median strong; bands translucent.
BAND_OUTER = "rgba(13,110,253,0.12)"
BAND_INNER = "rgba(13,110,253,0.22)"
LINE_MEDIAN = "#0d6efd"
LINE_ALT = "#d63384"
BAR_FILL = "#0d6efd"


def chart_block(div_id: str, data: list, spec: dict, *, height: int = 320) -> Markup:
    """Return the ``<div>`` + inline ``fiscusChart`` call for one chart."""
    spec = {**spec, "height": height}
    return Markup(
        f'<div id="{div_id}" class="uplot-host" style="width:100%;height:{height}px;"></div>\n'
        f'<script>fiscusChart({json.dumps(div_id)}, {json.dumps(data)}, {json.dumps(spec)});</script>'
    )
