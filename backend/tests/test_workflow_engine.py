from app.observation import Observation, ObservationStatus
from app.workflow_engine import ConfirmationMethod, EventType, StepState, WorkflowEngine
from app.workflow_models import Workflow, WorkflowStep


def step(step_id: str, **kwargs) -> WorkflowStep:
    return WorkflowStep(id=step_id, title=step_id, instruction="doe", completion_criterion="zichtbaar", **kwargs)


def make_engine(*steps: WorkflowStep, simulated: bool = False) -> WorkflowEngine:
    workflow = Workflow(id="wf", name="Test", steps=list(steps) or [step("s1"), step("s2")])
    engine = WorkflowEngine(workflow, simulated=simulated)
    engine.start()
    return engine


class Feed:
    """Hands out observations with ever newer frame numbers."""

    def __init__(self):
        self.sequence = 0

    def obs(self, status: ObservationStatus, step_id: str = "s1", **kwargs) -> Observation:
        self.sequence += 1
        frames = kwargs.pop("frames", {1: self.sequence})
        return Observation(step_id=step_id, status=status, evidence="bewijs", frames=frames, **kwargs)


C, I, U = ObservationStatus.COMPLETED, ObservationStatus.INCOMPLETE, ObservationStatus.UNCERTAIN


def types(events) -> list[EventType]:
    return [event.type for event in events]


def test_single_positive_is_not_enough():
    engine, feed = make_engine(), Feed()
    engine.apply(feed.obs(C))
    assert engine.active_record.state is StepState.VERIFYING
    assert engine.active_step.id == "s1"


def test_three_fresh_positives_complete_and_advance():
    engine, feed = make_engine(), Feed()
    events = [engine.apply(feed.obs(C)) for _ in range(3)][-1]
    assert types(events) == [EventType.STEP_CONFIRMED, EventType.STEP_ACTIVATED]
    assert engine.records[0].state is StepState.COMPLETED
    assert engine.records[0].method is ConfirmationMethod.AI
    assert engine.records[0].confirmed_at is not None
    assert len(engine.records[0].evidence) == 3
    assert engine.active_step.id == "s2"


def test_stale_frame_does_not_count():
    engine = make_engine()
    obs = Observation(step_id="s1", status=C, evidence="x", frames={1: 5})
    engine.apply(obs)
    events = engine.apply(obs)
    assert events[0].detail == "stale_frame"
    assert engine.active_record.confirmations == 1


def test_all_cameras_need_a_fresh_frame():
    engine = make_engine()
    engine.apply(Observation(step_id="s1", status=C, evidence="x", frames={1: 1, 2: 1}))
    events = engine.apply(Observation(step_id="s1", status=C, evidence="x", frames={1: 2, 2: 1}))
    assert events[0].detail == "stale_frame"


def test_observation_without_frames_is_ignored():
    engine = make_engine()
    events = engine.apply(Observation(step_id="s1", status=C, evidence="x", frames={}))
    assert events[0].detail == "no_frames"


def test_incomplete_resets_the_counter():
    engine, feed = make_engine(), Feed()
    engine.apply(feed.obs(C))
    engine.apply(feed.obs(C))
    engine.apply(feed.obs(I))
    assert engine.active_record.confirmations == 0
    assert engine.active_record.evidence == []
    assert engine.active_record.state is StepState.ACTIVE


def test_uncertain_resets_the_counter():
    engine, feed = make_engine(), Feed()
    engine.apply(feed.obs(C))
    engine.apply(feed.obs(U))
    assert engine.active_record.confirmations == 0
    assert engine.active_record.state is StepState.UNCERTAIN


def test_out_of_sequence_observation_is_rejected():
    engine, feed = make_engine(), Feed()
    events = engine.apply(feed.obs(C, step_id="s2"))
    assert events[0].detail == "wrong_step"
    assert engine.records[1].confirmations == 0


