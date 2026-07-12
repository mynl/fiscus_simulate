"""Web routes (single blueprint).

Stage 6 adds the configuration workflow: a YAML config editor with server-side
validation, a named saved-config store, and a run launcher that persists results and
runs large jobs in the background (see :mod:`.jobs`). Results *rendering* — funnel,
charts, csv-grid tables — is Stage 7; here a run view shows only enough to confirm the
run completed and was persisted.
"""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

import numpy as np
import pandas as pd

from ..config import from_yaml_str, to_yaml_str
from ..models import RunConfig
from ..preview import config_preview
from . import charts, configs
from .grid import render_table
from .views import format_config_error

bp = Blueprint("simulate", __name__)


def _state():
    return current_app.config["APP_STATE"]


def _jobs():
    return current_app.config["JOBS"]


# --------------------------------------------------------------------------- dashboard
@bp.route("/")
def dashboard():
    """Landing page: saved configurations and recent runs."""
    from .. import storage

    state = _state()
    saved = configs.list_configs(state.configs_dir)
    try:
        runs = storage.list_runs(runs_dir=state.runs_dir)
    except FileNotFoundError:
        runs = []
    return render_template(
        "fiscus_simulate/dashboard.html", state=state, saved=saved, runs=runs[:10]
    )


# ------------------------------------------------------------------------ config editor
@bp.route("/config/new")
def config_new():
    """Open the editor seeded from a starter configuration.

    ``?template=generic`` seeds a fully-populated accumulation-phase demo (still saving);
    anything else seeds the retired two-person default.
    """
    cfg = RunConfig.generic() if request.args.get("template") == "generic" \
        else RunConfig.default()
    return render_template(
        "fiscus_simulate/config_edit.html",
        state=_state(),
        name="",
        yaml_text=to_yaml_str(cfg),
        errors=[],
        is_saved=False,
        preview=config_preview(cfg),
    )


@bp.route("/config/<name>")
def config_edit(name: str):
    """Open a saved configuration in the editor, with a config-derived preview."""
    state = _state()
    if not configs.exists(state.configs_dir, name):
        abort(404)
    cfg = configs.load(state.configs_dir, name)
    return render_template(
        "fiscus_simulate/config_edit.html",
        state=state,
        name=name,
        yaml_text=to_yaml_str(cfg),
        errors=[],
        is_saved=True,
        preview=config_preview(cfg),
    )


@bp.route("/config", methods=["POST"])
def config_save():
    """Validate and save the edited YAML under the given name.

    On any parse/validation failure the editor re-renders with the submitted text
    preserved and the errors listed — never a 500.
    """
    state = _state()
    raw_name = request.form.get("name", "")
    yaml_text = request.form.get("yaml", "")
    name = configs.slugify(raw_name)

    errors: list[str] = []
    if not configs.valid_name(name):
        errors.append(
            f"invalid config name {raw_name!r}: use letters, digits, '-' or '_' "
            "(must start with a letter or digit)."
        )
    cfg = None
    try:
        cfg = from_yaml_str(yaml_text)
    except Exception as exc:  # noqa: BLE001 - render any parse/validation failure inline
        errors.extend(format_config_error(exc))

    if errors or cfg is None:
        return render_template(
            "fiscus_simulate/config_edit.html",
            state=state,
            name=raw_name,
            yaml_text=yaml_text,
            errors=errors,
            is_saved=configs.valid_name(name) and configs.exists(state.configs_dir, name),
        )

    configs.save(state.configs_dir, name, cfg)
    flash(f"Saved configuration '{name}'.", "success")
    return redirect(url_for("simulate.config_edit", name=name))


@bp.route("/config/<name>/delete", methods=["POST"])
def config_delete(name: str):
    """Delete a saved configuration."""
    if configs.delete(_state().configs_dir, name):
        flash(f"Deleted configuration '{name}'.", "success")
    return redirect(url_for("simulate.dashboard"))


