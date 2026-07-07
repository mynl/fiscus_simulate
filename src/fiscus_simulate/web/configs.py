"""Named saved-configuration store for the web layer.

Configs are YAML files under the app-state ``configs/`` directory — one per name, using
the package's canonical serialization (:mod:`fiscus_simulate.config`). Names are
validated to a filesystem-safe slug so they map onto filenames on any platform. This is
the thin persistence seam the config editor and run launcher build on; it adds no new
serialization path of its own.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..config import load_config, save_config
from ..models import RunConfig

# Filesystem-safe config names: lowercase alphanumerics, dash/underscore, must lead with
# an alphanumeric. Keeps names portable and free of path-traversal characters.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
MAX_NAME_LEN = 64


def valid_name(name: str) -> bool:
    """Return True if ``name`` is a safe saved-config slug."""
    return bool(name) and len(name) <= MAX_NAME_LEN and _SLUG_RE.match(name) is not None


def slugify(name: str) -> str:
    """Best-effort coercion of free text to a valid config slug (may be empty)."""
    s = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower())
    return s.strip("-_")[:MAX_NAME_LEN]


def _path(configs_dir: Path, name: str) -> Path:
    return Path(configs_dir) / f"{name}.yaml"


def list_configs(configs_dir: Path) -> list[str]:
    """Return the sorted names of saved configs (empty if the directory is absent)."""
    configs_dir = Path(configs_dir)
    if not configs_dir.exists():
        return []
    return sorted(p.stem for p in configs_dir.glob("*.yaml"))


def exists(configs_dir: Path, name: str) -> bool:
    """Return True if a config named ``name`` is saved."""
    return _path(configs_dir, name).exists()


def load(configs_dir: Path, name: str) -> RunConfig:
    """Load a saved config by name (raises if absent or invalid)."""
    return load_config(_path(configs_dir, name))


def save(configs_dir: Path, name: str, cfg: RunConfig) -> Path:
    """Persist ``cfg`` under ``name`` (canonical YAML); returns the path."""
    configs_dir = Path(configs_dir)
    configs_dir.mkdir(parents=True, exist_ok=True)
    return save_config(cfg, _path(configs_dir, name))


def delete(configs_dir: Path, name: str) -> bool:
    """Delete a saved config; returns True if a file was removed."""
    p = _path(configs_dir, name)
    if p.exists():
        p.unlink()
        return True
    return False
