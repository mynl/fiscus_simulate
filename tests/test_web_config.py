"""Stage 6 web workflow: config editor, saved-config store, and run launcher."""
from __future__ import annotations

import pytest

from fiscus_simulate import storage
from fiscus_simulate.config import to_yaml_str
from fiscus_simulate.models import RunConfig
from fiscus_simulate.web import configs
from fiscus_simulate.web.app import create_app
from fiscus_simulate.web.jobs import Job, JobRegistry
from fiscus_simulate.web.state import AppState


@pytest.fixture
def client(tmp_path):
    app = create_app(AppState(state_dir=tmp_path))
    app.config.update(TESTING=True)
    return app.test_client()


def _small_config_yaml() -> str:
    """A valid config small enough to run inline in a test (a few hundred scenarios)."""
    cfg = RunConfig.default()
    cfg.simulation.n_scenarios = 200
    cfg.simulation.chunk_size = 200
    return to_yaml_str(cfg)


# --------------------------------------------------------------------------- editor
def test_dashboard_and_new_config(client):
    assert b"New configuration" in client.get("/").data
    body = client.get("/config/new").get_data(as_text=True)
    assert "schema_version" in body  # default config YAML is seeded into the editor


def test_save_roundtrip(client, tmp_path):
    resp = client.post("/config", data={"name": "base-case", "yaml": _small_config_yaml()})
    assert resp.status_code == 302  # POST-redirect-GET
    assert configs.exists(tmp_path / "configs", "base-case")
    edit = client.get("/config/base-case").get_data(as_text=True)
    assert "total_annual_real" in edit


def test_name_is_slugified(client, tmp_path):
    client.post("/config", data={"name": "Base Case 1", "yaml": _small_config_yaml()})
    assert configs.list_configs(tmp_path / "configs") == ["base-case-1"]


def test_editor_shows_preview(client):
    client.post("/config", data={"name": "prev", "yaml": _small_config_yaml()})
    body = client.get("/config/prev").get_data(as_text=True)
    assert "Preview" in body and "After-tax income" in body  # the account x asset matrix
    assert "1,250,000" in body  # Total-row balance from the default balances


def test_generic_template_seeds_accumulation(client):
    """The 'generic demo' preset seeds a still-saving household with a retirement panel."""
    body = client.get("/config/new?template=generic").get_data(as_text=True)
    assert "At" in body and "retirement" in body  # projection row shows (years_to_ret > 0)
    assert "annual_real_savings: 30000" in body   # generic A saves


def test_rename_on_save_creates_new_scenario(client, tmp_path):
    """Editing a loaded config's name and saving keeps the original and adds a copy."""
    client.post("/config", data={"name": "orig", "yaml": _small_config_yaml()})
    client.post("/config", data={"name": "variant", "yaml": _small_config_yaml()})
    assert configs.list_configs(tmp_path / "configs") == ["orig", "variant"]


def test_invalid_yaml_rerenders_with_errors(client, tmp_path):
    resp = client.post("/config", data={"name": "broken", "yaml": "household: [unclosed"})
    assert resp.status_code == 200  # re-render, not a redirect, not a 500
    assert "problem" in resp.get_data(as_text=True)
    assert not configs.exists(tmp_path / "configs", "broken")


def test_validation_error_rerenders(client, tmp_path):
    cfg = RunConfig.default()
    cfg.spending.category_pct[list(cfg.spending.category_pct)[0]] += 10  # sum != 100
    resp = client.post("/config", data={"name": "bad", "yaml": to_yaml_str(cfg)})
    assert resp.status_code == 200
    assert "sum to 100" in resp.get_data(as_text=True)
    assert not configs.exists(tmp_path / "configs", "bad")


def test_empty_name_rejected(client):
    resp = client.post("/config", data={"name": "", "yaml": _small_config_yaml()})
    assert resp.status_code == 200
    assert "invalid config name" in resp.get_data(as_text=True)


def test_delete_config(client, tmp_path):
    client.post("/config", data={"name": "temp", "yaml": _small_config_yaml()})
    assert configs.exists(tmp_path / "configs", "temp")
    resp = client.post("/config/temp/delete")
    assert resp.status_code == 302
    assert not configs.exists(tmp_path / "configs", "temp")


def test_dashboard_offers_config_delete(client):
    client.post("/config", data={"name": "shown", "yaml": _small_config_yaml()})
    body = client.get("/").get_data(as_text=True)
    assert "/config/shown/delete" in body  # trash button present on the dashboard


def test_delete_unparseable_config(client, tmp_path):
    """A config that no longer validates can still be deleted (filesystem unlink)."""
    (tmp_path / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "configs" / "legacy.yaml").write_text("schema_version: '0.0'\nbroken: [", encoding="utf-8")
    assert "legacy" in configs.list_configs(tmp_path / "configs")
    resp = client.post("/config/legacy/delete")
    assert resp.status_code == 302
    assert "legacy" not in configs.list_configs(tmp_path / "configs")


