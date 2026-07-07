"""Web routes (single blueprint). Stage 1: a dashboard stub only."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

bp = Blueprint("simulate", __name__)


@bp.route("/")
def dashboard():
    """Simulation dashboard. Stage 1 shows version + a no-runs-yet placeholder."""
    state = current_app.config["APP_STATE"]
    return render_template("fiscus_simulate/dashboard.html", runs=[], state=state)
