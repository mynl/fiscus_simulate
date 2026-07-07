"""Application state: version and lazily-created app-state directories.

App state (configs, run directories) lives under ``~/.fiscus_simulate`` by default —
derived artifacts only, never inside the repo. Cross-platform: all paths via
``pathlib.Path`` and ``Path.home()``; no drive-letter literals.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .. import __version__


def default_state_dir() -> Path:
    """Return the app-state directory (``$FISCUS_SIMULATE_HOME`` or ``~/.fiscus_simulate``)."""
    env = os.environ.get("FISCUS_SIMULATE_HOME")
    return Path(env) if env else Path.home() / ".fiscus_simulate"


@dataclass
class AppState:
    """Per-process application state."""

    version: str = __version__
    state_dir: Path = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.state_dir is None:
            self.state_dir = default_state_dir()

    @property
    def runs_dir(self) -> Path:
        """Directory holding per-run subdirectories (created lazily on first use)."""
        return self.state_dir / "simulation_runs"

    def ensure_dirs(self) -> None:
        """Create the app-state directories if they do not yet exist."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