def test_transition_required_blocks_a_state_that_was_already_true():
    engine, feed = make_engine(step("s1", requires_transition=True)), Feed()
    for _ in range(5):
        events = engine.apply(feed.obs(C))
    assert events[0].detail == "awaiting_transition"
    assert engine.active_record.confirmations == 0


def test_transition_required_passes_after_seeing_unfinished_state():
    engine, feed = make_engine(step("s1", requires_transition=True)), Feed()
    engine.apply(feed.obs(I))
    for _ in range(3):
        engine.apply(feed.obs(C))
    assert engine.finished


def test_static_completed_state_passes_by_default():
    engine, feed = make_engine(step("s1")), Feed()
    for _ in range(3):
        engine.apply(feed.obs(C))
    assert engine.finished


def test_deviation_is_suspected_before_confirmed():
    engine, feed = make_engine(), Feed()
    assert types(engine.apply(feed.obs(I, deviation="sluitring ontbreekt"))) == [EventType.DEVIATION_SUSPECTED]
    assert engine.active_record.state is StepState.UNCERTAIN
    engine.apply(feed.obs(I, deviation="sluitring ontbreekt"))
    assert types(engine.apply(feed.obs(I, deviation="sluitring ontbreekt"))) == [EventType.DEVIATION_CONFIRMED]
    assert engine.active_record.state is StepState.DEVIATION


def test_step_can_still_complete_after_a_deviation():
    engine, feed = make_engine(), Feed()
    for _ in range(3):
        engine.apply(feed.obs(I, deviation="fout"))
    for _ in range(3):
        engine.apply(feed.obs(C))
    assert engine.records[0].state is StepState.COMPLETED
    assert engine.records[0].deviation is None


def test_manual_confirmation_is_recorded_as_manual():
    engine = make_engine()
    events = engine.confirm_manually()
    assert events[0].detail == "manual"
    assert engine.records[0].method is ConfirmationMethod.MANUAL


def test_reject_and_reset_clear_progress():
    engine, feed = make_engine(step("s1", requires_transition=True)), Feed()
    engine.apply(feed.obs(I))
    engine.apply(feed.obs(C))
    engine.reject_completion()
    assert engine.active_record.confirmations == 0
    assert engine.active_record.seen_incomplete is False


def test_model_switch_keeps_completed_steps():
    engine, feed = make_engine(), Feed()
    for _ in range(3):
        engine.apply(feed.obs(C))
    engine.apply(feed.obs(C, step_id="s2"))
    engine.reset_counters()
    assert engine.records[0].state is StepState.COMPLETED
    assert engine.records[1].confirmations == 0


def test_restart_clears_everything_and_frame_history():
    engine, feed = make_engine(), Feed()
    for _ in range(3):
        engine.apply(feed.obs(C))
    engine.start()
    assert engine.progress == 0
    assert engine.active_step.id == "s1"
    engine.apply(Observation(step_id="s1", status=C, evidence="x", frames={1: 1}))
    assert engine.active_record.confirmations == 1


def test_workflow_finishes_and_ignores_later_input():
    engine, feed = make_engine(step("s1")), Feed()
    events = [engine.apply(feed.obs(C)) for _ in range(3)][-1]
    assert types(events) == [EventType.STEP_CONFIRMED, EventType.WORKFLOW_COMPLETED]
    assert engine.progress == 1
    assert engine.apply(feed.obs(C))[0].detail == "not_running"


def test_step_can_override_required_confirmations():
    engine, feed = make_engine(step("s1", required_confirmations=1)), Feed()
    engine.apply(feed.obs(C))
    assert engine.finished


def test_simulated_observation_cannot_drive_a_live_workflow():
    engine, feed = make_engine(), Feed()
    assert engine.apply(feed.obs(C, simulated=True))[0].detail == "simulation_mismatch"


def test_simulation_uses_the_same_rules():
    engine, feed = make_engine(step("s1"), simulated=True), Feed()
    engine.apply(feed.obs(C, simulated=True))
    assert not engine.finished
    for _ in range(2):
        engine.apply(feed.obs(C, simulated=True))
    assert engine.records[0].method is ConfirmationMethod.SIMULATED
