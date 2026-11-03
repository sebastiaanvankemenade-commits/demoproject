import time

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.camera_manager import CameraManager
from app.cameras.base import CameraInfo, LatestFrame
from app.cameras.testsource import TestSource
from app.settings_store import Roi, SettingsStore


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
    Capture = FakeCapture

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


def test_work_area_crops_only_the_analysed_frame(tmp_path):
    cams = manager(tmp_path, ["A"])
    cams.sync()
    cams.set_roi(1, Roi(x=0.25, y=0.5, w=0.5, h=0.25))
    assert cams.frames("1")[0].image.shape[:2] == (270, 960)
    assert cams.status()[0]["roi"]["w"] == 0.5
    assert cams.preview(1) is not None
    cams.set_roi(1, None)
    assert cams.frames("1")[0].image.shape[:2] == (1080, 1920)


def test_work_area_follows_the_camera_on_swap(tmp_path):
    cams = manager(tmp_path, ["A", "B"])
    cams.sync()
    cams.set_roi(1, Roi(x=0, y=0, w=0.5, h=0.5))
    cams.swap()
    assert cams.status()[0]["roi"] is None
    assert cams.status()[1]["roi"] is not None


def test_work_area_must_stay_inside_the_image():
    with pytest.raises(ValidationError):
        Roi(x=0.8, y=0, w=0.5, h=0.5)


def test_snapshot_saves_full_frames_as_a_replayable_scene(tmp_path):
    cams = manager(tmp_path, ["A", "B"])
    cams.sync()
    cams.set_roi(1, Roi(x=0, y=0, w=0.5, h=0.5))
    assert cams.save_snapshot("stap1", tmp_path) == 2
    assert cv2.imread(str(tmp_path / "stap1_top.jpg")).shape[:2] == (1080, 1920)
    assert TestSource(tmp_path).scenes() == ["stap1"]


def test_test_source_fills_the_top_view_first(tmp_path):
    cams = CameraManager(SettingsStore(tmp_path / "s.json"), backend=TestSource(tmp_path))
    cams.sync()
    assert cams.slots[1].capture.view == "top"
    assert cams.slots[2].capture.view == "side"
    cams.stop()


def test_test_source_plays_scenes_with_unique_frames(tmp_path):
    for scene, level in (("a", 100), ("b", 150)):
        cv2.imwrite(str(tmp_path / f"{scene}_top.png"), np.full((108, 192, 3), level, np.uint8))
    source = TestSource(tmp_path)
    capture = source.Capture("top")
    capture.start()
    first = wait_for_frame(capture)
    second = wait_for_frame(capture, first.sequence)
    capture.stop()
    assert source.scenes() == ["a", "b"]
    assert not np.array_equal(first.image, second.image)
    source.select("b")
    assert source.image("top").mean() == 150
    assert source.image("side") is None


def wait_for_frame(capture, after: int = 0):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        frame = capture.buffer.get()
        if frame and frame.sequence > after:
            return frame
        time.sleep(0.02)
    raise AssertionError("no frame")


def test_frame_numbers_keep_rising_across_captures():
    first, second = LatestFrame(), LatestFrame()
    image = np.zeros((2, 2, 3), np.uint8)
    first.put(image)
    second.put(image)
    assert second.get().sequence > first.get().sequence


def test_a_box_from_the_work_area_lands_on_the_right_spot_in_the_full_image(tmp_path):
    from app.observation import Detection
    from app.settings_store import Roi

    cams = CameraManager(SettingsStore(tmp_path / "s.json"), backend=TestSource(tmp_path))
    cams.slots[1].key = "cam"
    box = Detection(label="blok", x=0.5, y=0.5, w=0.5, h=0.5)
    assert cams.to_full_image(1, box) == box

    cams.set_roi(1, Roi(x=0.2, y=0.4, w=0.4, h=0.2))
    mapped = cams.to_full_image(1, box)
    assert (mapped.x, mapped.y, mapped.w, mapped.h) == pytest.approx((0.4, 0.5, 0.2, 0.1))
