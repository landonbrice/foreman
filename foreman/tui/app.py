"""Foreman scoreboard — a live Textual dashboard over scoreboard.db.

Polls the SQLite scoreboard once a second and repaints. This is the window you
watch the backend through: per-worker totals up top, a task table below with
each subtask's worker lane, status, model, tokens and duration.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Static

from foreman.scoreboard import db

_STATUS_STYLE = {
    "running": "bold yellow",
    "done": "bold green",
    "failed": "bold red",
    "pending": "dim",
}


class Totals(Static):
    """One-line per-worker scoreboard summary."""

    def refresh_totals(self) -> None:
        rows = db.worker_totals()
        if not rows:
            self.update(Text("no tasks yet — kick off a run with `foreman run`", style="dim"))
            return
        parts = []
        for r in rows:
            worker = r["worker"]
            seg = Text(f" {worker} ", style="bold white on blue")
            seg.append(
                f" {r['done']}✓ {r['failed']}✗ {r['running']}⟳"
                f"  {r['tokens']:,}tok  ${r['cost']:.3f}   ",
                style="white",
            )
            parts.append(seg)
        line = Text()
        for p in parts:
            line.append_text(p)
        self.update(line)


class ForemanApp(App):
    TITLE = "FOREMAN — agent scoreboard"
    CSS = """
    Totals { height: 1; padding: 0 1; margin: 1 0; }
    DataTable { height: 1fr; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Totals(id="totals")
            yield DataTable(id="tasks", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        db.init_db()
        table = self.query_one("#tasks", DataTable)
        table.add_columns("seq", "worker", "status", "task", "model", "tokens", "ms")
        self.refresh_board()
        self.set_interval(1.0, self.refresh_board)

    def action_refresh(self) -> None:
        self.refresh_board()

    def refresh_board(self) -> None:
        self.query_one("#totals", Totals).refresh_totals()
        table = self.query_one("#tasks", DataTable)
        table.clear()
        for t in db.all_tasks(limit=100):
            status = t["status"]
            desc = (t["description"] or "")[:60]
            tokens = (t["tokens_in"] or 0) + (t["tokens_out"] or 0)
            table.add_row(
                str(t["seq"]),
                Text(t["worker"] or "?", style="cyan"),
                Text(status, style=_STATUS_STYLE.get(status, "")),
                desc,
                t["model"] or "",
                f"{tokens:,}" if tokens else "",
                str(t["duration_ms"] or ""),
            )


def main() -> None:
    ForemanApp().run()


if __name__ == "__main__":
    main()