# ---------------------------------------------------------------------------- run launch
@bp.route("/config/<name>/run", methods=["POST"])
def config_run(name: str):
    """Launch a simulation from a saved configuration and go to its status/result."""
    state = _state()
    if not configs.exists(state.configs_dir, name):
        abort(404)
    cfg = configs.load(state.configs_dir, name)
    job = _jobs().submit(name, cfg, runs_dir=state.runs_dir)
    return redirect(url_for("simulate.job_view", job_id=job.job_id))


@bp.route("/jobs/<job_id>")
def job_view(job_id: str):
    """Route a launched job: finished → its run; running → a polling status page."""
    job = _jobs().get(job_id)
    if job is None:
        abort(404)
    if job.state == "complete" and job.run_id:
        return redirect(url_for("simulate.run_detail", run_id=job.run_id))
    return render_template("fiscus_simulate/job_status.html", state=_state(), job=job)


@bp.route("/jobs/<job_id>/status")
def job_status(job_id: str):
    """JSON job status polled by the status page while a background run is in flight."""
    job = _jobs().get(job_id)
    if job is None:
        abort(404)
    return jsonify(
        {"state": job.state, "run_id": job.run_id, "error": job.error,
         "n_scenarios": job.n_scenarios}
    )


# --------------------------------------------------------------------------------- runs
@bp.route("/runs")
def runs_list():
    """List persisted runs (newest first)."""
    from .. import storage

    state = _state()
    try:
        runs = storage.list_runs(runs_dir=state.runs_dir)
    except FileNotFoundError:
        runs = []
    return render_template("fiscus_simulate/runs.html", state=state, runs=runs)


@bp.route("/runs/<run_id>")
def run_detail(run_id: str):
    """Run view: headline metrics, the outcome distribution, then reproducibility."""
    from .. import storage

    state = _state()
    try:
        loaded = storage.load_run(run_id, runs_dir=state.runs_dir)
    except FileNotFoundError:
        abort(404)

    view = request.args.get("view", "percentile")
    if view == "terminal" and loaded.joint is None:
        view = "percentile"
    dist = _distribution_frame(loaded, view)

    scale = "real" if request.args.get("scale") == "real" else "nominal"
    labels = _period_labels(loaded.config)

    return render_template(
        "fiscus_simulate/run_detail.html",
        state=state,
        run=loaded,
        metadata=loaded.metadata,
        headline=_headline_metrics(loaded),
        dist_table=render_table(dist, name="outcome distribution") if dist is not None else None,
        view=view,
        has_joint=loaded.joint is not None,
        scale=scale,
        funnel=_funnel_block(loaded, scale, labels),
        histogram=_histogram_block(loaded),
        fail_timing=_fail_timing_block(loaded, labels),
        has_failures=bool(loaded.failures["first_failure_count"].sum() > 0),
    )