# --------------------------------------------------------------------------- running
def test_run_launch_persists_and_views(client, tmp_path):
    client.post("/config", data={"name": "runme", "yaml": _small_config_yaml()})
    # Small run executes inline, so the job is complete by the redirect.
    launch = client.post("/config/runme/run")
    assert launch.status_code == 302
    job_url = launch.headers["Location"]

    status = client.get(job_url + "/status").get_json()
    assert status["state"] == "complete"
    run_id = status["run_id"]

    # The run is persisted and viewable.
    runs = storage.list_runs(runs_dir=tmp_path / "simulation_runs")
    assert [r.run_id for r in runs] == [run_id]
    detail = client.get(f"/runs/{run_id}").get_data(as_text=True)
    assert "Overall success (every criterion met)" in detail  # human headline titles
    assert "Taxes paid" in detail  # tax outcomes surfaced in the distribution
    assert "Glossary" in detail    # self-documenting notes present
    # Charts render (uPlot blocks present).
    assert "Net-worth funnel" in detail
    assert "fiscusChart" in detail and "chart-funnel" in detail and "chart-terminal" in detail
    # The helper must be DEFINED before the inline chart calls run, else ReferenceError
    # leaves empty placeholders (regression guard).
    assert detail.index("window.fiscusChart =") < detail.index('fiscusChart("chart-funnel"')
    # Real scale toggle renders.
    assert client.get(f"/runs/{run_id}?scale=real").status_code == 200
    # Terminal-net-worth-ranked view is available and renders.
    terminal = client.get(f"/runs/{run_id}?view=terminal").get_data(as_text=True)
    assert "Each row is one real scenario" in terminal
    assert client.get("/runs").status_code == 200


def _launch_run(client, name: str) -> str:
    """Save a small config, run it inline, and return its persisted run id."""
    client.post("/config", data={"name": name, "yaml": _small_config_yaml()})
    job_url = client.post(f"/config/{name}/run").headers["Location"]
    return client.get(job_url + "/status").get_json()["run_id"]


def test_runs_list_has_summary_and_details_buttons(client):
    run_id = _launch_run(client, "listme")
    page = client.get("/runs").get_data(as_text=True)
    assert "Summary" in page and "Details" in page
    assert f"/runs/{run_id}/details" in page


def test_details_scenario_walk_overlay_and_tabs(client):
    run_id = _launch_run(client, "inside")
    # Pick the median percentile and inspect the scenario sitting there.
    page = client.get(f"/runs/{run_id}/details?p=50").get_data(as_text=True)
    assert "Details" in page and "chart-funnel" in page
    # Grab a real scenario index from the picker options.
    import re
    idx = int(re.search(r'<option value="(\d+)"', page).group(1))
    detail = client.get(f"/runs/{run_id}/details?p=50&scenario={idx}").get_data(as_text=True)
    # Overlay series present on the funnel, the walk grid, all three tabs, and the glossary.
    assert '"scenario"' in detail and "chart-funnel" in detail
    assert "Consolidated" in detail and "By account" in detail and "Order of returns" in detail
    assert "Not yet implemented" in detail            # By account placeholder
    assert "chart-order" in detail                    # order histogram rendered
    assert "Glossary" in detail
    assert detail.index("window.fiscusChart =") < detail.index('fiscusChart("chart-funnel"')


def test_details_missing_run_404(client):
    assert client.get("/runs/nope/details").status_code == 404


def test_compare_two_runs(client):
    client.post("/config", data={"name": "cmpa", "yaml": _small_config_yaml()})
    client.post("/config", data={"name": "cmpb", "yaml": _small_config_yaml()})
    a = client.get(client.post("/config/cmpa/run").headers["Location"] + "/status").get_json()["run_id"]
    b = client.get(client.post("/config/cmpb/run").headers["Location"] + "/status").get_json()["run_id"]
    page = client.get(f"/runs/compare?a={a}&b={b}").get_data(as_text=True)
    assert "chart-compare" in page and "fiscusChart" in page
    assert "Overall success" in page  # headline comparison table


def test_delete_run(client, tmp_path):
    client.post("/config", data={"name": "todelete", "yaml": _small_config_yaml()})
    run_id = client.post("/config/todelete/run").headers["Location"].rstrip("/").split("/")[-1]
    # job_id URL -> resolve to the run via status
    status = client.get(f"/jobs/{run_id}/status").get_json()
    real_run_id = status["run_id"]
    assert storage.list_runs(runs_dir=tmp_path / "simulation_runs")
    resp = client.post(f"/runs/{real_run_id}/delete")
    assert resp.status_code == 302
    assert storage.list_runs(runs_dir=tmp_path / "simulation_runs") == []


def test_job_view_redirects_to_completed_run(client):
    client.post("/config", data={"name": "r2", "yaml": _small_config_yaml()})
    job_url = client.post("/config/r2/run").headers["Location"]
    view = client.get(job_url)  # complete job → redirect to its run
    assert view.status_code == 302
    assert "/runs/" in view.headers["Location"]


def test_run_missing_config_404(client):
    assert client.post("/config/nope/run").status_code == 404


def test_registry_refuses_duplicate_inflight(tmp_path):
    """A second submit for a config with an in-flight job returns the existing job."""
    reg = JobRegistry()
    inflight = Job(job_id="abc", config_name="base", n_scenarios=999, state="running")
    reg._jobs[inflight.job_id] = inflight
    cfg = RunConfig.default()
    returned = reg.submit("base", cfg, runs_dir=tmp_path)
    assert returned is inflight  # refused; no second run started
