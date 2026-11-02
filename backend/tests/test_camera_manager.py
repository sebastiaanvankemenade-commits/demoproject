import numpy as np

from app.camera_manager import CameraManager
from app.cameras.base import CameraInfo, LatestFrame
from app.settings_store import SettingsStore


class FakeCapture:
    def __init__(self, device_id, fail=False):
        self.device_id = device_id
        self.width, self.height = 1920, 1080
        self.buffer = LatestFrame()

    def start(self):
        self.buffer.put(np.zeros((1080, 1920, 3), np.uint8))

    def stop(self):
        pass


class FakeBackend:
    CameraOpenError = RuntimeError
    MacCameraCapture = FakeCapture

    def __init__(self, keys):
        self.keys = keys

    def discover(self):
        return [CameraInfo(key=k, device_id=f"id-{k}", name="Cam") for k in self.keys]


def manager(tmp_path, keys) -> CameraManager:
    return CameraManager(SettingsStore(tmp_path / "s.json"), backend=FakeBackend(keys))


def test_cameras_fill_slots_and_assignment_is_persisted(tmp_path):
    cams = manager(tmp_path, ["A", "B"])
    cams.sync()
    assert (cams.slots[1].key, cams.slots[2].key) == ("A", "B")
    again = CameraManager(SettingsStore(tmp_path / "s.json"), backend=FakeBackend(["A", "B"]))
    assert (again.slots[1].key, again.slots[2].key) == ("A", "B")


def test_assignment_survives_discovery_order(tmp_path):
    manager(tmp_path, ["A", "B"]).sync()
    cams = CameraManager(SettingsStore(tmp_path / "s.json"), backend=FakeBackend(["B", "A"]))
    cams.sync()
    assert cams.slots[1].key == "A"


def test_single_camera_works(tmp_path):
    cams = manager(tmp_path, ["A"])
    cams.sync()
    assert len(cams.frames("both")) == 1
    assert cams.status()[1]["error"] == "Camera niet verbonden."


def test_swap_exchanges_views(tmp_path):
    cams = manager(tmp_path, ["A", "B"])
    cams.sync()
    cams.swap()
    assert (cams.slots[1].key, cams.slots[2].key) == ("B", "A")
    assert cams.slots[1].capture.device_id == "id-B"


def test_frame_numbers_keep_rising_across_captures():
    first, second = LatestFrame(), LatestFrame()
    image = np.zeros((2, 2, 3), np.uint8)
    first.put(image)
    second.put(image)
    assert second.get().sequence > first.get().sequence