@bp.route("/runs/<run_id>/details")
def run_details(run_id: str):
    """See inside one scenario: pick a percentile, pick a scenario, walk it quarter by
    quarter, overlay it on the funnel, and run a throwaway order-of-returns experiment."""
    from .. import service, storage

    state = _state()
    try:
        loaded = storage.load_run(run_id, runs_dir=state.runs_dir)
    except FileNotFoundError:
        abort(404)

    scale = "real" if request.args.get("scale") == "real" else "nominal"
    tab = request.args.get("tab", "consolidated")
    labels = _period_labels(loaded.config)
    horizon = loaded.config.household.horizon_years

    outcomes = service.scenario_outcomes(loaded)
    terminal = outcomes["terminal_net_worth"]
    first_fail = outcomes["first_failure_period"]
    S = len(terminal)
    order = np.argsort(terminal, kind="stable")

    p = _clamp_pct(request.args.get("p", "50"))
    rank = int(np.clip(round(p / 100.0 * (S - 1)), 0, S - 1))
    lo, hi = max(0, rank - 5), min(S, rank + 6)
    picker = [_picker_row(int(i), terminal, first_fail, horizon) for i in order[lo:hi]]
    picker_indices = {row["index"] for row in picker}

    selected = _safe_int(request.args.get("scenario"))
    if selected is not None and not 0 <= selected < S:
        selected = None

    order_n = int(np.clip(_safe_int(request.args.get("n")) or 1000, 10, 20000))
    funnel = _funnel_block(loaded, scale, labels)
    walk_table = order_block = order_stats = scenario_info = None
    if selected is not None:
        walk = service.replay_scenario(loaded.config, selected)
        funnel = _funnel_block(loaded, scale, labels, overlay=("scenario", walk.net_worth))
        walk_table = render_table(_walk_frame(walk, labels), name=f"scenario {selected} walk")
        scenario_info = _scenario_info(walk, loaded.config, labels)
        result = service.resample_order(walk.bundle, loaded.config, n=order_n,
                                        seed=_safe_int(request.args.get("seed")))
        order_block = _order_block(result)
        order_stats = _order_stats(result, horizon)

    return render_template(
        "fiscus_simulate/run_details.html",
        state=state, run=loaded, scale=scale, tab=tab, p=("%g" % p),
        picker=picker, selected=selected, in_window=(selected in picker_indices),
        funnel=funnel, scenario_info=scenario_info, walk_table=walk_table,
        order_block=order_block, order_stats=order_stats,
        order_n=order_n, order_seed=request.args.get("seed", ""),
    )


@bp.route("/runs/compare")
def runs_compare():
    """Overlay two runs' net-worth funnels (median + p10/p90) and headline metrics."""
    from .. import storage

    state = _state()
    a_id, b_id = request.args.get("a"), request.args.get("b")
    try:
        runs = storage.list_runs(runs_dir=state.runs_dir)
    except FileNotFoundError:
        runs = []
    a = b = None
    if a_id:
        try:
            a = storage.load_run(a_id, runs_dir=state.runs_dir)
        except FileNotFoundError:
            a = None
    if b_id:
        try:
            b = storage.load_run(b_id, runs_dir=state.runs_dir)
        except FileNotFoundError:
            b = None

    scale = "real" if request.args.get("scale") == "real" else "nominal"
    block = headline = None
    if a is not None and b is not None:
        block = _compare_block(a, b, scale, _period_labels(a.config))
        headline = [
            (label, _headline_lookup(a, key), _headline_lookup(b, key))
            for label, key in _COMPARE_ROWS
        ]
    return render_template(
        "fiscus_simulate/compare.html",
        state=state, runs=runs, a=a, b=b, a_id=a_id, b_id=b_id,
        scale=scale, compare_block=block, headline=headline,
    )


@bp.route("/runs/<run_id>/delete", methods=["POST"])
def run_delete(run_id: str):
    """Delete a persisted run and its directory."""
    from .. import storage

    storage.delete_run(run_id, runs_dir=_state().runs_dir)
    flash(f"Deleted run {run_id}.", "success")
    return redirect(url_for("simulate.runs_list"))


def _fmt_pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _fmt_money(x: float) -> str:
    return f"{x:,.0f}"


def _headline_metrics(loaded) -> list[tuple[str, str]]:
    """Human-titled headline figures, most decision-relevant first."""
    m = {row["metric"]: row["value"] for _, row in loaded.summary.iterrows()}
    sc = {float(r["percentile"]): r for _, r in loaded.scalars.iterrows()}
    n = int(m.get("n_scenarios", 0))
    never = int(m.get("n_never_fail", 0))
    rows = [
        ("Overall success (every criterion met)", _fmt_pct(m.get("overall_success_rate", 0))),
        ("Spending plan fully funded", _fmt_pct(m.get("success_rate.all_planned_funded", 0))),
        ("Portfolio never goes negative", _fmt_pct(m.get("success_rate.portfolio_non_negative", 0))),
        ("Terminal wealth above threshold", _fmt_pct(m.get("success_rate.terminal_above_threshold", 0))),
        ("Scenarios that never fail", f"{never:,} of {n:,}"),
        ("Mean terminal net worth", _fmt_money(m.get("terminal.mean", 0))),
    ]
    if 50.0 in sc:
        rows.append(("Median terminal net worth", _fmt_money(sc[50.0]["terminal_nominal"])))
    return rows


