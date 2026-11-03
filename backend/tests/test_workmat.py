import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "spike"))

from app import workmat
from app.settings_store import Roi

W, H = 1920, 1080


def lay_down(page: np.ndarray, corners, cover: int | None = None) -> np.ndarray:
    """The mat on a table, seen at an angle; optionally a hand over one marker."""
    height, width = page.shape[:2]
    matrix = cv2.getPerspectiveTransform(np.float32([[0, 0], [width, 0], [width, height], [0, height]]), np.float32(corners))
    image = np.full((H, W, 3), (150, 165, 175), np.uint8)
    warped = cv2.warpPerspective(cv2.cvtColor(page, cv2.COLOR_GRAY2BGR), matrix, (W, H))
    mask = cv2.warpPerspective(np.full((height, width), 255, np.uint8), matrix, (W, H)) > 0
    image[mask] = warped[mask]
    if cover is not None:
        x, y = (round(v) for v in corners[cover])
        cv2.circle(image, (x, y), 110, (120, 160, 215), -1)
    return image


PAGE = workmat.render(dpi=120)
TOP = [[520, 260], [1400, 280], [1380, 900], [540, 880]]
SIDE = [[700, 520], [1250, 520], [1620, 930], [330, 930]]
REBUILT = [[300, 120], [1100, 180], [1060, 760], [280, 700]]


@pytest.mark.parametrize("corners", [TOP, SIDE, REBUILT])
def test_the_mat_is_found_from_any_angle(corners):
    view = workmat.locate(lay_down(PAGE, corners))
    assert view is not None and view.markers == 4
    area = workmat.mat_area(view, (W, H))
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    # The work area hugs the page, with a small margin, wherever the camera stands.
    assert area.x == pytest.approx(min(xs) / W, abs=0.04)
    assert area.x + area.w == pytest.approx(max(xs) / W, abs=0.04)
    assert area.y == pytest.approx(min(ys) / H, abs=0.05)


def test_a_hand_over_one_marker_does_not_lose_the_mat():
    view = workmat.locate(lay_down(PAGE, TOP, cover=0))
    assert view is not None and view.markers == 3


def test_two_covered_markers_are_not_enough():
    image = lay_down(PAGE, TOP, cover=0)
    x, y = TOP[1]
    cv2.circle(image, (x, y), 110, (120, 160, 215), -1)
    assert workmat.locate(image) is None


def test_no_mat_no_area():
    assert workmat.locate(np.full((H, W, 3), 150, np.uint8)) is None


def test_an_area_on_the_mat_lands_on_the_same_spot_after_a_rebuild():
    before, after = workmat.locate(lay_down(PAGE, TOP)), workmat.locate(lay_down(PAGE, REBUILT))
    drawn = Roi(x=0.4, y=0.4, w=0.1, h=0.1)
    on_mat = workmat.to_mat(before, drawn, (W, H))
    moved = workmat.to_image(after, on_mat, (W, H))
    # Same spot on the mat: map the centre of slot B in both builds and compare.
    centre = np.float32([[[on_mat.x + on_mat.w / 2, on_mat.y + on_mat.h / 2]]])
    expected = cv2.perspectiveTransform(centre, after.homography)[0][0]
    assert moved.x + moved.w / 2 == pytest.approx(expected[0] / W, abs=0.01)
    assert moved.y + moved.h / 2 == pytest.approx(expected[1] / H, abs=0.01)
    assert abs(moved.x - drawn.x) > 0.05  # the setup really moved


def test_the_printed_page_carries_all_four_markers():
    view = workmat.locate(cv2.cvtColor(PAGE, cv2.COLOR_GRAY2BGR))
    assert view is not None and view.markers == 4


def mat_manager(tmp_path):
    from app.camera_manager import CameraManager
    from app.cameras.testsource import TestSource
    from app.settings_store import SettingsStore

    scenes = tmp_path / "scenes"
    scenes.mkdir()
    cv2.imwrite(str(scenes / "a_top.png"), lay_down(PAGE, TOP))
    cv2.imwrite(str(scenes / "b_top.png"), lay_down(PAGE, REBUILT))
    cv2.imwrite(str(scenes / "c_top.png"), np.full((H, W, 3), 150, np.uint8))
    source = TestSource(scenes)
    cams = CameraManager(SettingsStore(tmp_path / "s.json"), backend=source)
    cams.sync()

    def show(scene):
        source.select(scene)
        time.sleep(0.6)

    show("a")
    return cams, show


def test_a_rebuilt_setup_gets_its_areas_back_without_drawing(tmp_path):
    cams, show = mat_manager(tmp_path)
    try:
        assert cams.check_workmat(1) == {"found": True, "changed": True, "moved": True}
        first = cams.status()[0]["roi"]
        cams.set_count_area(1, Roi(x=0.45, y=0.45, w=0.1, h=0.1))
        assert cams.store.settings.count_area.mat is not None

        show("b")
        outcome = cams.check_workmat(1)
        assert outcome["found"] and outcome["moved"]
        status = cams.status()[0]
        assert abs(status["roi"]["x"] - first["x"]) > 0.05
        assert status["count_area"]["x"] < 0.4  # the counting area followed the mat
        assert cams.check_workmat(1)["moved"] is False  # nothing new on a second look
    finally:
        cams.stop()


def test_a_briefly_hidden_mat_keeps_its_area(tmp_path):
    cams, show = mat_manager(tmp_path)
    try:
        cams.check_workmat(1)
        roi = cams.status()[0]["roi"]
        show("c")
        assert cams.check_workmat(1)["found"] is True
        assert cams.check_workmat(1)["found"] is True
        outcome = cams.check_workmat(1)
        assert (outcome["found"], outcome["changed"]) == (False, True)
        assert cams.status()[0]["roi"] == roi
    finally:
        cams.stop()


def test_switching_the_mat_off_leaves_the_areas_to_the_operator(tmp_path):
    cams, _ = mat_manager(tmp_path)
    try:
        cams.store.settings.auto_work_area = False
        assert cams.check_workmat(1) is None
        assert cams.status()[0]["workmat"] is None
    finally:
        cams.stop()


def test_jitter_in_finding_the_mat_does_not_move_the_area(tmp_path):
    cams, show = mat_manager(tmp_path)
    try:
        cams.check_workmat(1)
        before = cams.status()[0]["roi"]
        jittered = [[x + 6, y - 4] for x, y in TOP]  # a few pixels, as between two real frames
        cv2.imwrite(str(tmp_path / "scenes" / "d_top.png"), lay_down(PAGE, jittered))
        show("d")
        assert cams.check_workmat(1)["moved"] is False
        assert cams.status()[0]["roi"] == before
    finally:
        cams.stop()
