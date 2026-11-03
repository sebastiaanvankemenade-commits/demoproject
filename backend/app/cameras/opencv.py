"""Camera capture through OpenCV, for Windows and Linux.

On Linux every camera has a stable name with its USB serial under /dev/v4l/by-id, so the
assignment survives replugging, like the serial on macOS. Windows offers no such name
through OpenCV: cameras are found by number, which can change after replugging. The
"Wissel camera's" button and the work mat cover that.
"""
import sys
import threading
import time
from pathlib import Path

import cv2

from .base import CameraInfo, CameraMode, LatestFrame

MAX_INDEX = 6  # how many camera numbers Windows is searched for
BY_ID = Path("/dev/v4l/by-id")


class CameraOpenError(Exception):
    pass


# Cameras this process has open. Opening them again just to list them would fail or steal them.
_open: dict[str, "OpenCvCapture"] = {}


def _backend() -> int:
    if sys.platform == "win32":
        return cv2.CAP_DSHOW  # MSMF opens Facecams slowly and often at a lower resolution
    if sys.platform.startswith("linux"):
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


def _source(device_id: str):
    """A camera number on Windows, a device path on Linux."""
    return int(device_id) if device_id.isdigit() else device_id


def discover() -> list[CameraInfo]:
    if sys.platform.startswith("linux") and BY_ID.exists():
        return [
            CameraInfo(key=path.name.removesuffix("-video-index0"), device_id=str(path), name=path.name)
            for path in sorted(BY_ID.glob("*-video-index0"))
        ]
    cameras = []
    for index in range(MAX_INDEX):
        device_id = str(index)
        if device_id not in _open:
            probe = cv2.VideoCapture(index, _backend())
            present = probe.isOpened()
            probe.release()
            if not present:
                continue
        cameras.append(
            CameraInfo(
                key=f"camera-{index}",
                device_id=device_id,
                name=f"Camera {index}",
                modes=[CameraMode(width=1920, height=1080, fps=[30.0])],
            )
        )
    return cameras


class OpenCvCapture:
    def __init__(self, device_id: str, width: int = 1920, height: int = 1080, fps: float = 30.0):
        self.device_id = device_id
        self.width, self.height, self.fps = width, height, fps
        self.buffer = LatestFrame()
        self._capture: cv2.VideoCapture | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        capture = cv2.VideoCapture(_source(self.device_id), _backend())
        if not capture.isOpened():
            raise CameraOpenError("camera kon niet worden geopend")
        # Uncompressed 1080p does not fit through USB at 30 FPS; the Facecam sends MJPEG for that.
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        capture.set(cv2.CAP_PROP_FPS, self.fps)
        # Many cameras need a few frames to wake up; the first reads can come back empty.
        deadline = time.monotonic() + 3
        ok, frame = capture.read()
        while (not ok or frame is None) and time.monotonic() < deadline:
            time.sleep(0.1)
            ok, frame = capture.read()
        if not ok or frame is None:
            capture.release()
            raise CameraOpenError("camera levert geen beeld")
        # Report what the camera really gives, not what was asked.
        self.height, self.width = frame.shape[:2]
        self.buffer.put(frame)
        self._capture = capture
        _open[self.device_id] = self
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            ok, frame = self._capture.read()
            if ok and frame is not None:
                failures = 0
                self.buffer.put(frame)
                continue
            # An unplugged camera stops delivering; the manager notices the stale buffer and reopens.
            failures += 1
            if failures > 30:
                break
            time.sleep(0.05)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        _open.pop(self.device_id, None)


Capture = OpenCvCapture