# Distribution columns: (frame key, human header, is-money).
_DIST_COLS = [
    ("terminal_nominal", "Terminal net worth", True),
    ("min_net_worth", "Minimum net worth", True),
    ("years_funded", "Years funded", False),
    ("total_tax", "Taxes paid", True),
    ("total_sales", "Assets sold", True),
]


def _distribution_frame(loaded, view: str):
    """Build the transposed outcome table for the chosen view (mean row on top).

    ``view='percentile'`` uses the marginal per-column percentiles; ``view='terminal'``
    uses the joint frame (each row is one real scenario ranked by terminal net worth).
    """
    src = loaded.joint if view == "terminal" else loaded.scalars
    if src is None:
        return None
    means = loaded.metadata.get("scalar_means", {})
    have_mean = bool(means)
    pcts = [float(p) for p in src["percentile"]]
    labels = (["mean"] if have_mean else []) + [f"p{p:g}" for p in pcts]

    cols: dict[str, object] = {"level": labels}
    for key, header, is_money in _DIST_COLS:
        if key not in src.columns:
            continue
        prefix = [means[key]] if have_mean else []
        arr = np.asarray(prefix + list(src[key]), dtype=float)
        cols[header] = np.rint(arr).astype("int64") if is_money else np.round(arr, 1)
    return pd.DataFrame(cols)


# ------------------------------------------------------------------------ charts
def _period_labels(config) -> list[str]:
    """A ``"YYYY Qn"`` label per quarterly period, for chart hover/ticks."""
    start = config.household.start_date
    out = []
    for t in range(config.household.n_periods):
        m = start.month - 1 + 3 * t
        out.append(f"{start.year + m // 12} Q{(m % 12) // 3 + 1}")
    return out


def _pcol(dfp, p: float, scale: str):
    """A percentile column from the percentiles frame, deflated to real if asked."""
    v = dfp[f"p{p:g}"].to_numpy(dtype=float)
    return v / dfp["deflator"].to_numpy(dtype=float) if scale == "real" else v


def _funnel_block(loaded, scale: str, labels: list[str], overlay=None):
    """Net-worth funnel: median line with p10–p90 and p30–p70 shaded bands.

    ``overlay`` is an optional ``(label, nominal_array)`` single-scenario path drawn on top
    (Details view). Bands index the percentile series (1–5), so an appended overlay series
    at index 6 leaves them untouched.
    """
    dfp = loaded.percentiles
    x = list(range(len(dfp)))
    data = [x] + [list(_pcol(dfp, p, scale)) for p in (90, 70, 50, 30, 10)]
    spec = {
        "type": "line", "yMoney": True, "xLabels": labels, "xLabel": "quarter",
        "series": [
            {"label": "p90", "stroke": "rgba(0,0,0,0)", "width": 0},
            {"label": "p70", "stroke": "rgba(0,0,0,0)", "width": 0},
            {"label": "median", "stroke": charts.LINE_MEDIAN, "width": 2},
            {"label": "p30", "stroke": "rgba(0,0,0,0)", "width": 0},
            {"label": "p10", "stroke": "rgba(0,0,0,0)", "width": 0},
        ],
        "bands": [[1, 5, charts.BAND_OUTER], [2, 4, charts.BAND_INNER]],
    }
    if overlay is not None:
        label, arr = overlay
        y = np.asarray(arr, dtype=float)
        if scale == "real":
            y = y / dfp["deflator"].to_numpy(dtype=float)
        data.append(list(y))
        spec["series"].append({"label": label, "stroke": charts.LINE_ALT, "width": 2})
    return charts.chart_block("chart-funnel", data, spec, height=360)


