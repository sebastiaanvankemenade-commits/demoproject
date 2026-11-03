"""Stored images played back through the camera interface, for work without cameras.

Only active when explicitly started with a test folder. The dashboard labels it on every
view, because stored images must never pass for live camera output.
"""
import threading
from pathlib import Path

import cv2
import numpy as np

from .base import CameraInfo, CameraMode, LatestFrame

VIEWS = ("top", "side")
EXTENSIONS = (".png", ".jpg", ".jpeg", ".mp4", ".mov")
FPS = 4
MAX_CLIP_FRAMES = 900
NOISE = 3


class CameraOpenError(Exception):
    pass


class FileCapture:
    def __init__(self, source: "TestSource", view: str):
        self.source = source
        self.view = view
        self.width, self.height = 1920, 1080
        self.buffer = LatestFrame()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        rng = np.random.default_rng()
        tick = 0
        while not self._stop.wait(1 / self.source.rate(self.view)):
            image = self.source.image(self.view, tick)
            tick += 1
            if image is None:
                continue
            # Sensor-like noise: identical images would be answered from Ollama's cache.
            noise = rng.integers(-NOISE, NOISE + 1, image.shape, dtype=np.int16)
            self.buffer.put(np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8))

    def stop(self) -> None:
        self._stop.set()


class TestSource:
    """Camera backend. A scene is a pair of files: <scene>_top and <scene>_side."""

    __test__ = False  # Not a pytest class, despite the name.
    CameraOpenError = CameraOpenError

    def __init__(self, folder: Path):
        self.folder = folder
        self._cache: dict[tuple[str, str], tuple[list[np.ndarray], float]] = {}
        scenes = self.scenes()
        self.scene = scenes[0] if scenes else None

    def scenes(self) -> list[str]:
        names = {
            path.stem.removesuffix("_top")
            for path in self.folder.glob("*_top.*")
            if path.suffix.lower() in EXTENSIONS
        }
        return sorted(names)

    def select(self, scene: str) -> None:
        if scene not in self.scenes():
            raise ValueError(scene)
        self.scene = scene

    def _frames(self, view: str) -> tuple[list[np.ndarray], float]:
        key = (self.scene, view)
        if key not in self._cache:
            self._cache[key] = self._load(view)
        return self._cache[key]

    def image(self, view: str, tick: int = 0) -> np.ndarray | None:
        frames, _ = self._frames(view)
        return frames[tick % len(frames)] if frames else None

    def rate(self, view: str) -> float:
        return self._frames(view)[1]

    def _load(self, view: str) -> tuple[list[np.ndarray], float]:
        for extension in EXTENSIONS:
            path = self.folder / f"{self.scene}_{view}{extension}"
            if not path.exists():
                continue
            if extension in (".mp4", ".mov"):
                return self._load_clip(path)
            return [cv2.imread(str(path))], FPS
        return [], FPS

    @staticmethod
    def _load_clip(path: Path) -> tuple[list[np.ndarray], float]:
        clip = cv2.VideoCapture(str(path))
        rate = clip.get(cv2.CAP_PROP_FPS) or FPS
        frames = []
        while len(frames) < MAX_CLIP_FRAMES:
            ok, frame = clip.read()
            if not ok:
                break
            frames.append(frame)
        clip.release()
        return frames, rate

    def discover(self) -> list[CameraInfo]:
        # Numbered keys: slots fill in sorted order, and "side" would otherwise take camera 1.
        return [
            CameraInfo(
                key=f"test-{number}-{view}",
                device_id=view,
                name=f"Testbeelden ({view})",
                modes=[CameraMode(width=1920, height=1080, fps=[FPS])],
            )
            for number, view in enumerate(VIEWS, start=1)
        ]

    def Capture(self, device_id: str) -> FileCapture:
        return FileCapture(self, device_id)
