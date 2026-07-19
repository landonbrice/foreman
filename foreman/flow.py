"""The Master Flow: Foreman's PM brain and lane graph.

A CrewAI Flow that takes a vision + a list of subtasks, routes each subtask to a
worker, dispatches them concurrently, and collects results. Every step emits
events onto the shared bus, which the ScoreboardListener mirrors into SQLite.

For phases 1-3 subtasks are supplied by the caller. Phase 4 will add an LLM step
that decomposes `vision` into subtasks — it slots in ahead of `dispatch` without
changing anything downstream.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from crewai.events.event_bus import crewai_event_bus
from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel

from foreman.config import workdir_for
from foreman.router import pick_worker
from foreman.scoreboard.events import (
    RunFinishedEvent,
    RunStartedEvent,
    SubtaskDispatchedEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
)
from foreman.workers.claude_worker import ClaudeWorker
from foreman.workers.codex_worker import CodexWorker


class ForemanState(BaseModel):
    vision: str = ""
    run_id: str = ""
    subtasks: list[dict] = []  # each: {description: str, worker?: str}
    results: list[dict] = []


def build_workers() -> dict:
    return {"claude": ClaudeWorker(), "codex": CodexWorker()}


class ForemanFlow(Flow[ForemanState]):
    """Routes and dispatches subtasks across subscription-backed CLI workers."""

    def __init__(self, max_concurrency: int = 3, **kwargs) -> None:
        super().__init__(**kwargs)
        self.max_concurrency = max_concurrency
        self.workers = build_workers()

    @start()
    def begin(self) -> list[dict]:
        if not self.state.run_id:
            self.state.run_id = uuid.uuid4().hex
        crewai_event_bus.emit(
            self,
            RunStartedEvent(run_id=self.state.run_id, vision=self.state.vision),
        )
        return self.state.subtasks

    @listen(begin)
    def dispatch(self, subtasks: list[dict]) -> list[dict]:
        run_id = self.state.run_id
        workdir = workdir_for(run_id)
        available = list(self.workers)

        planned = []
        for i, spec in enumerate(subtasks):
            desc = spec["description"]
            worker, reason = pick_worker(desc, spec.get("worker"), available)
            subtask_id = f"{run_id[:8]}-{i:02d}"
            planned.append(
                {"id": subtask_id, "seq": i, "description": desc,
                 "worker": worker, "reason": reason}
            )
            crewai_event_bus.emit(
                self,
                SubtaskDispatchedEvent(
                    run_id=run_id, subtask_id=subtask_id, seq=i,
                    description=desc, worker=worker, repo_path=str(workdir),
                ),
            )

        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            futures = {
                pool.submit(self._run_one, p, workdir): p for p in planned
            }
            for fut in as_completed(futures):
                results.append(fut.result())

        self.state.results = results
        status = "done" if all(r["ok"] for r in results) else "failed"
        crewai_event_bus.emit(
            self, RunFinishedEvent(run_id=run_id, status=status)
        )
        return results

    def _run_one(self, planned: dict, workdir) -> dict:
        run_id = self.state.run_id
        worker = self.workers[planned["worker"]]
        res = worker.run(planned["description"], workdir)
        if res.ok:
            crewai_event_bus.emit(
                self,
                WorkerCompletedEvent(
                    run_id=run_id, subtask_id=planned["id"], worker=planned["worker"],
                    result=res.result, model=res.model,
                    tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                    cost_usd=res.cost_usd, duration_ms=res.duration_ms,
                ),
            )
        else:
            crewai_event_bus.emit(
                self,
                WorkerFailedEvent(
                    run_id=run_id, subtask_id=planned["id"], worker=planned["worker"],
                    error=res.error, duration_ms=res.duration_ms,
                ),
            )
        return {"id": planned["id"], "worker": planned["worker"], "ok": res.ok,
                "result": res.result, "error": res.error}


def run_vision(vision: str, subtasks: list[dict], max_concurrency: int = 3) -> ForemanState:
    """Kick off a Foreman run and return the final flow state."""
    flow = ForemanFlow(max_concurrency=max_concurrency)
    flow.kickoff(inputs={"vision": vision, "subtasks": subtasks})
    return flow.state
