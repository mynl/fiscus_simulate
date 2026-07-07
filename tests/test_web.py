"""Web skeleton tests: the app boots and serves the dashboard."""
from __future__ import annotations

import fiscus_simulate
from fiscus_simulate.web.app import create_app
from fiscus_simulate.web.state import AppState


def test_app_boots_and_serves_dashboard(tmp_path):
    app = create_app(AppState(state_dir=tmp_path))
    app.config.update(TESTING=True)
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert fiscus_simulate.__version__ in body
    assert "Model limitations" in body  # V1 simplifications are labelled


def test_favicon_asset_served(tmp_path):
    app = create_app(AppState(state_dir=tmp_path))
    client = app.test_client()
    resp = client.get("/static/fiscus_simulate/branding/favicon.ico")
    assert resp.status_code == 200
