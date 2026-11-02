"""Open both cameras by serial and report measured FPS. Stores no images.

Run from backend/ with its venv: .venv/bin/python ../spike/camera_check.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from app.cameras.macos import MacCameraCapture, discover


def main() -> None:
    cameras = discover()
    for camera in cameras:
        print(camera.name, camera.key, camera.device_id, camera.usb_speed, [(m.width, m.height, m.fps) for m in camera.modes][:3])
    captures = {camera.key: MacCameraCapture(camera.device_id) for camera in cameras}
    for capture in captures.values():
        capture.start()
    time.sleep(10)
    for key, capture in captures.items():
        frame = capture.buffer.get()
        shape = None if frame is None else frame.image.shape
        luma = None if frame is None else round(float(frame.image.mean()), 1)
        print(key, "frames", 0 if frame is None else frame.sequence, "fps", round(capture.buffer.measured_fps(), 1), shape, "mean", luma)
        capture.stop()


if __name__ == "__main__":
    main()
