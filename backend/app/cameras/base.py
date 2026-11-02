"""Platform-neutral camera types. Everything OS-specific lives in a sibling module."""
import itertools
import threading
import time
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel


class CameraMode(BaseModel):
    width: int
    height: int
    fps: list[float]


class CameraInfo(BaseModel):
    # Stable identity for assignments: the USB serial when available, else the OS id.
    key: str
    device_id: str
    name: str
    serial: str | None = None
    usb_speed: str | None = None
    modes: list[CameraMode] = []


@dataclass(frozen=True)
class Frame:
    sequence: int
    captured_at: float
    image: np.ndarray


# Shared by all buffers so numbers keep rising across a reconnect or camera swap;
# the workflow engine treats a lower number as a stale frame.
_sequences = itertools.count(1)


class LatestFrame:
    """Bounded buffer of one frame: capture overwrites, readers never queue up old images."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Frame | None = None
        self._window: list[float] = []

    def put(self, image: np.ndarray) -> None:
        now = time.monotonic()
        with self._lock:
            self._frame = Frame(next(_sequences), now, image)
            self._window.append(now)
            if len(self._window) > 120:
                del self._window[0]

    def get(self) -> Frame | None:
        with self._lock:
            return self._frame

    def measured_fps(self) -> float:
        with self._lock:
            window = list(self._window)
        if len(window) < 2 or time.monotonic() - window[-1] > 2:
            return 0.0
        return (len(window) - 1) / (window[-1] - window[0])
