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
from . import configs
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
    """Open the editor seeded from the illustrative default configuration."""
    cfg = RunConfig.default()
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

    return render_template(
        "fiscus_simulate/run_detail.html",
        state=state,
        run=loaded,
        metadata=loaded.metadata,
        headline=_headline_metrics(loaded),
        dist_table=render_table(dist, name="outcome distribution") if dist is not None else None,
        view=view,
        has_joint=loaded.joint is not None,
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
    sc = {int(r["percentile"]): r for _, r in loaded.scalars.iterrows()}
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
    if 50 in sc:
        rows.append(("Median terminal net worth", _fmt_money(sc[50]["terminal_nominal"])))
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
    pcts = [int(p) for p in src["percentile"]]
    labels = (["mean"] if have_mean else []) + [f"p{p:02d}" for p in pcts]

    cols: dict[str, object] = {"level": labels}
    for key, header, is_money in _DIST_COLS:
        if key not in src.columns:
            continue
        prefix = [means[key]] if have_mean else []
        arr = np.asarray(prefix + list(src[key]), dtype=float)
        cols[header] = np.rint(arr).astype("int64") if is_money else np.round(arr, 1)
    return pd.DataFrame(cols)
