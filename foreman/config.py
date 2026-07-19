"""Foreman configuration: filesystem locations for state and managed projects."""

from __future__ import annotations

import os
from pathlib import Path

# Where Foreman itself lives + keeps its state (the scoreboard DB, schemas).
FOREMAN_HOME = Path(os.environ.get("FOREMAN_HOME", Path.home() / "foreman"))
DATA_DIR = FOREMAN_HOME / "data"
SCOREBOARD_DB = Path(os.environ.get("FOREMAN_SCOREBOARD_DB", DATA_DIR / "scoreboard.db"))

# Where the projects Foreman *manages* live. Each run gets a working repo here.
PROJECTS_ROOT = Path(
    os.environ.get("FOREMAN_PROJECTS_ROOT", Path.home() / "agent-projects")
)


def ensure_dirs() -> None:
    """Create the state + projects directories if they do not exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)


def workdir_for(run_id: str) -> Path:
    """Return (and create) the working repo directory for a run."""
    d = PROJECTS_ROOT / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d
