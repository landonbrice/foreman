"""Custom CrewAI events Foreman emits onto the shared event bus.

The flow emits these; the ScoreboardListener is the single consumer that turns
them into scoreboard rows. Keeping worker telemetry on the same bus CrewAI uses
means native agent/task events (added later) land in the same place.
"""

from __future__ import annotations

from typing import Literal

from crewai.events.base_events import BaseEvent


class RunStartedEvent(BaseEvent):
    type: Literal["foreman_run_started"] = "foreman_run_started"
    run_id: str
    vision: str


class RunFinishedEvent(BaseEvent):
    type: Literal["foreman_run_finished"] = "foreman_run_finished"
    run_id: str
    status: str


class SubtaskDispatchedEvent(BaseEvent):
    type: Literal["foreman_subtask_dispatched"] = "foreman_subtask_dispatched"
    run_id: str
    subtask_id: str
    seq: int
    description: str
    worker: str
    repo_path: str


class WorkerCompletedEvent(BaseEvent):
    type: Literal["foreman_worker_completed"] = "foreman_worker_completed"
    run_id: str
    subtask_id: str
    worker: str
    result: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0


class WorkerFailedEvent(BaseEvent):
    type: Literal["foreman_worker_failed"] = "foreman_worker_failed"
    run_id: str
    subtask_id: str
    worker: str
    error: str = ""
    duration_ms: int = 0
