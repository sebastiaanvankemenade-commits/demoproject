import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "spike"))

from app.motion_counter import TurnCounter
from turn_clip import draw_handle, draw_wrench, passing, turning

FPS = 15


def count(frames, fps: int = FPS, change=lambda frame, index: frame) -> int:
    counter = TurnCounter()
    total = 0
    for index, frame in enumerate(frames):
        gray = cv2.cvtColor(change(frame, index), cv2.COLOR_BGR2GRAY)
        total += counter.feed(gray, index / fps)
    return total


@pytest.mark.parametrize("turns", [2, 3, 6, 10])
def test_counts_a_handle_turning_around_its_own_centre(turns):
    assert count(turning(turns)) == turns


@pytest.mark.parametrize("turns", [3, 6])
def test_counts_a_wrench_swinging_around_the_screw(turns):
    assert count(turning(turns, tool=draw_wrench)) == turns


@pytest.mark.parametrize("hz", [0.5, 1.0, 2.0])
def test_tempo_does_not_change_the_count(hz):
    assert count(turning(6, hz=hz)) == 6


@pytest.mark.parametrize("amplitude", [0.35, 1.2])
def test_small_and_large_movements_count_the_same(amplitude):
    assert count(turning(5, amplitude=amplitude)) == 5


def test_a_lower_frame_rate_counts_the_same():
    assert count(turning(6, fps=8), fps=8) == 6


def test_a_still_scene_counts_nothing():
    assert count(turning(0, idle_s=4)) == 0


def test_a_hand_coming_in_and_leaving_counts_nothing():
    assert count(passing()) == 0


def test_one_isolated_movement_counts_nothing():
    assert count(turning(1)) == 0


def test_flickering_light_counts_nothing():
    def flicker(frame, index):
        return np.clip(frame.astype(np.float32) * (1 + 0.04 * np.sin(index)), 0, 255).astype(np.uint8)

    assert count(turning(0, idle_s=4), change=flicker) == 0


def test_a_pause_between_turns_keeps_counting():
    frames = [*turning(3), *turning(3)]
    assert count(frames) == 6


def test_reset_forgets_a_held_turn():
    counter = TurnCounter()
    for index, frame in enumerate(turning(1)):
        counter.feed(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), index / FPS)
    counter.reset()
    total = 0
    for index, frame in enumerate(turning(1)):
        total += counter.feed(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 100 + index / FPS)
    assert total == 0


def test_a_change_of_size_does_not_crash():
    counter = TurnCounter()
    assert counter.feed(np.zeros((100, 200), np.uint8), 0.0) == 0
    assert counter.feed(np.zeros((300, 200), np.uint8), 0.1) == 0


def test_drawings_are_still_used():
    # Guards the test clip itself: a tool that draws nothing would make every test above pass at 0.
    blank = np.zeros((720, 1280, 3), np.uint8)
    draw_handle(blank, 0.3)
    assert blank.any()


def test_counted_turns_stay_with_the_step_and_never_decide_it():
    from app.default_workflows import SCREW_TIGHTENING
    from app.event_log import describe
    from app.workflow_engine import EventType, StepState, WorkflowEngine

    engine = WorkflowEngine(SCREW_TIGHTENING)
    engine.start()
    engine.add_turns(4)
    assert engine.active_record.turns == 4
    assert engine.active_record.state is StepState.ACTIVE

    events = engine.confirm_manually()
    recorded = next(event for event in events if event.type is EventType.TURNS_RECORDED)
    assert describe(recorded, SCREW_TIGHTENING) == "Stap 1: 4 van 6 draaibewegingen geteld. Minder dan verwacht."


def test_resetting_a_step_clears_its_turns_but_a_model_switch_does_not():
    from app.default_workflows import SCREW_TIGHTENING
    from app.workflow_engine import WorkflowEngine

    engine = WorkflowEngine(SCREW_TIGHTENING)
    engine.start()
    engine.add_turns(3)
    engine.reset_counters()
    assert engine.active_record.turns == 3
    engine.reset_active_step()
    assert engine.active_record.turns == 0


def test_a_clip_plays_through_the_test_source(tmp_path):
    from app.cameras.testsource import TestSource

    writer = cv2.VideoWriter(str(tmp_path / "clip_top.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 15, (320, 240))
    for level in (40, 120, 200):
        writer.write(np.full((240, 320, 3), level, np.uint8))
    writer.release()
    source = TestSource(tmp_path)
    assert source.scenes() == ["clip"]
    assert source.rate("top") == 15
    assert source.image("top", 0).mean() != source.image("top", 2).mean()
    assert source.image("top", 3).mean() == source.image("top", 0).mean()
