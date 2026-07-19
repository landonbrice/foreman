"""SQLite scoreboard: the single source of truth the TUI reads from.

Design notes
------------
* Every function opens a short-lived connection. SQLite handles are not shared
  across threads, and CrewAI's event bus may dispatch handlers from worker
  threads, so per-call connections keep us thread-safe without a lock.
* WAL mode lets the Textual dashboard read while the flow writes.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from foreman.config import SCOREBOARD_DB, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    vision      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',   -- running | done | failed
    created_at  REAL NOT NULL,
    finished_at REAL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    description TEXT NOT NULL,
    worker      TEXT,                              -- claude | codex | ...
    status      TEXT NOT NULL DEFAULT 'pending',   -- pending | running | done | failed
    result      TEXT,
    error       TEXT,
    model       TEXT,
    tokens_in   INTEGER DEFAULT 0,
    tokens_out  INTEGER DEFAULT 0,
    cost_usd    REAL DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    repo_path   TEXT,
    created_at  REAL NOT NULL,
    started_at  REAL,
    finished_at REAL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    run_id   TEXT,
    task_id  TEXT,
    kind     TEXT NOT NULL,
    payload  TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(SCOREBOARD_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as c:
        c.executescript(SCHEMA)


# --- writers -------------------------------------------------------------

def create_run(run_id: str, vision: str) -> None:
    with _connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO runs (id, vision, status, created_at) "
            "VALUES (?, ?, 'running', ?)",
            (run_id, vision, time.time()),
        )


def finish_run(run_id: str, status: str) -> None:
    with _connect() as c:
        c.execute(
            "UPDATE runs SET status=?, finished_at=? WHERE id=?",
            (status, time.time(), run_id),
        )


def create_task(
    task_id: str, run_id: str, seq: int, description: str, worker: str, repo_path: str
) -> None:
    with _connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO tasks "
            "(id, run_id, seq, description, worker, status, repo_path, created_at, started_at) "
            "VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)",
            (task_id, run_id, seq, description, worker, repo_path, time.time(), time.time()),
        )


def finish_task(task_id: str, **fields: Any) -> None:
    """Update a task row. Accepts any subset of the task columns plus status."""
    fields.setdefault("finished_at", time.time())
    cols = ", ".join(f"{k}=?" for k in fields)
    with _connect() as c:
        c.execute(f"UPDATE tasks SET {cols} WHERE id=?", (*fields.values(), task_id))


def log_event(kind: str, run_id: str | None, task_id: str | None, payload: dict) -> None:
    with _connect() as c:
        c.execute(
            "INSERT INTO events (ts, run_id, task_id, kind, payload) VALUES (?, ?, ?, ?, ?)",
            (time.time(), run_id, task_id, kind, json.dumps(payload, default=str)),
        )


# --- readers (used by the TUI) ------------------------------------------

def recent_runs(limit: int = 20) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def tasks_for_run(run_id: str) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE run_id=? ORDER BY seq", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def all_tasks(limit: int = 200) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def worker_totals() -> list[dict]:
    """Aggregate per-worker counts + cost for the scoreboard header."""
    with _connect() as c:
        rows = c.execute(
            "SELECT worker, "
            "COUNT(*) AS total, "
            "SUM(status='done') AS done, "
            "SUM(status='failed') AS failed, "
            "SUM(status='running') AS running, "
            "COALESCE(SUM(cost_usd),0) AS cost, "
            "COALESCE(SUM(tokens_in+tokens_out),0) AS tokens "
            "FROM tasks WHERE worker IS NOT NULL GROUP BY worker ORDER BY worker"
        ).fetchall()
        return [dict(r) for r in rows]
