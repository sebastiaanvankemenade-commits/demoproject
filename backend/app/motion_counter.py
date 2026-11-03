"""Counts repeated turning movements with optical flow, without the model.

An analysis takes about 20 s and a turn about a second, so the model cannot see them happen.
This runs on every frame instead. It counts back-and-forth movements of whatever moves in the
counting area: that is the hand, not proof of how far the screw went in.
"""
from collections import deque

import cv2
import numpy as np

WORK_WIDTH = 160
NOISE_PX = 0.25  # per frame; smaller flow is sensor noise
MIN_MOVING_SHARE = 0.003
ENTER_SPEED = 4.0  # px/s at WORK_WIDTH, along the main direction of movement
MIN_TRAVEL = 1.5  # px at WORK_WIDTH; a smaller stroke is jitter
STOPPED_S = 0.7  # a pause this long ends a movement
BURST_GAP_S = 3.0  # turns further apart belong to separate bursts
AXIS_WINDOW_S = 3.0


def motion_sample(previous: np.ndarray, current: np.ndarray, dt: float) -> np.ndarray:
    """(sideways, up-down, rotation) of the moving pixels, in px/s."""
    flow = cv2.calcOpticalFlowFarneback(previous, current, None, 0.5, 2, 15, 2, 5, 1.1, 0)
    fx, fy = flow[..., 0], flow[..., 1]
    moving = np.hypot(fx, fy) > NOISE_PX
    if moving.mean() < MIN_MOVING_SHARE:
        return np.zeros(3)
    rows, columns = np.nonzero(moving)
    rx, ry = columns - columns.mean(), rows - rows.mean()
    radius = np.maximum(np.hypot(rx, ry), 1.0)
    # A handle turning around its own centre has no net sideways movement, only rotation.
    rotation = ((-ry * fx[moving] + rx * fy[moving]) / radius).mean()
    return np.array([fx[moving].mean(), fy[moving].mean(), rotation]) / dt


class TurnCounter:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._previous: np.ndarray | None = None
        self._previous_at = 0.0
        self._samples: deque[tuple[float, np.ndarray]] = deque()
        self._axis: np.ndarray | None = None
        self._smooth: deque[float] = deque(maxlen=2)
        self._direction = 0
        self._travel = 0.0
        self._strokes = 0
        self._last_motion = 0.0
        self._last_turn = -BURST_GAP_S * 2
        self._held = False

    def feed(self, gray: np.ndarray, now: float) -> int:
        """Takes one grayscale frame and returns how many turns it completed."""
        height, width = gray.shape[:2]
        small = cv2.resize(gray, (WORK_WIDTH, max(8, round(height * WORK_WIDTH / width))), interpolation=cv2.INTER_AREA)
        previous, previous_at = self._previous, self._previous_at
        self._previous, self._previous_at = small, now
        if previous is None or previous.shape != small.shape or now <= previous_at:
            return 0
        dt = now - previous_at
        return self._follow(self._project(motion_sample(previous, small, dt), now), dt, now)

    def _project(self, sample: np.ndarray, now: float) -> float:
        """Reduces movement to the one direction it has been repeating in."""
        self._samples.append((now, sample))
        while now - self._samples[0][0] > AXIS_WINDOW_S:
            self._samples.popleft()
        vectors = np.array([vector for _, vector in self._samples])
        _, axes = np.linalg.eigh(vectors.T @ vectors)
        axis = axes[:, -1]
        if self._axis is not None and axis @ self._axis < 0:
            axis = -axis
        self._axis = axis
        self._smooth.append(float(sample @ axis))
        return sum(self._smooth) / len(self._smooth)

    def _follow(self, speed: float, dt: float, now: float) -> int:
        direction = 1 if speed > ENTER_SPEED else -1 if speed < -ENTER_SPEED else 0
        counted = 0
        if direction:
            self._last_motion = now
            if direction != self._direction:
                counted = self._close_stroke(now)
                self._direction = direction
            self._travel += abs(speed) * dt
        elif self._direction and now - self._last_motion > STOPPED_S:
            counted = self._close_stroke(now)
            self._direction = 0
            self._strokes = 0
        if self._held and now - self._last_turn > BURST_GAP_S:
            self._held = False
        return counted

    def _close_stroke(self, now: float) -> int:
        real = self._travel >= MIN_TRAVEL
        self._travel = 0.0
        if not real:
            return 0
        self._strokes += 1
        if self._strokes < 2:
            return 0
        self._strokes = 0
        return self._turn(now)

    def _turn(self, now: float) -> int:
        """One back-and-forth alone is also what a hand reaching in and out looks like,
        so a first turn only counts once a second one follows."""
        continuing = now - self._last_turn <= BURST_GAP_S
        held, self._held = self._held and continuing, False
        first = not continuing
        self._last_turn = now
        if first:
            self._held = True
            return 0
        return 2 if held else 1
