"""Foreman command-line entrypoint.

    foreman run   -v "vision" -t "task" [-t "codex: build X"] ...   # dispatch subtasks
    foreman tui                                                     # live scoreboard
    foreman tasks                                                   # dump recent tasks
    foreman ping                                                    # phase-0 worker proof
"""

from __future__ import annotations

import argparse
import json
import sys

from foreman.scoreboard import db


def _parse_task_arg(t: str) -> dict:
    """Allow "codex: do the thing" / "claude: think" to pin a worker."""
    head, sep, rest = t.partition(":")
    if sep and head.strip() in ("claude", "codex"):
        return {"description": rest.strip(), "worker": head.strip()}
    return {"description": t.strip()}


def cmd_run(args: argparse.Namespace) -> int:
    from foreman.flow import run_vision
    from foreman.scoreboard.listener import ScoreboardListener

    ScoreboardListener()  # registers handlers on the shared bus

    subtasks: list[dict] = []
    if args.tasks_file:
        subtasks.extend(json.load(open(args.tasks_file)))
    for t in args.task or []:
        subtasks.append(_parse_task_arg(t))

    if not subtasks:
        print("No subtasks. Pass -t/--task or --tasks-file.", file=sys.stderr)
        return 2

    print(f"Dispatching {len(subtasks)} subtask(s)…  (watch live with `foreman tui`)")
    state = run_vision(args.vision or "ad-hoc run", subtasks, max_concurrency=args.concurrency)

    print(f"\nrun {state.run_id}")
    for r in state.results:
        mark = "✓" if r["ok"] else "✗"
        line = r["result"] if r["ok"] else r["error"]
        print(f"  {mark} [{r['worker']:>6}] {r['id']}  {(line or '')[:80]}")
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from foreman.tui.app import ForemanApp

    ForemanApp().run()
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    db.init_db()
    for t in db.all_tasks(limit=args.limit):
        tokens = (t["tokens_in"] or 0) + (t["tokens_out"] or 0)
        print(
            f"{t['status']:>7} [{t['worker'] or '?':>6}] {t['id']}  "
            f"{t['model'] or '':>16}  {tokens:>7,}tok  {t['duration_ms'] or 0:>6}ms  "
            f"{(t['description'] or '')[:50]}"
        )
    return 0


def cmd_ping(args: argparse.Namespace) -> int:
    """Phase-0 proof: hit each worker directly, no flow, no bus."""
    from pathlib import Path

    from foreman.config import PROJECTS_ROOT, ensure_dirs
    from foreman.workers.claude_worker import ClaudeWorker
    from foreman.workers.codex_worker import CodexWorker

    ensure_dirs()
    workdir = Path(PROJECTS_ROOT) / "_ping"
    workdir.mkdir(parents=True, exist_ok=True)
    prompt = "Reply with exactly: PING_OK"

    for w in (ClaudeWorker(), CodexWorker()):
        print(f"— {w.name} …", flush=True)
        r = w.run(prompt, workdir)
        status = "OK" if r.ok else "FAIL"
        print(
            f"  [{status}] result={r.result!r} model={r.model!r} "
            f"tokens={r.tokens_in + r.tokens_out} cost=${r.cost_usd:.4f} {r.duration_ms}ms"
        )
        if not r.ok:
            print(f"  error: {r.error}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="foreman", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="dispatch subtasks across workers")
    r.add_argument("-v", "--vision", help="the overall goal for this run")
    r.add_argument("-t", "--task", action="append", help="a subtask (repeatable). "
                   "Prefix 'codex:' or 'claude:' to pin a worker.")
    r.add_argument("--tasks-file", help="JSON file: list of {description, worker?}")
    r.add_argument("-c", "--concurrency", type=int, default=3)
    r.set_defaults(func=cmd_run)

    t = sub.add_parser("tui", help="launch the live scoreboard")
    t.set_defaults(func=cmd_tui)

    ts = sub.add_parser("tasks", help="print recent tasks")
    ts.add_argument("--limit", type=int, default=50)
    ts.set_defaults(func=cmd_tasks)

    pg = sub.add_parser("ping", help="phase-0 proof: call each worker directly")
    pg.set_defaults(func=cmd_ping)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
