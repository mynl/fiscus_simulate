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
    assert "Preview" in body and "Household wealth" in body
    assert "1,250,000" in body  # wealth total from the default balances


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
    # Terminal-net-worth-ranked view is available and renders.
    terminal = client.get(f"/runs/{run_id}?view=terminal").get_data(as_text=True)
    assert "Each row is one real scenario" in terminal
    assert client.get("/runs").status_code == 200


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
