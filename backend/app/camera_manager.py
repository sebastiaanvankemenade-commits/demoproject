"""Logical camera slots on top of a platform capture backend. A missing camera is a normal state."""
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import calibration, workmat
from .cameras.base import Frame
from .cameras.testsource import TestSource
from .inference_service import CameraFrame
from .observation import Detection
from .settings_store import DATA_DIR, Calibration, CountArea, Roi, SettingsStore

MAX_FRAME_AGE_S = 2.0
MAT_MISSES = 3  # a hand over the markers for a moment is not a lost mat
# The mat is found anew every few seconds and its outline jitters a little. Smaller changes than
# this keep the area as it is: at 0.5% the jitter wiped the confirmations of the active step every 5 s.
MAT_TOLERANCE = 0.02
SLOT_LABELS = {1: "Bovenaanzicht", 2: "Zijaanzicht"}
SLOT_VIEWS = {1: "top", 2: "side"}


def load_backend():
    if sys.platform == "darwin":
        from .cameras import macos

        return macos
    from .cameras import opencv

    return opencv


@dataclass
class Slot:
    number: int
    key: str | None = None
    capture: object = None
    width: int = 0
    height: int = 0
    error: str | None = None
    opened_at: float = field(default=0.0)


def _differs(old: Roi | None, new: Roi, tolerance: float = 0.005) -> bool:
    if old is None:
        return True
    return any(abs(getattr(old, side) - getattr(new, side)) > tolerance for side in ("x", "y", "w", "h"))


