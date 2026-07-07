"""Cross-platform guard: no drive-letter path literals in package source.

fiscus_simulate must run on Windows and the author's Linux VPS. Absolute drive paths
(e.g. ``C:\\...``) in source would break portability — configuration and app state
must come from ``pathlib`` / config, never hardcoded locations.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "fiscus_simulate"
DRIVE_LITERAL = re.compile(r"[A-Za-z]:\\")


def test_no_drive_letter_paths_in_source():
    offenders = []
    for py in SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if DRIVE_LITERAL.search(text):
            offenders.append(py.name)
    assert not offenders, f"drive-letter path literals found in: {offenders}"
