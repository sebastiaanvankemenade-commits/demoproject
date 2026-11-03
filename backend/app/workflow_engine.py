"""Deterministic workflow state machine.

The model never changes a state. It supplies observations; only this engine decides.
Live, simulated and manual input all pass through the same rules.
"""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from .observation import Observation, ObservationStatus
from .workflow_models import Workflow, WorkflowStep


class StepState(StrEnum):
    WAITING = "waiting"
    ACTIVE = "active"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    UNCERTAIN = "uncertain"
    DEVIATION = "deviation"


class ConfirmationMethod(StrEnum):
    AI = "ai"
    SIMULATED = "simulated"
    MANUAL = "manual"


class EventType(StrEnum):
    STARTED = "started"
    STEP_ACTIVATED = "step_activated"
    OBSERVATION_COUNTED = "observation_counted"
    OBSERVATION_IGNORED = "observation_ignored"
    NOT_COMPLETE = "not_complete"
    UNCERTAIN = "uncertain"
    DEVIATION_SUSPECTED = "deviation_suspected"
    DEVIATION_CONFIRMED = "deviation_confirmed"
    STEP_CONFIRMED = "step_confirmed"
    TURNS_RECORDED = "turns_recorded"
    COMPLETION_REJECTED = "completion_rejected"
    STEP_RESET = "step_reset"
    COUNTERS_RESET = "counters_reset"
    WORKFLOW_COMPLETED = "workflow_completed"


class IgnoreReason(StrEnum):
    NOT_RUNNING = "not_running"
    WRONG_STEP = "wrong_step"
    STALE_FRAME = "stale_frame"
    NO_FRAMES = "no_frames"
    SIMULATION_MISMATCH = "simulation_mismatch"
    AWAITING_TRANSITION = "awaiting_transition"


class EngineEvent(BaseModel):
    type: EventType
    step_id: str | None = None
    detail: str | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StepRecord(BaseModel):
    step_id: str
    state: StepState = StepState.WAITING
    confirmations: int = 0
    required_confirmations: int
    seen_incomplete: bool = False
    deviation_count: int = 0
    deviation: str | None = None
    turns: int = 0
    method: ConfirmationMethod | None = None
    confirmed_at: datetime | None = None
    evidence: list[Observation] = Field(default_factory=list)


