"""Suite-wide isolation: every test runs with ``$FISCUS_ROOT`` on a temporary folder, so no test
resolves a path to the real tree (``~/.fiscus``) or to the shared test tree (``~/.fiscus-test``)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_fiscus_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FISCUS_ROOT", str(tmp_path / "fiscus-root"))
