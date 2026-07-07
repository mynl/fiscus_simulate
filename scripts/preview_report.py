"""Generate a self-contained HTML preview of a simulation run — open locally, no server.

    uv run python scripts/preview_report.py [n_scenarios]

Writes ``dev/preview/report.html`` (gitignored). A stop-gap look at real engine output
until the Stage 6/7 web results pages exist; the polished, house-styled funnel lands in
Stage 7. Values are in real (today's-money) terms; the y-axis is log so the skew and the
failure floor are both visible.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

from fiscus_simulate.models import RunConfig
from fiscus_simulate.service import run_simulation

FLOOR = 1_000.0  # log-axis floor; percentile paths that hit ruin sit here
W, H = 920, 460
ML, MR, MT, MB = 70, 20, 30, 40  # plot margins


def _fmt_gbp(x: float) -> str:
    ax = abs(x)
    if ax >= 1e6:
        return f"£{x/1e6:.1f}M"
    if ax >= 1e3:
        return f"£{x/1e3:.0f}k"
    return f"£{x:.0f}"


def _svg(summary) -> str:
    pcts = summary.percentiles
    idx = {p: i for i, p in enumerate(pcts)}
    real = summary.net_worth_pctiles_real                    # (n_pct, T)
    T = real.shape[1]
    years = (np.arange(T) + 1) / 4.0

    ymax = max(float(real[idx[90]].max()), FLOOR * 10)
    ymin = FLOOR
    lymin, lymax = math.log10(ymin), math.log10(ymax)

    def px(year: float) -> float:
        return ML + (year / (T / 4.0)) * (W - ML - MR)

    def py(val: float) -> float:
        v = min(max(val, ymin), ymax)
        return MT + (1 - (math.log10(v) - lymin) / (lymax - lymin)) * (H - MT - MB)

    def band(lo_p: int, hi_p: int, fill: str) -> str:
        lo, hi = real[idx[lo_p]], real[idx[hi_p]]
        top = " ".join(f"{px(years[t]):.1f},{py(hi[t]):.1f}" for t in range(T))
        bot = " ".join(f"{px(years[t]):.1f},{py(lo[t]):.1f}" for t in range(T - 1, -1, -1))
        return f'<polygon points="{top} {bot}" fill="{fill}" stroke="none"/>'

    def line(p: int, stroke: str, w: float) -> str:
        pts = " ".join(f"{px(years[t]):.1f},{py(real[idx[p]][t]):.1f}" for t in range(T))
        return f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="{w}"/>'

    # gridlines at powers of ten
    grid = []
    k = math.ceil(lymin)
    while k <= lymax:
        val = 10 ** k
        y = py(val)
        grid.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{W-MR}" y2="{y:.1f}" '
                    f'stroke="#eee"/>'
                    f'<text x="{ML-8}" y="{y+4:.1f}" text-anchor="end" '
                    f'font-size="11" fill="#888">{_fmt_gbp(val)}</text>')
        k += 1
    xticks = []
    for yr in range(0, T // 4 + 1, 5):
        x = px(yr)
        xticks.append(f'<line x1="{x:.1f}" y1="{H-MB}" x2="{x:.1f}" y2="{H-MB+4}" stroke="#aaa"/>'
                      f'<text x="{x:.1f}" y="{H-MB+18}" text-anchor="middle" '
                      f'font-size="11" fill="#888">{yr}y</text>')

    return f'''<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px">
  {''.join(grid)}
  {band(10, 90, "#cfe3ee")}
  {band(25, 75, "#8fbdd6")}
  {line(50, "#0b5c8a", 2.5)}
  {''.join(xticks)}
  <line x1="{ML}" y1="{MT}" x2="{ML}" y2="{H-MB}" stroke="#ccc"/>
  <line x1="{ML}" y1="{H-MB}" x2="{W-MR}" y2="{H-MB}" stroke="#ccc"/>
</svg>'''


def _tiles(res) -> str:
    sm = res.summary
    rate = 100 * sm.overall_success_rate
    tmed = sm.terminal_pctiles_real[4]
    tp10, tp90 = sm.terminal_pctiles_real[2], sm.terminal_pctiles_real[6]
    cells = [
        ("Scenarios", f"{sm.n_scenarios:,}"),
        ("Success rate", f"{rate:.1f}%"),
        ("Terminal median (real)", _fmt_gbp(tmed)),
        ("Terminal p10 / p90 (real)", f"{_fmt_gbp(tp10)} / {_fmt_gbp(tp90)}"),
        ("Runtime", f"{res.meta['runtime_s']:.1f}s"),
    ]
    return "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in cells
    )


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20_000
    cfg = RunConfig.default().clone()
    cfg.simulation.n_scenarios = n
    res = run_simulation(cfg)

    html = f'''<!doctype html><html><head><meta charset="utf-8">
<title>fiscus_simulate — run preview</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 980px;
         color: #222; }}
  h1 {{ font-size: 1.25rem; }} .sub {{ color:#777; margin-top:-.4rem; }}
  .tiles {{ display:flex; flex-wrap:wrap; gap:.75rem; margin:1rem 0 1.5rem; }}
  .tile {{ border:1px solid #eee; border-radius:8px; padding:.6rem .9rem; min-width:150px; }}
  .tile .k {{ font-size:.75rem; color:#888; }} .tile .v {{ font-size:1.15rem; font-weight:600; }}
  .legend span {{ margin-right:1rem; font-size:.8rem; color:#555; }}
  .sw {{ display:inline-block; width:12px; height:12px; border-radius:2px; vertical-align:middle;
         margin-right:4px; }}
  .note {{ color:#999; font-size:.8rem; margin-top:1rem; }}
</style></head><body>
<h1>fiscus_simulate — net-worth funnel (preview)</h1>
<p class="sub">Default synthetic plan · real / today's-money terms · log scale</p>
<div class="tiles">{_tiles(res)}</div>
<div class="legend">
  <span><span class="sw" style="background:#0b5c8a"></span>median</span>
  <span><span class="sw" style="background:#8fbdd6"></span>25–75%</span>
  <span><span class="sw" style="background:#cfe3ee"></span>10–90%</span>
</div>
{_svg(res.summary)}
<p class="note">Percentiles at each date are cross-sectional — they do not trace one
continuous path. Paths at the £1k floor have run out (ruin). This is a stop-gap preview;
the house-styled interactive funnel arrives in Stage 7.</p>
</body></html>'''

    out = Path(__file__).resolve().parent.parent / "dev" / "preview" / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")
    print(f"  {n:,} scenarios · success {100*res.summary.overall_success_rate:.1f}%")


if __name__ == "__main__":
    main()
