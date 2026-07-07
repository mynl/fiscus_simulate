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

from ..config import from_yaml_str, to_yaml_str
from ..models import RunConfig
from . import configs
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
    return render_template(
        "fiscus_simulate/config_edit.html",
        state=_state(),
        name="",
        yaml_text=to_yaml_str(RunConfig.default()),
        errors=[],
        is_saved=False,
    )


@bp.route("/config/<name>")
def config_edit(name: str):
    """Open a saved configuration in the editor."""
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
    """Minimal run view (Stage 6): metadata + summary metrics. Charts land in Stage 7."""
    from .. import storage

    state = _state()
    try:
        loaded = storage.load_run(run_id, runs_dir=state.runs_dir)
    except FileNotFoundError:
        abort(404)
    metrics = [
        (row["metric"], row["value"]) for _, row in loaded.summary.iterrows()
    ]
    return render_template(
        "fiscus_simulate/run_detail.html",
        state=state,
        run=loaded,
        metadata=loaded.metadata,
        metrics=metrics,
    )
