"""(b) Performance caps in config.py match the numbers stated in BOTS.md."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from blob_evolution import config

REPO_ROOT = Path(__file__).resolve().parent.parent

# BOTS.md label -> config.py constant that implements it.
CAP_CONSTANTS = {
    "particles": "MAX_PARTICLES",
    "creatures": "MAX_CREATURES",
    "bosses": "MAX_BOSSES",
    "projectiles": "MAX_PROJECTILES",
    "FPS": "FPS",
}


def _bots_caps() -> dict:
    """Parse the 'Performance caps in `config.py`: ...' line from BOTS.md."""
    text = (REPO_ROOT / "BOTS.md").read_text(encoding="utf-8")
    match = re.search(r"Performance caps in `config\.py`:\s*(.+)", text)
    assert match, "BOTS.md no longer has a 'Performance caps in `config.py`:' line"
    caps = {}
    for number, label in re.findall(r"([\d,]+)\s+([A-Za-z]+)", match.group(1)):
        caps[label] = int(number.replace(",", ""))
    return caps


def test_bots_md_lists_every_cap():
    """BOTS.md still states all five caps this suite checks."""
    assert set(_bots_caps()) == set(CAP_CONSTANTS)


@pytest.mark.parametrize("label", sorted(CAP_CONSTANTS))
def test_config_cap_matches_bots_md(label):
    """config.py defines the cap and its value equals BOTS.md's number."""
    expected = _bots_caps()[label]
    name = CAP_CONSTANTS[label]
    assert hasattr(config, name), f"config.py has no {name} (BOTS.md: {expected} {label})"
    assert getattr(config, name) == expected, (
        f"config.{name} = {getattr(config, name)!r}, BOTS.md says {expected} {label}"
    )
