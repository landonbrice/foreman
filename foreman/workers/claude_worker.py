"""Claude Code worker: drives `claude -p` headless under the Claude subscription.

`claude -p ... --output-format json` returns a single JSON object with the final
result plus rich telemetry (cost, tokens, duration, model) — which we map
straight onto WorkerResult. No API key involved; auth is the CLI's own session.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from foreman.workers.base import WorkerResult


class ClaudeWorker:
    name = "claude"

    def __init__(self, permission_mode: str = "acceptEdits", timeout: int = 600) -> None:
        self.permission_mode = permission_mode
        self.timeout = timeout

    def run(self, prompt: str, workdir: Path) -> WorkerResult:
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "json",
            "--permission-mode", self.permission_mode,
        ]
        started = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workdir),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return WorkerResult(
                ok=False, error=f"claude timed out after {self.timeout}s",
                duration_ms=int((time.time() - started) * 1000),
            )

        elapsed_ms = int((time.time() - started) * 1000)
        raw = proc.stdout.strip()

        if proc.returncode != 0 and not raw:
            return WorkerResult(
                ok=False, error=proc.stderr.strip() or "claude exited non-zero",
                duration_ms=elapsed_ms, raw=proc.stderr,
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return WorkerResult(
                ok=False, error="could not parse claude JSON output",
                duration_ms=elapsed_ms, raw=raw,
            )

        usage = data.get("usage", {}) or {}
        model_usage = data.get("modelUsage", {}) or {}
        model = next(iter(model_usage), "") if model_usage else ""
        is_error = data.get("is_error", False)

        return WorkerResult(
            ok=not is_error,
            result=data.get("result", ""),
            error="" if not is_error else str(data.get("result", "claude reported error")),
            model=model,
            tokens_in=int(usage.get("input_tokens", 0))
            + int(usage.get("cache_read_input_tokens", 0))
            + int(usage.get("cache_creation_input_tokens", 0)),
            tokens_out=int(usage.get("output_tokens", 0)),
            cost_usd=float(data.get("total_cost_usd", 0.0) or 0.0),
            duration_ms=int(data.get("duration_ms", elapsed_ms)),
            raw=raw,
        )
