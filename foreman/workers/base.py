"""Worker interface: a thin wrapper around a subscription-backed CLI agent.

A worker takes a prompt + a working directory, shells out to its CLI (running
under the user's existing subscription — no API key), and returns a normalized
result with whatever telemetry the CLI exposes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class WorkerResult:
    ok: bool
    result: str = ""
    error: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    raw: str = ""


class Worker(Protocol):
    name: str

    def run(self, prompt: str, workdir: Path) -> WorkerResult:
        ...