def _histogram_block(loaded):
    """Terminal-wealth histogram (bars over wealth bins)."""
    h = loaded.terminal_hist
    if h is None or len(h) == 0:
        return None
    centers = ((h["left"].to_numpy() + h["right"].to_numpy()) / 2.0)
    data = [list(centers), list(h["count"].to_numpy(dtype=float))]
    spec = {
        "type": "bars", "xMoney": True, "yMoney": False, "xLabel": "terminal net worth",
        "series": [{"label": "scenarios", "stroke": charts.BAR_FILL, "fill": charts.BAND_INNER}],
    }
    return charts.chart_block("chart-terminal", data, spec, height=300)


def _fail_timing_block(loaded, labels: list[str]):
    """First-failure counts aggregated by year (bars)."""
    counts = loaded.failures["first_failure_count"].to_numpy(dtype=float)
    horizon = len(counts) // 4
    if horizon == 0:
        return None
    yearly = counts[: horizon * 4].reshape(horizon, 4).sum(axis=1)
    year_labels = [labels[4 * y][:4] for y in range(horizon)]  # the calendar year
    data = [list(range(horizon)), list(yearly)]
    spec = {
        "type": "bars", "yMoney": False, "xLabels": year_labels, "xLabel": "year",
        "series": [{"label": "first failures", "stroke": charts.LINE_ALT, "fill": "rgba(214,51,132,0.25)"}],
    }
    return charts.chart_block("chart-failtiming", data, spec, height=280)


# --------------------------------------------------------- details ("see inside")
def _safe_int(v):
    """Parse an int from a query arg; None on empty/invalid."""
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _clamp_pct(v) -> float:
    """Parse a percentile query arg into ``[0, 100]`` (default 50 on garbage)."""
    try:
        return float(np.clip(float(v), 0.0, 100.0))
    except (TypeError, ValueError):
        return 50.0


def _years_funded(first_fail: int, horizon: int) -> float:
    """Years of fully-funded spending: full horizon if never failed, else failure/4."""
    return float(horizon) if first_fail < 0 else first_fail / 4.0


def _picker_row(i: int, terminal, first_fail, horizon: int) -> dict:
    return {
        "index": i,
        "terminal": _fmt_money(float(terminal[i])),
        "years": f"{_years_funded(int(first_fail[i]), horizon):.1f}",
    }


def _walk_frame(walk, labels: list[str]) -> pd.DataFrame:
    """The consolidated quarter-by-quarter walk table (money rounded to whole dollars).

    Beginning balances by asset (ending = next period's beginning, so not repeated), then
    the flows. Reconciles: ``Total change = Income + Savings − Expense − Tax + Realized
    G/L + Δ Unrealized`` and ``End = Begin + Total change``. Capital return is split into
    the realized part (crystallized by sales) and the change in unrealized (the remainder).
    """
    c = walk.columns
    income = c["ext_income"] + c["invest_income"]
    total_change = c["end"] - c["begin"]
    df = pd.DataFrame({
        "Period": labels,
        "BOP Stocks": c["stocks"],
        "BOP Bonds": c["bonds"],
        "BOP Cash": c["cash"],
        "BOP Total": c["begin"],
        "Expense": c["spending"],
        "Income": income,
        "Savings": c["savings"],
        "Realized G/L": c["realized"],
        "Tax": c["tax"],
        "Δ Unrealized": c["unrealized"],
        "Total change": total_change,
    })
    money = [col for col in df.columns if col != "Period"]
    df[money] = df[money].round(0).astype("int64")
    return df