class CameraManager:
    def __init__(self, store: SettingsStore, backend=None):
        self.store = store
        self.backend = backend if backend is not None else load_backend()
        self.slots = {number: Slot(number) for number in SLOT_LABELS}
        self._lock = threading.Lock()
        # Next to the settings file, so the test views and tests keep their own references.
        self.calibration_dir = store.path.parent / "calibration"
        # camera number -> outcome of the last check
        self.calibration_state: dict[int, dict] = {}
        self._references: dict[str, tuple[str, np.ndarray]] = {}
        self.mat_state: dict[int, dict] = {}
        self._mat_misses: dict[int, int] = {}
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
        capture = self.backend.Capture(camera.device_id)
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

    @property
    def test_source(self) -> TestSource | None:
        return self.backend if isinstance(self.backend, TestSource) else None

    def _roi(self, slot: Slot) -> Roi | None:
        return self.store.settings.rois.get(slot.key) if slot.key else None

    def set_roi(self, number: int, roi: Roi | None) -> None:
        key = self.slots[number].key
        if key is None:
            raise ValueError("no camera in this slot")
        if roi is None:
            self.store.settings.rois.pop(key, None)
        else:
            self.store.settings.rois[key] = roi
        self.store.save()
        self.calibrate(number)

    def set_count_area(self, number: int, roi: Roi | None) -> None:
        key = self.slots[number].key
        if key is None:
            raise ValueError("no camera in this slot")
        mat = None
        frame = self._fresh_frame(self.slots[number])
        if roi and frame is not None and self.store.settings.auto_work_area:
            view = workmat.locate(frame.image)
            size = (frame.image.shape[1], frame.image.shape[0])
            mat = workmat.to_mat(view, roi, size) if view else None
        self.store.settings.count_area = CountArea(key=key, roi=roi, mat=mat) if roi else None
        self.store.save()
        self.calibrate(number)

    def check_workmat(self, number: int) -> dict | None:
        """Finds the mat and puts the work and counting area on it. Blocking.

        Returns None when there is no automatic work area or no picture to look at.
        """
        slot = self.slots[number]
        frame = self._fresh_frame(slot)
        if not self.store.settings.auto_work_area or frame is None or slot.key is None:
            return None
        previous = self.mat_state.get(number, {}).get("found")
        view = workmat.locate(frame.image)
        if view is None:
            self._mat_misses[number] = self._mat_misses.get(number, 0) + 1
            found = bool(previous) and self._mat_misses[number] < MAT_MISSES
            self.mat_state[number] = {"found": found, "markers": 0}
            return {"found": found, "changed": found != previous and previous is not None, "moved": False}
        self._mat_misses[number] = 0
        size = (frame.image.shape[1], frame.image.shape[0])
        settings = self.store.settings
        moved = False
        roi = workmat.mat_area(view, size)
        if roi and _differs(settings.rois.get(slot.key), roi, MAT_TOLERANCE):
            settings.rois[slot.key] = roi
            moved = True
        area = settings.count_area
        if area and area.key == slot.key and area.mat:
            count = workmat.to_image(view, area.mat, size)
            if count and _differs(area.roi, count, MAT_TOLERANCE):
                settings.count_area = CountArea(key=slot.key, roi=count, mat=area.mat)
                moved = True
        if moved:
            self.store.save()
        self.mat_state[number] = {"found": True, "markers": view.markers}
        return {"found": True, "changed": previous is not True, "moved": moved}

    def _reference_path(self, key: str) -> Path:
        return self.calibration_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '_', key)}.png"

    def calibrate(self, number: int) -> bool:
        """The current picture becomes the reference for this camera's areas. Blocking."""
        slot = self.slots[number]
        frame = self._fresh_frame(slot)
        if frame is None or slot.key is None:
            return False
        self.calibration_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(self._reference_path(slot.key)), calibration.prepare(frame.image))
        area = self.store.settings.count_area
        self.store.settings.calibrations[slot.key] = Calibration(
            roi=self._roi(slot),
            count_area=area.roi if area and area.key == slot.key else None,
            saved_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.store.save()
        self.calibration_state[number] = {"state": "ok", "shift": 0.0}
        return True

    def _reference(self, key: str, saved_at: str) -> np.ndarray | None:
        cached = self._references.get(key)
        if cached and cached[0] == saved_at:
            return cached[1]
        image = cv2.imread(str(self._reference_path(key)), cv2.IMREAD_GRAYSCALE)
        if image is not None:
            self._references[key] = (saved_at, image)
        return image

    def reference_jpeg(self, number: int) -> bytes | None:
        key = self.slots[number].key
        stored = self.store.settings.calibrations.get(key) if key else None
        image = self._reference(key, stored.saved_at) if stored else None
        if image is None:
            return None
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buffer.tobytes() if ok else None

    def check_calibration(self, number: int) -> dict | None:
        """Compares with the reference and moves the areas along when that is safe. Blocking.

        Returns the outcome, or None when there is nothing to compare.
        """
        slot = self.slots[number]
        stored = self.store.settings.calibrations.get(slot.key) if slot.key else None
        frame = self._fresh_frame(slot)
        reference = self._reference(slot.key, stored.saved_at) if stored and frame else None
        if reference is None:
            return None
        current = calibration.prepare(frame.image)
        shift = calibration.measure(reference, current)
        if shift is None:
            outcome = {"state": "lost", "shift": None}
        elif shift.amount < calibration.STILL:
            outcome = {"state": "ok", "shift": shift.amount}
            outcome["moved"] = self._place_areas(slot.key, stored.roi, stored.count_area)
        elif shift.amount > calibration.MAX_SHIFT:
            outcome = {"state": "lost", "shift": shift.amount}
        else:
            size = (current.shape[1], current.shape[0])
            roi = calibration.move_area(stored.roi, shift, size) if stored.roi else None
            count = calibration.move_area(stored.count_area, shift, size) if stored.count_area else None
            if (stored.roi and roi is None) or (stored.count_area and count is None):
                outcome = {"state": "lost", "shift": shift.amount}
            else:
                outcome = {"state": "corrected", "shift": shift.amount}
                outcome["moved"] = self._place_areas(slot.key, roi, count)
        outcome["changed"] = outcome["state"] != self.calibration_state.get(number, {}).get("state")
        self.calibration_state[number] = {"state": outcome["state"], "shift": outcome["shift"]}
        return outcome

    def _place_areas(self, key: str, roi: Roi | None, count: Roi | None) -> bool:
        """Writes corrected areas without touching the reference they were derived from.

        Returns whether an area really moved; the same small shift measured again does not count.
        """
        settings = self.store.settings
        moved = False
        if roi:
            moved |= _differs(settings.rois.get(key), roi)
            settings.rois[key] = roi
        if count and settings.count_area and settings.count_area.key == key:
            moved |= _differs(settings.count_area.roi, count)
            settings.count_area = CountArea(key=key, roi=count)
        if moved:
            self.store.save()
        return moved

    def count_frame(self) -> Frame | None:
        """Newest grayscale picture of the counting area, if a camera has one."""
        area = self.store.settings.count_area
        slot = next((s for s in self.slots.values() if area and s.key == area.key), None)
        frame = self._fresh_frame(slot) if slot else None
        if frame is None:
            return None
        gray = cv2.cvtColor(self._crop(frame.image, area.roi), cv2.COLOR_BGR2GRAY)
        return Frame(frame.sequence, frame.captured_at, gray)

    @staticmethod
    def _crop(image: np.ndarray, roi: Roi | None) -> np.ndarray:
        if roi is None:
            return image
        height, width = image.shape[:2]
        left, top = round(roi.x * width), round(roi.y * height)
        return image[top : top + round(roi.h * height), left : left + round(roi.w * width)]

    def to_full_image(self, number: int, box: Detection) -> Detection:
        """Boxes come from the cropped work area; the live view shows the whole image."""
        roi = self._roi(self.slots[number])
        if roi is None:
            return box
        return box.model_copy(
            update={"x": roi.x + box.x * roi.w, "y": roi.y + box.y * roi.h, "w": box.w * roi.w, "h": box.h * roi.h}
        )

    def frames(self, mode: str) -> list[CameraFrame]:
        numbers = [1, 2] if mode == "both" else [int(mode)]
        frames = []
        for number in numbers:
            slot = self.slots[number]
            frame = self._fresh_frame(slot)
            if frame is not None:
                frames.append(CameraFrame(number, frame.sequence, self._crop(frame.image, self._roi(slot))))
        return frames

    def save_snapshot(self, name: str, folder: Path | None = None) -> int:
        """Store full frames as a scene that the test source can replay. Blocking."""
        folder = folder or DATA_DIR / "snapshots"
        folder.mkdir(parents=True, exist_ok=True)
        saved = 0
        for number, slot in self.slots.items():
            frame = self._fresh_frame(slot)
            if frame is not None:
                cv2.imwrite(str(folder / f"{name}_{SLOT_VIEWS[number]}.jpg"), frame.image, [cv2.IMWRITE_JPEG_QUALITY, 92])
                saved += 1
        return saved

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
            area = self.store.settings.count_area
            rows.append(
                {
                    "slot": number,
                    "label": SLOT_LABELS[number],
                    "connected": connected,
                    "fps": round(slot.capture.buffer.measured_fps(), 1) if slot.capture else 0,
                    "width": slot.width,
                    "height": slot.height,
                    "serial": slot.key,
                    "roi": roi.model_dump() if (roi := self._roi(slot)) else None,
                    "count_area": area.roi.model_dump() if area and area.key == slot.key else None,
                    "calibrated_at": stored.saved_at
                    if slot.key and (stored := self.store.settings.calibrations.get(slot.key))
                    else None,
                    "calibration": self.calibration_state.get(number),
                    "workmat": self.mat_state.get(number) if self.store.settings.auto_work_area else None,
                    "error": None if connected else slot.error or "Wachten op beeld…",
                }
            )
        return rows

    def stop(self) -> None:
        with self._lock:
            for slot in self.slots.values():
                self._close(slot)
