"""The family root defaults to the synthetic test tree, and no other code builds a ``.fiscus`` path.

The firewall property: with ``$FISCUS_ROOT`` unset, the run directories and the saved-scenario
folder both sit under ``~/.fiscus-test``. The real tree is reached only when a launcher sets
``$FISCUS_ROOT`` to it.
"""
from __future__ import annotations

import re
from pathlib import Path

from fiscus_simulate.storage import default_runs_dir, fiscus_root
from fiscus_simulate.web.state import AppState

SRC = Path(__file__).resolve().parents[1] / "src"


def test_unset_root_is_the_test_tree(monkeypatch):
    monkeypatch.delenv("FISCUS_ROOT", raising=False)
    assert fiscus_root().name == ".fiscus-test"
    assert fiscus_root().parent == Path.home()


def test_state_and_scenarios_follow_the_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FISCUS_ROOT", str(tmp_path))
    monkeypatch.delenv("FISCUS_SIMULATE_HOME", raising=False)
    state = AppState()
    assert state.state_dir == tmp_path / "simulate"
    assert state.runs_dir == default_runs_dir() == tmp_path / "simulate" / "simulation_runs"
    assert state.configs_dir == tmp_path / "settings" / "simulate"


def test_scenario_folder_is_its_own_argument(tmp_path):
    state = AppState(state_dir=tmp_path / "state", configs_dir=tmp_path / "scenarios")
    assert state.configs_dir == tmp_path / "scenarios"
    assert state.runs_dir == tmp_path / "state" / "simulation_runs"


def test_no_other_fiscus_literal_in_src():
    pattern = re.compile(r"""["']\.fiscus["']""")
    hits = [f"{p.relative_to(SRC)}:{n}" for p in SRC.rglob("*.py")
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if pattern.search(line)]
    assert hits == []
