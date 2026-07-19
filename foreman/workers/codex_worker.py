"""Codex worker: drives `codex exec` headless under the ChatGPT subscription.

With `--output-schema`, codex writes a pure-JSON final answer to stdout while the
transcript + telemetry go to stderr. We force a {"result": string} shape so the
answer is trivially parseable. Codex reports no per-token cost (it is billed by
subscription), so cost_usd stays 0 — which is exactly the point of this setup.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from foreman.config import DATA_DIR
from foreman.workers.base import WorkerResult

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TOKENS = re.compile(r"tokens used[:\s]+([\d,]+)", re.IGNORECASE)
_MODEL = re.compile(r"^model:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

_SCHEMA = {
    "type": "object",
    "properties": {"result": {"type": "string"}},
    "required": ["result"],
    "additionalProperties": False,
}


class CodexWorker:
    name = "codex"

    def __init__(self, sandbox: str = "workspace-write", timeout: int = 600) -> None:
        self.sandbox = sandbox
        self.timeout = timeout
        self._schema_path = DATA_DIR / "codex_result_schema.json"

    def _ensure_schema(self) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self._schema_path.exists():
            self._schema_path.write_text(json.dumps(_SCHEMA))
        return self._schema_path

    def run(self, prompt: str, workdir: Path) -> WorkerResult:
        schema = self._ensure_schema()
        cmd = [
            "codex", "exec", prompt,
            "--sandbox", self.sandbox,
            "-C", str(workdir),
            "--skip-git-repo-check",
            "--output-schema", str(schema),
        ]
        started = time.time()
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return WorkerResult(
                ok=False, error=f"codex timed out after {self.timeout}s",
                duration_ms=int((time.time() - started) * 1000),
            )

        elapsed_ms = int((time.time() - started) * 1000)
        stdout = proc.stdout.strip()
        stderr_clean = _ANSI.sub("", proc.stderr)

        # Telemetry lives on stderr.
        tokens = 0
        if m := _TOKENS.search(stderr_clean):
            tokens = int(m.group(1).replace(",", ""))
        model = ""
        if m := _MODEL.search(stderr_clean):
            model = m.group(1).strip()

        # Final answer is JSON on stdout thanks to --output-schema.
        result_text = stdout
        if stdout:
            try:
                result_text = json.loads(stdout).get("result", stdout)
            except json.JSONDecodeError:
                result_text = stdout  # fall back to raw

        if proc.returncode != 0 and not stdout:
            return WorkerResult(
                ok=False,
                error=stderr_clean.strip()[-500:] or "codex exited non-zero",
                model=model, tokens_out=tokens, duration_ms=elapsed_ms, raw=proc.stderr,
            )

        return WorkerResult(
            ok=True,
            result=result_text,
            model=model,
            tokens_out=tokens,  # codex reports a single total; kept as one figure
            cost_usd=0.0,       # subscription-billed, no per-token cost
            duration_ms=elapsed_ms,
            raw=stdout,
        )
