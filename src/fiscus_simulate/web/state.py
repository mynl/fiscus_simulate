"""Application state: version and lazily-created app-state directories.

App state (run directories) lives under ``<root>/simulate`` by default, ``<root>`` being
``fiscus_root()`` — derived artifacts only, never inside the repo. Saved scenario configs are
authored documents, so they live apart from it, under ``<root>/settings/simulate`` (the
backed-up settings tree). Cross-platform: all paths via ``pathlib.Path``; no drive-letter literals.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .. import __version__
from ..storage import fiscus_root


def default_state_dir() -> Path:
    """Return the app-state directory (``$FISCUS_SIMULATE_HOME`` or ``<root>/simulate``)."""
    env = os.environ.get("FISCUS_SIMULATE_HOME")
    return Path(env) if env else fiscus_root() / "simulate"


def default_configs_dir() -> Path:
    """Return the saved-scenario directory, ``<root>/settings/simulate``."""
    return fiscus_root() / "settings" / "simulate"


@dataclass
class AppState:
    """Per-process application state.

    ``state_dir`` holds derived run directories; ``configs_dir`` holds the saved scenario
    documents. Each defaults independently, so tests can point either at a temporary folder.
    """

    version: str = __version__
    state_dir: Path = None  # type: ignore[assignment]
    configs_dir: Path = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.state_dir is None:
            self.state_dir = default_state_dir()
        if self.configs_dir is None:
            self.configs_dir = default_configs_dir()

    @property
    def runs_dir(self) -> Path:
        """Directory holding per-run subdirectories (created lazily on first use)."""
        return self.state_dir / "simulation_runs"

    def ensure_dirs(self) -> None:
        """Create the app-state directories if they do not yet exist."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.configs_dir.mkdir(parents=True, exist_ok=True)
