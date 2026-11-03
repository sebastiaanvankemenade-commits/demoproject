"""Watching a demonstration: when a step happens, and which pictures show it.

Movement in the work area marks a step; a few seconds of stillness after it ends the step.
The model gets a short filmstrip of each step instead of only a before and after picture,
so it can see what the hands did.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

from .inference_service import CameraFrame

WORK_WIDTH = 160
PIXEL_CHANGE = 14  # grey levels; less is sensor noise
ACTIVE_SHARE = 0.01  # share of changed pixels that counts as movement
STILL_SHARE = 0.003
STILL_S = 2.5  # stillness after movement that ends a step
MIN_ACTION_S = 1.0  # shorter movement is a hand passing by
MAX_STRIP = 8
MAX_BUFFER = 60


def motion(previous: np.ndarray, current: np.ndarray) -> float:
    """Share of pixels that changed between two small grayscale pictures."""
    return float((cv2.absdiff(previous, current) > PIXEL_CHANGE).mean())


def small_gray(image: np.ndarray) -> np.ndarray:
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    return cv2.resize(gray, (WORK_WIDTH, max(8, round(height * WORK_WIDTH / width))), interpolation=cv2.INTER_AREA)


class StepSegmenter:
    """Says when a step starts and ends, from movement alone."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._previous: np.ndarray | None = None
        self.moving = False
        self._started = 0.0
        self._last_motion = 0.0

    def feed(self, gray: np.ndarray, now: float) -> tuple[float, bool]:
        """Returns (movement, step finished)."""
        previous, self._previous = self._previous, gray
        if previous is None or previous.shape != gray.shape:
            return 0.0, False
        amount = motion(previous, gray)
        if amount >= ACTIVE_SHARE:
            if not self.moving:
                self.moving, self._started = True, now
            self._last_motion = now
        elif self.moving and amount < STILL_SHARE and now - self._last_motion >= STILL_S:
            self.moving = False
            return amount, self._last_motion - self._started >= MIN_ACTION_S
        return amount, False


@dataclass
class Filmstrip:
    """Pictures of one step, bounded: a long step keeps every other picture."""

    frames: list[tuple[float, float, CameraFrame]] = field(default_factory=list)  # (time, movement, frame)

    def add(self, now: float, movement: float, frame: CameraFrame) -> None:
        self.frames.append((now, movement, frame))
        if len(self.frames) > MAX_BUFFER:
            # Keep the first picture: it is the situation before the step.
            self.frames = self.frames[:1] + self.frames[2::2]

    def select(self, after: CameraFrame, count: int = MAX_STRIP) -> list[CameraFrame]:
        """Before, the moments with most movement in time order, and after."""
        if not self.frames:
            return [after]
        before, middle = self.frames[0], self.frames[1:]
        busiest = sorted(sorted(middle, key=lambda item: item[1], reverse=True)[: count - 2], key=lambda item: item[0])
        return [before[2], *(frame for _, _, frame in busiest), after]

    def span_s(self) -> float:
        return self.frames[-1][0] - self.frames[0][0] if len(self.frames) > 1 else 0.0
