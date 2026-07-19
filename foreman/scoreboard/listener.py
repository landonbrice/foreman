"""The single scoreboard writer.

Subscribes to Foreman's custom events (and CrewAI's native flow events) on the
shared bus and mirrors them into scoreboard.db. Instantiate one of these before
kicking off a flow; the base class registers the handlers on construction.
"""

from __future__ import annotations

from crewai.events.base_event_listener import BaseEventListener
from crewai.events.event_bus import CrewAIEventsBus
from crewai.events.types.flow_events import (
    FlowFinishedEvent,
    FlowStartedEvent,
    MethodExecutionStartedEvent,
)

from foreman.scoreboard import db
from foreman.scoreboard.events import (
    RunFinishedEvent,
    RunStartedEvent,
    SubtaskDispatchedEvent,
    WorkerCompletedEvent,
    WorkerFailedEvent,
)


class ScoreboardListener(BaseEventListener):
    """Turns bus events into scoreboard rows. One writer, event-sourced."""

    def setup_listeners(self, bus: CrewAIEventsBus) -> None:
        db.init_db()

        @bus.on(RunStartedEvent)
        def _run_started(source, event: RunStartedEvent) -> None:
            db.create_run(event.run_id, event.vision)
            db.log_event("run_started", event.run_id, None, {"vision": event.vision})

        @bus.on(RunFinishedEvent)
        def _run_finished(source, event: RunFinishedEvent) -> None:
            db.finish_run(event.run_id, event.status)
            db.log_event("run_finished", event.run_id, None, {"status": event.status})

        @bus.on(SubtaskDispatchedEvent)
        def _dispatched(source, event: SubtaskDispatchedEvent) -> None:
            db.create_task(
                task_id=event.subtask_id,
                run_id=event.run_id,
                seq=event.seq,
                description=event.description,
                worker=event.worker,
                repo_path=event.repo_path,
            )
            db.log_event(
                "subtask_dispatched",
                event.run_id,
                event.subtask_id,
                {"worker": event.worker, "description": event.description},
            )

        @bus.on(WorkerCompletedEvent)
        def _completed(source, event: WorkerCompletedEvent) -> None:
            db.finish_task(
                event.subtask_id,
                status="done",
                result=event.result,
                model=event.model,
                tokens_in=event.tokens_in,
                tokens_out=event.tokens_out,
                cost_usd=event.cost_usd,
                duration_ms=event.duration_ms,
            )
            db.log_event(
                "worker_completed",
                event.run_id,
                event.subtask_id,
                {"worker": event.worker, "model": event.model, "cost_usd": event.cost_usd},
            )

        @bus.on(WorkerFailedEvent)
        def _failed(source, event: WorkerFailedEvent) -> None:
            db.finish_task(
                event.subtask_id,
                status="failed",
                error=event.error,
                duration_ms=event.duration_ms,
            )
            db.log_event(
                "worker_failed",
                event.run_id,
                event.subtask_id,
                {"worker": event.worker, "error": event.error},
            )

        # --- native CrewAI flow events: captured for the lane graph / audit ---

        @bus.on(FlowStartedEvent)
        def _flow_started(source, event: FlowStartedEvent) -> None:
            db.log_event("flow_started", None, None, {"flow": event.flow_name})

        @bus.on(MethodExecutionStartedEvent)
        def _method_started(source, event: MethodExecutionStartedEvent) -> None:
            db.log_event(
                "flow_method", None, None,
                {"flow": event.flow_name, "method": event.method_name},
            )

        @bus.on(FlowFinishedEvent)
        def _flow_finished(source, event: FlowFinishedEvent) -> None:
            db.log_event("flow_finished", None, None, {"flow": event.flow_name})
