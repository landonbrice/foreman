# Foreman

An autonomous project-manager built on **CrewAI**. You give it a vision plus
subtasks; it routes each subtask to a specialist **CLI agent running under your
existing subscription** (Claude Code, Codex — Gemini next), dispatches them
concurrently, and tracks everything on a live SQLite **scoreboard** you watch
through a Textual TUI.

The whole thing runs with **no per-token API keys**. The trick: instead of
routing tokens to LLM APIs, Foreman shells out to each vendor's *headless CLI*
(`claude -p`, `codex exec`), which authenticates against the subscription seat
you already pay for.

## Architecture

```
   You ──(vision + subtasks)──▶ Master Flow (CrewAI Flow)   ← the "lane graph"
                                     │ router picks a worker per subtask
                          ┌──────────┴──────────┐
                          ▼                      ▼
                   ClaudeWorker            CodexWorker          ← subprocess adapters,
                   `claude -p --json`      `codex exec`           subscription-authed
                          │                      │
                          └── work inside a per-run repo under ~/agent-projects/<run_id>/

   every step ──emit──▶ CrewAI event bus ──▶ ScoreboardListener ──▶ scoreboard.db (SQLite)
                                                                          │
                                                                          ▼
                                                            Textual TUI (`foreman tui`)
```

| Module | Job |
|---|---|
| `foreman/flow.py` | Master Flow: routes + dispatches subtasks concurrently, emits events |
| `foreman/router.py` | Rules-based worker choice (keyword hints + explicit override) |
| `foreman/workers/` | `claude_worker.py`, `codex_worker.py` — headless CLI adapters |
| `foreman/scoreboard/` | `db.py` (SQLite), `events.py` (custom bus events), `listener.py` (sole writer) |
| `foreman/tui/app.py` | Live Textual dashboard reading the scoreboard |
| `foreman/cli.py` | `foreman run / tui / tasks / ping` |

## Usage

```bash
# prove the workers respond under your subscriptions (phase-0 check)
uv run foreman ping

# dispatch subtasks — router sends each to the right worker
uv run foreman run -v "Ship the login page" \
  -t "Summarize the auth requirements" \
  -t "Write a Python function to hash passwords"        # coding kw -> codex

# pin a worker explicitly with a prefix
uv run foreman run -t "codex: refactor utils.py" -t "claude: draft release notes"

# watch it live
uv run foreman tui

# dump the scoreboard
uv run foreman tasks
```

## Configuration

Environment variables (all optional):

| Var | Default | Meaning |
|---|---|---|
| `FOREMAN_HOME` | `~/foreman` | where state lives |
| `FOREMAN_SCOREBOARD_DB` | `~/foreman/data/scoreboard.db` | the scoreboard |
| `FOREMAN_PROJECTS_ROOT` | `~/agent-projects` | per-run working repos |

## Status

Built and verified: **phases 0–3**.

- **0 · workers** — `claude -p` + `codex exec` driven headless, subscription-authed, no API keys.
- **1 · scoreboard spine** — event bus → `ScoreboardListener` → SQLite; Master Flow + Claude worker.
- **2 · the board** — live Textual dashboard.
- **3 · multi-provider routing** — Codex worker + rules router; a writing task lands on Claude, a coding task on Codex, concurrently.

### Next (not yet built)
- **4 · chat + projects** — conversational front door that decomposes a spoken/typed vision into subtasks via an LLM step; durable per-project repos.
- **5 · always-on** — `launchd` agent so Foreman persists.
- **later** — Gemini CLI worker, voice input, smarter (LLM-based) routing, Tauri desktop app.

## Notes / gotchas

- **Python 3.13 required.** CrewAI pulls in `chromadb`, whose Pydantic-v1
  `BaseSettings` breaks on Python 3.14. The project is pinned to 3.13.
- **Codex reports no cost** in the scoreboard (`$0.00`) — it is subscription-billed,
  not per-token. That empty cost column is the design working as intended.
- Codex telemetry gives a single token total (stored under `tokens_out`); Claude
  gives a full in/out split.
