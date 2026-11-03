import numpy as np
import pytest

from app.cameras import opencv


class FakeVideoCapture:
    """Cameras 0 and 2 exist; every open is recorded."""

    opened: list = []

    def __init__(self, source, backend=None):
        self.source = source
        self.settings = {}
        FakeVideoCapture.opened.append(source)

    def isOpened(self):
        return self.source in (0, 2)

    def set(self, prop, value):
        self.settings[prop] = value

    def read(self):
        return True, np.zeros((1080, 1920, 3), np.uint8)

    def release(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    FakeVideoCapture.opened = []
    monkeypatch.setattr(opencv.cv2, "VideoCapture", FakeVideoCapture)
    monkeypatch.setattr(opencv, "BY_ID", opencv.Path("/bestaat/niet"))
    monkeypatch.setattr(opencv.sys, "platform", "win32")
    yield
    for capture in list(opencv._open.values()):
        capture.stop()


def test_windows_cameras_are_found_by_number(fake):
    assert [(c.key, c.device_id) for c in opencv.discover()] == [("camera-0", "0"), ("camera-2", "2")]


def test_an_open_camera_is_listed_without_opening_it_again(fake):
    capture = opencv.Capture("2")
    capture.start()
    FakeVideoCapture.opened = []
    assert [c.key for c in opencv.discover()] == ["camera-0", "camera-2"]
    assert 2 not in FakeVideoCapture.opened


def test_capture_asks_for_mjpeg_at_1080p_and_reports_what_it_got(fake):
    capture = opencv.Capture("0")
    capture.start()
    assert (capture.width, capture.height) == (1920, 1080)
    assert capture.buffer.get() is not None
    capture.stop()
    assert "0" not in opencv._open


def test_a_missing_camera_gives_a_clear_error(fake):
    with pytest.raises(opencv.CameraOpenError):
        opencv.Capture("1").start()


def test_linux_uses_stable_names_with_the_serial(monkeypatch, tmp_path):
    for name in ("usb-Elgato_Facecam_4K_A9T9D61510SY7V-video-index0", "usb-Elgato_Facecam_4K_A9T9D61510SY7V-video-index1"):
        (tmp_path / name).touch()
    monkeypatch.setattr(opencv, "BY_ID", tmp_path)
    monkeypatch.setattr(opencv.sys, "platform", "linux")
    cameras = opencv.discover()
    assert [c.key for c in cameras] == ["usb-Elgato_Facecam_4K_A9T9D61510SY7V"]
    assert cameras[0].device_id.endswith("-video-index0")
