"""Load, save, and validate :class:`RunConfig` as human-readable YAML.

Serialization goes through pydantic's JSON-mode dump (enums -> their string values,
dates -> ISO strings) so the YAML is clean and hand-editable, and round-trips exactly.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import yaml

from .models import SCHEMA_VERSION, RunConfig

__all__ = ["load_config", "save_config", "to_yaml_str", "from_yaml_str"]


def to_yaml_str(cfg: RunConfig) -> str:
    """Serialize a config to a YAML string (block style, keys in definition order)."""
    data = cfg.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def from_yaml_str(text: str) -> RunConfig:
    """Parse a config from a YAML string, validating and checking the schema version."""
    data = yaml.safe_load(text)
    _check_schema_version(data)
    return RunConfig.model_validate(data)


def save_config(cfg: RunConfig, path: str | Path) -> Path:
    """Write ``cfg`` to ``path`` as YAML, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_yaml_str(cfg), encoding="utf-8")
    return path


def load_config(path: str | Path) -> RunConfig:
    """Read and validate a config from a YAML file."""
    return from_yaml_str(Path(path).read_text(encoding="utf-8"))


def _check_schema_version(data: object) -> None:
    """Warn if the file's schema version differs from the current one.

    Notes
    -----
    A warning (not an error) in V1: there is only one schema version, and a soft check
    keeps old fixtures loadable. Turn this into a migration hook when the schema forks.
    """
    if isinstance(data, dict):
        found = data.get("schema_version")
        if found is not None and found != SCHEMA_VERSION:
            warnings.warn(
                f"config schema_version {found!r} != current {SCHEMA_VERSION!r}; "
                "loading anyway",
                stacklevel=3,
            )