def _scenario_info(walk, config, labels: list[str]) -> list[tuple[str, str]]:
    """Headline tiles for the selected scenario."""
    ff = walk.first_failure_period
    if ff < 0:
        timing = "Never — plan funded throughout"
    else:
        timing = f"{labels[ff]} (year {ff // 4 + 1})"
    return [
        ("Scenario index", f"#{walk.index}"),
        ("Terminal net worth", _fmt_money(walk.terminal_net_worth)),
        ("First shortfall", timing),
    ]


def _order_block(result):
    """Histogram of terminal wealth across the order-of-returns reorderings."""
    term = np.asarray(result.terminal, dtype=float)
    lo = min(0.0, float(term.min()))
    hi = float(np.percentile(term, 99))
    if hi <= lo:
        hi = lo + 1.0
    counts, edges = np.histogram(np.clip(term, lo, hi), bins=40, range=(lo, hi))
    centers = (edges[:-1] + edges[1:]) / 2.0
    data = [list(centers), list(counts.astype(float))]
    spec = {
        "type": "bars", "xMoney": True, "yMoney": False,
        "xLabel": "terminal net worth (reordered)",
        "series": [{"label": "reorderings", "stroke": charts.LINE_ALT,
                    "fill": "rgba(214,51,132,0.25)"}],
    }
    return charts.chart_block("chart-order", data, spec, height=300)


def _order_stats(result, horizon: int) -> list[tuple[str, str]]:
    """Summary stats for the order-of-returns experiment."""
    term = np.asarray(result.terminal, dtype=float)
    p10, p50, p90 = (float(np.percentile(term, q)) for q in (10, 50, 90))
    fail_frac = float((np.asarray(result.first_failure_period) >= 0).mean())
    return [
        ("Reorderings", f"{result.n:,}"),
        ("Actual (this order)", _fmt_money(result.reference_terminal)),
        ("Reordered median", _fmt_money(p50)),
        ("Reordered p10 / p90", f"{_fmt_money(p10)} / {_fmt_money(p90)}"),
        ("Reorderings that fail", _fmt_pct(fail_frac)),
    ]


# Headline rows reused by the comparison view: (label, summary-metric key).
_COMPARE_ROWS = [
    ("Overall success", "overall_success_rate"),
    ("Plan fully funded", "success_rate.all_planned_funded"),
    ("Portfolio never negative", "success_rate.portfolio_non_negative"),
    ("Mean terminal net worth", "terminal.mean"),
]


def _headline_lookup(loaded, key: str) -> str:
    m = {row["metric"]: row["value"] for _, row in loaded.summary.iterrows()}
    v = m.get(key, 0.0)
    return _fmt_money(v) if key.startswith("terminal.") else _fmt_pct(v)


def _compare_block(a, b, scale: str, labels: list[str]):
    """Overlay two runs' funnels: median + p10/p90 band each (A blue, B pink)."""
    xa = list(range(len(a.percentiles)))
    data = [
        xa,
        list(_pcol(a.percentiles, 90, scale)), list(_pcol(a.percentiles, 10, scale)),
        list(_pcol(a.percentiles, 50, scale)),
        list(_pcol(b.percentiles, 90, scale)), list(_pcol(b.percentiles, 10, scale)),
        list(_pcol(b.percentiles, 50, scale)),
    ]
    spec = {
        "type": "line", "yMoney": True, "xLabels": labels, "xLabel": "quarter",
        "series": [
            {"label": "A p90", "stroke": "rgba(0,0,0,0)", "width": 0},
            {"label": "A p10", "stroke": "rgba(0,0,0,0)", "width": 0},
            {"label": "A median", "stroke": charts.LINE_MEDIAN, "width": 2},
            {"label": "B p90", "stroke": "rgba(0,0,0,0)", "width": 0},
            {"label": "B p10", "stroke": "rgba(0,0,0,0)", "width": 0},
            {"label": "B median", "stroke": charts.LINE_ALT, "width": 2},
        ],
        "bands": [[1, 2, charts.BAND_OUTER], [4, 5, "rgba(214,51,132,0.12)"]],
    }
    return charts.chart_block("chart-compare", data, spec, height=380)
