"""Logical camera slots on top of a platform capture backend. A missing camera is a normal state."""
import sys
import threading
import time
from dataclasses import dataclass, field

import cv2

from .cameras.base import Frame
from .inference_service import CameraFrame
from .settings_store import SettingsStore

MAX_FRAME_AGE_S = 2.0
SLOT_LABELS = {1: "Bovenaanzicht", 2: "Zijaanzicht"}


def load_backend():
    if sys.platform == "darwin":
        from .cameras import macos

        return macos
    return None


@dataclass
class Slot:
    number: int
    key: str | None = None
    capture: object = None
    width: int = 0
    height: int = 0
    error: str | None = None
    opened_at: float = field(default=0.0)


class CameraManager:
    def __init__(self, store: SettingsStore, backend=None):
        self.store = store
        self.backend = backend if backend is not None else load_backend()
        self.slots = {number: Slot(number) for number in SLOT_LABELS}
        self._lock = threading.Lock()
        for number, slot in self.slots.items():
            slot.key = store.settings.camera_keys.get(str(number))

    def healthy(self, slot: Slot) -> bool:
        return self._fresh_frame(slot) is not None

    def _fresh_frame(self, slot: Slot) -> Frame | None:
        if slot.capture is None:
            return None
        frame = slot.capture.buffer.get()
        if frame is None or time.monotonic() - frame.captured_at > MAX_FRAME_AGE_S:
            return None
        return frame

    def all_healthy(self) -> bool:
        return all(self.healthy(slot) for slot in self.slots.values())

    def sync(self) -> None:
        """Discover cameras and (re)open slots that have no live picture. Blocking."""
        if self.backend is None:
            for slot in self.slots.values():
                slot.error = "Geen camera-ondersteuning op dit platform."
            return
        cameras = {camera.key: camera for camera in self.backend.discover()}
        with self._lock:
            self._assign(cameras)
            for slot in self.slots.values():
                self._refresh(slot, cameras)

    def _assign(self, cameras: dict) -> None:
        taken = {slot.key for slot in self.slots.values() if slot.key}
        free = [key for key in sorted(cameras) if key not in taken]
        changed = False
        for slot in self.slots.values():
            if slot.key is None and free:
                slot.key = free.pop(0)
                changed = True
        if changed:
            self._persist()

    def _refresh(self, slot: Slot, cameras: dict) -> None:
        if self.healthy(slot):
            return
        # A just-opened camera needs a moment before its first frame arrives.
        if slot.capture is not None and time.monotonic() - slot.opened_at < 3:
            return
        self._close(slot)
        camera = cameras.get(slot.key)
        if camera is None:
            slot.error = "Camera niet verbonden."
            return
        capture = self.backend.MacCameraCapture(camera.device_id)
        try:
            capture.start()
        except self.backend.CameraOpenError as exc:
            slot.error = f"Camera kon niet starten: {exc}"
            return
        slot.capture, slot.width, slot.height = capture, capture.width, capture.height
        slot.opened_at = time.monotonic()
        slot.error = None

    def _close(self, slot: Slot) -> None:
        if slot.capture is not None:
            slot.capture.stop()
            slot.capture = None

    def _persist(self) -> None:
        keys = {str(n): slot.key for n, slot in self.slots.items() if slot.key}
        self.store.settings.camera_keys = keys
        self.store.save()

    def swap(self) -> None:
        with self._lock:
            one, two = self.slots[1], self.slots[2]
            for name in ("key", "capture", "width", "height", "error", "opened_at"):
                first, second = getattr(one, name), getattr(two, name)
                setattr(one, name, second)
                setattr(two, name, first)
            self._persist()

    def frames(self, mode: str) -> list[CameraFrame]:
        numbers = [1, 2] if mode == "both" else [int(mode)]
        frames = []
        for number in numbers:
            frame = self._fresh_frame(self.slots[number])
            if frame is not None:
                frames.append(CameraFrame(number, frame.sequence, frame.image))
        return frames

    def preview(self, number: int, width: int = 960) -> bytes | None:
        frame = self._fresh_frame(self.slots[number])
        if frame is None:
            return None
        height = round(frame.image.shape[0] * width / frame.image.shape[1])
        small = cv2.resize(frame.image, (width, height), interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buffer.tobytes() if ok else None

    def status(self) -> list[dict]:
        rows = []
        for number, slot in self.slots.items():
            connected = self.healthy(slot)
            rows.append(
                {
                    "slot": number,
                    "label": SLOT_LABELS[number],
                    "connected": connected,
                    "fps": round(slot.capture.buffer.measured_fps(), 1) if slot.capture else 0,
                    "width": slot.width,
                    "height": slot.height,
                    "serial": slot.key,
                    "error": None if connected else slot.error or "Wachten op beeld…",
                }
            )
        return rows

    def stop(self) -> None:
        with self._lock:
            for slot in self.slots.values():
                self._close(slot)
