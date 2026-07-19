"""Rules-based router: pick a worker for a subtask.

v1 is deliberately simple and transparent — keyword rules plus an explicit
per-subtask override. Phase-later work can swap this for an LLM-based router
without touching the flow, since the interface is just (description) -> worker.
"""

from __future__ import annotations

import re

# Words that suggest hands-on coding work → prefer Codex (a coding-first agent).
CODING_HINTS = {
    "code", "coding", "implement", "implementation", "refactor", "fix", "bug",
    "function", "script", "build", "compile", "test", "tests", "api", "class",
    "debug", "lint", "typescript", "python", "rust", "endpoint", "migration",
}


def pick_worker(
    description: str,
    override: str | None = None,
    available: list[str] | None = None,
) -> tuple[str, str]:
    """Return (worker_name, reason)."""
    available = available or ["claude", "codex"]

    if override:
        if override in available:
            return override, "explicit override"
        # fall through if the override isn't available

    words = set(re.findall(r"[a-zA-Z]+", description.lower()))
    if words & CODING_HINTS and "codex" in available:
        hit = ", ".join(sorted(words & CODING_HINTS)[:3])
        return "codex", f"coding keywords ({hit})"

    return "claude", "default: reasoning / writing / research"