class WorkflowEngine:
    def __init__(self, workflow: Workflow, simulated: bool = False):
        self.workflow = workflow
        self.simulated = simulated
        self.running = False
        self.active_index = 0
        self.records: list[StepRecord] = []
        self._last_frames: dict[int, int] = {}
        self._reset_records()

    def _reset_records(self) -> None:
        self.records = [
            StepRecord(step_id=step.id, required_confirmations=self._required(step))
            for step in self.workflow.steps
        ]
        self.active_index = 0

    def _required(self, step: WorkflowStep) -> int:
        return step.required_confirmations or self.workflow.required_confirmations

    @property
    def finished(self) -> bool:
        return all(record.state is StepState.COMPLETED for record in self.records)

    @property
    def active_step(self) -> WorkflowStep | None:
        if self.finished:
            return None
        return self.workflow.steps[self.active_index]

    @property
    def active_record(self) -> StepRecord | None:
        return None if self.finished else self.records[self.active_index]

    @property
    def progress(self) -> float:
        done = sum(record.state is StepState.COMPLETED for record in self.records)
        return done / len(self.records)

    def start(self) -> list[EngineEvent]:
        self._reset_records()
        self._last_frames = {}
        self.running = True
        self.records[0].state = StepState.ACTIVE
        return [
            EngineEvent(type=EventType.STARTED),
            EngineEvent(type=EventType.STEP_ACTIVATED, step_id=self.records[0].step_id),
        ]

    def apply(self, obs: Observation) -> list[EngineEvent]:
        reason = self._ignore_reason(obs)
        if reason:
            return [EngineEvent(type=EventType.OBSERVATION_IGNORED, step_id=obs.step_id, detail=reason.value)]
        self._last_frames.update(obs.frames)

        record = self.active_record
        if obs.status is ObservationStatus.COMPLETED:
            return self._on_completed(record, obs)
        if obs.status is ObservationStatus.INCOMPLETE:
            return self._on_incomplete(record, obs)
        return self._on_uncertain(record, obs)

    def _ignore_reason(self, obs: Observation) -> IgnoreReason | None:
        if not self.running or self.finished:
            return IgnoreReason.NOT_RUNNING
        if obs.step_id != self.active_record.step_id:
            return IgnoreReason.WRONG_STEP
        if obs.simulated != self.simulated:
            return IgnoreReason.SIMULATION_MISMATCH
        if not obs.frames:
            return IgnoreReason.NO_FRAMES
        # Every analysed camera must have delivered a newer frame: repeating a stale
        # image would otherwise count as independent evidence.
        for camera, sequence in obs.frames.items():
            if sequence <= self._last_frames.get(camera, -1):
                return IgnoreReason.STALE_FRAME
        return None

    def _on_completed(self, record: StepRecord, obs: Observation) -> list[EngineEvent]:
        record.deviation_count = 0
        record.deviation = None
        if self.active_step.requires_transition and not record.seen_incomplete:
            record.state = StepState.ACTIVE
            return [
                EngineEvent(
                    type=EventType.OBSERVATION_IGNORED,
                    step_id=record.step_id,
                    detail=IgnoreReason.AWAITING_TRANSITION.value,
                )
            ]
        record.confirmations += 1
        record.evidence.append(obs)
        if record.confirmations >= record.required_confirmations:
            method = ConfirmationMethod.SIMULATED if obs.simulated else ConfirmationMethod.AI
            return self._confirm(record, method)
        record.state = StepState.VERIFYING
        detail = f"{record.confirmations}/{record.required_confirmations}"
        return [EngineEvent(type=EventType.OBSERVATION_COUNTED, step_id=record.step_id, detail=detail)]

    def _on_incomplete(self, record: StepRecord, obs: Observation) -> list[EngineEvent]:
        self._clear_confirmations(record)
        record.seen_incomplete = True
        if not obs.deviation:
            record.deviation_count = 0
            record.deviation = None
            record.state = StepState.ACTIVE
            return [EngineEvent(type=EventType.NOT_COMPLETE, step_id=record.step_id, detail=obs.evidence)]

        # A deviation is only confirmed by the same number of fresh frames as a completion.
        record.deviation_count += 1
        record.deviation = obs.deviation
        if record.deviation_count >= record.required_confirmations:
            record.state = StepState.DEVIATION
            return [EngineEvent(type=EventType.DEVIATION_CONFIRMED, step_id=record.step_id, detail=obs.deviation)]
        record.state = StepState.UNCERTAIN
        return [EngineEvent(type=EventType.DEVIATION_SUSPECTED, step_id=record.step_id, detail=obs.deviation)]

    def _on_uncertain(self, record: StepRecord, obs: Observation) -> list[EngineEvent]:
        self._clear_confirmations(record)
        record.deviation_count = 0
        record.deviation = None
        record.state = StepState.UNCERTAIN
        return [EngineEvent(type=EventType.UNCERTAIN, step_id=record.step_id, detail=obs.evidence)]

    def _clear_confirmations(self, record: StepRecord) -> None:
        record.confirmations = 0
        record.evidence = []

    def add_turns(self, turns: int) -> None:
        """Counted movements are recorded with the step but never decide it."""
        if self.running and self.active_record is not None:
            self.active_record.turns += turns

    def _confirm(self, record: StepRecord, method: ConfirmationMethod) -> list[EngineEvent]:
        expected = self.active_step.expected_turns
        record.state = StepState.COMPLETED
        record.method = method
        record.confirmed_at = datetime.now(timezone.utc)
        events = [EngineEvent(type=EventType.STEP_CONFIRMED, step_id=record.step_id, detail=method.value)]
        if expected is not None:
            events.append(
                EngineEvent(type=EventType.TURNS_RECORDED, step_id=record.step_id, detail=f"{record.turns}/{expected}")
            )
        if self.finished:
            self.running = False
            events.append(EngineEvent(type=EventType.WORKFLOW_COMPLETED))
            return events
        self.active_index += 1
        next_record = self.records[self.active_index]
        next_record.state = StepState.ACTIVE
        events.append(EngineEvent(type=EventType.STEP_ACTIVATED, step_id=next_record.step_id))
        return events

    def confirm_manually(self) -> list[EngineEvent]:
        if not self.running or self.finished:
            return []
        return self._confirm(self.active_record, ConfirmationMethod.MANUAL)

    def reject_completion(self) -> list[EngineEvent]:
        record = self.active_record
        if not self.running or record is None:
            return []
        self._reset_record(record)
        record.turns = 0
        return [EngineEvent(type=EventType.COMPLETION_REJECTED, step_id=record.step_id)]

    def reset_active_step(self) -> list[EngineEvent]:
        record = self.active_record
        if not self.running or record is None:
            return []
        self._reset_record(record)
        record.turns = 0
        return [EngineEvent(type=EventType.STEP_RESET, step_id=record.step_id)]

    def reset_counters(self) -> list[EngineEvent]:
        """Drop unconfirmed progress, for example after a model switch. Completed steps stay."""
        record = self.active_record
        if record is None:
            return []
        self._reset_record(record)
        return [EngineEvent(type=EventType.COUNTERS_RESET, step_id=record.step_id)]

    def _reset_record(self, record: StepRecord) -> None:
        self._clear_confirmations(record)
        record.seen_incomplete = False
        record.deviation_count = 0
        record.deviation = None
        record.state = StepState.ACTIVE
