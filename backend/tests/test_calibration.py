import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "spike"))

from app.calibration import measure, move_area, prepare
from app.settings_store import Roi
from make_scenes import scene

SLOTS_SCENE = scene([("red", 560, 560)])


def moved(image: np.ndarray, dx: float, dy: float, angle: float = 0.0, scale: float = 1.0) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, scale)
    matrix[:, 2] += (dx, dy)
    return cv2.warpAffine(image, matrix, (width, height), borderValue=(60, 60, 60))


def noisy(image: np.ndarray, seed: int) -> np.ndarray:
    noise = np.random.default_rng(seed).integers(-3, 4, image.shape, dtype=np.int16)
    return np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_the_same_view_counts_as_not_moved():
    shift = measure(prepare(noisy(SLOTS_SCENE, 1)), prepare(noisy(SLOTS_SCENE, 2)))
    assert shift is not None and shift.amount < 0.01


@pytest.mark.parametrize("dx, dy, angle", [(60, 0, 0), (-40, 35, 0), (30, 20, 2.5)])
def test_a_small_move_is_measured(dx, dy, angle):
    shift = measure(prepare(SLOTS_SCENE), prepare(moved(SLOTS_SCENE, dx, dy, angle)))
    assert shift is not None
    assert 0.01 < shift.amount < 0.2


def test_a_moved_area_follows_the_picture():
    reference, current = SLOTS_SCENE, moved(SLOTS_SCENE, 96, 54)
    shift = measure(prepare(reference), prepare(current))
    area = move_area(Roi(x=0.2, y=0.3, w=0.4, h=0.4), shift, (960, 540))
    assert (area.x, area.y, area.w, area.h) == pytest.approx((0.25, 0.35, 0.4, 0.4), abs=0.01)


def test_parts_and_a_hand_in_view_do_not_hide_a_move():
    busy = moved(scene([("red", 560, 560), ("blue", 960, 560), ("green", 1360, 560)]), 60, 30)
    cv2.circle(busy, (1500, 300), 160, (120, 160, 215), -1)
    shift = measure(prepare(SLOTS_SCENE), prepare(busy))
    assert shift is not None
    assert shift.amount == pytest.approx(np.hypot(60, 30) / 1920, abs=0.01)


def test_a_different_view_cannot_be_matched():
    other = np.random.default_rng(5).integers(0, 255, SLOTS_SCENE.shape, dtype=np.uint8)
    assert measure(prepare(SLOTS_SCENE), prepare(other)) is None


def test_a_blank_view_cannot_be_matched():
    blank = np.full(SLOTS_SCENE.shape, 128, np.uint8)
    assert measure(prepare(SLOTS_SCENE), prepare(blank)) is None


def test_an_area_pushed_out_of_the_picture_is_not_invented():
    shift = measure(prepare(SLOTS_SCENE), prepare(moved(SLOTS_SCENE, 150, 0)))
    assert move_area(Roi(x=0.9, y=0.3, w=0.1, h=0.4), shift, (960, 540)) is None


def calibrated_manager(tmp_path):
    """Camera 1 plays a scene, gets a work area and with it a reference picture."""
    import time

    from app.camera_manager import CameraManager
    from app.cameras.testsource import TestSource
    from app.settings_store import SettingsStore

    images = tmp_path / "scenes"
    images.mkdir()
    cv2.imwrite(str(images / "a_basis_top.png"), SLOTS_SCENE)
    cv2.imwrite(str(images / "b_verschoven_top.png"), moved(SLOTS_SCENE, 70, 40, 1.5))
    cv2.imwrite(str(images / "c_ander_beeld_top.png"), np.random.default_rng(5).integers(0, 255, SLOTS_SCENE.shape, dtype=np.uint8))
    source = TestSource(images)
    cams = CameraManager(SettingsStore(tmp_path / "s.json"), backend=source)
    cams.sync()

    def show(scene):
        source.select(scene)
        time.sleep(0.6)

    show("a_basis")
    cams.set_roi(1, Roi(x=0.2, y=0.3, w=0.4, h=0.4))
    return cams, show


def test_a_bumped_camera_takes_its_work_area_along(tmp_path):
    cams, show = calibrated_manager(tmp_path)
    try:
        assert cams.check_calibration(1)["state"] == "ok"
        show("b_verschoven")
        outcome = cams.check_calibration(1)
        assert (outcome["state"], outcome["moved"]) == ("corrected", True)
        roi = cams.status()[0]["roi"]
        assert roi["x"] == pytest.approx(0.2 + 70 / 1920, abs=0.015)
        # The same shift measured again is not a new movement.
        assert cams.check_calibration(1)["moved"] is False
        show("a_basis")
        assert cams.check_calibration(1)["state"] == "ok"
        assert cams.status()[0]["roi"]["x"] == pytest.approx(0.2, abs=0.005)
    finally:
        cams.stop()


def test_an_unrecognisable_view_keeps_the_area_and_warns(tmp_path):
    cams, show = calibrated_manager(tmp_path)
    try:
        show("c_ander_beeld")
        assert cams.check_calibration(1)["state"] == "lost"
        assert cams.status()[0]["roi"]["x"] == pytest.approx(0.2)
        assert cams.status()[0]["calibration"]["state"] == "lost"
    finally:
        cams.stop()


def test_without_a_reference_nothing_is_checked(tmp_path):
    from app.camera_manager import CameraManager
    from app.settings_store import SettingsStore

    cams = CameraManager(SettingsStore(tmp_path / "s.json"), backend=object())
    assert cams.check_calibration(1) is None
    assert cams.reference_jpeg(1) is None
