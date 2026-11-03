import numpy as np

from app.demonstration import MAX_BUFFER, Filmstrip, StepSegmenter
from app.inference_service import CameraFrame

STEP = 0.5  # seconds between pictures, as in the app


def picture(hand_at: int | None, seed: int) -> np.ndarray:
    """A still table with sensor noise, and optionally a hand at a position."""
    rng = np.random.default_rng(seed)
    image = np.clip(120 + rng.normal(0, 3, (90, 160)), 0, 255).astype(np.uint8)
    if hand_at is not None:
        image[30:60, hand_at : hand_at + 30] = 210
    return image


def run(positions: list[int | None]) -> list[float]:
    """Feeds pictures and returns when steps were reported finished."""
    segmenter = StepSegmenter()
    finished = []
    for index, position in enumerate(positions):
        now = index * STEP
        if segmenter.feed(picture(position, index), now)[1]:
            finished.append(now)
    return finished


def action(seconds: float) -> list[int]:
    return [10 + (i * 17) % 100 for i in range(round(seconds / STEP))]


def stillness(seconds: float, hand_at: int | None = None) -> list[int | None]:
    return [hand_at] * round(seconds / STEP)


def test_movement_then_stillness_is_one_step():
    assert len(run(stillness(2) + action(3) + stillness(4))) == 1


def test_three_actions_with_pauses_are_three_steps():
    positions = stillness(2)
    for _ in range(3):
        positions += action(3) + stillness(4)
    assert len(run(positions)) == 3


def test_a_short_pause_inside_an_action_does_not_split_it():
    assert len(run(stillness(2) + action(2) + stillness(1) + action(2) + stillness(4))) == 1


def test_noise_alone_is_no_step():
    assert run(stillness(20)) == []


def test_a_hand_passing_by_is_no_step():
    assert run(stillness(2) + action(0.5) + stillness(5)) == []


def test_a_resting_hand_counts_as_still():
    # The operator may keep a hand on the mat after placing a part.
    assert len(run(stillness(2) + action(3) + stillness(4, hand_at=50))) == 1


def test_a_step_that_never_comes_to_rest_is_not_finished():
    assert run(stillness(2) + action(10)) == []


def frame(sequence: int) -> CameraFrame:
    return CameraFrame(1, sequence, np.zeros((4, 4, 3), np.uint8))


def test_the_strip_keeps_before_after_and_the_busiest_moments_in_order():
    strip = Filmstrip()
    movements = [0.0, 0.02, 0.3, 0.01, 0.25, 0.4, 0.0, 0.2, 0.05, 0.35, 0.0]
    for sequence, amount in enumerate(movements):
        strip.add(sequence * STEP, amount, frame(sequence))
    chosen = [f.sequence for f in strip.select(frame(99))]
    assert chosen[0] == 0 and chosen[-1] == 99
    assert chosen[1:-1] == [2, 4, 5, 7, 8, 9]  # six busiest, in time order
    assert len(chosen) == 8


def test_a_short_step_sends_what_there_is():
    strip = Filmstrip()
    strip.add(0, 0.0, frame(1))
    strip.add(0.5, 0.2, frame(2))
    assert [f.sequence for f in strip.select(frame(3))] == [1, 2, 3]


def test_a_long_step_stays_bounded_and_keeps_the_start():
    strip = Filmstrip()
    for sequence in range(500):
        strip.add(sequence * STEP, 0.1, frame(sequence))
    assert len(strip.frames) <= MAX_BUFFER
    assert strip.frames[0][2].sequence == 0
    assert strip.span_s() > 200
