"""Generated clips of turning movements with a known count, seen from above.

Drawn shapes, not recordings: they test the counting logic, not real hands.
As a script it writes a clip that the test source can play:
python spike/turn_clip.py spike/scenes
"""
from pathlib import Path
import sys

import cv2
import numpy as np

W, H = 1280, 720
PIVOT = (640, 380)
SKIN = (120, 160, 215)


def table(seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), (150, 165, 175), np.uint8)
    img = np.clip(img.astype(np.int16) + rng.normal(0, 6, (H, W, 1)).astype(np.int16), 0, 255).astype(np.uint8)
    cv2.rectangle(img, (440, 230), (840, 530), (95, 100, 105), -1)
    cv2.circle(img, PIVOT, 26, (60, 60, 60), -1)
    return img


def draw_handle(img: np.ndarray, angle: float) -> None:
    """A screwdriver seen from above: a turning T-handle held by a hand."""
    dx, dy = np.cos(angle) * 95, np.sin(angle) * 95
    a = (round(PIVOT[0] - dx), round(PIVOT[1] - dy))
    b = (round(PIVOT[0] + dx), round(PIVOT[1] + dy))
    cv2.line(img, a, b, (40, 60, 190), 34, cv2.LINE_AA)
    cv2.circle(img, b, 42, SKIN, -1, cv2.LINE_AA)
    cv2.circle(img, a, 34, SKIN, -1, cv2.LINE_AA)


def draw_wrench(img: np.ndarray, angle: float) -> None:
    """A wrench on the screw: the hand swings around it on a long arm."""
    end = (round(PIVOT[0] + np.cos(angle) * 260), round(PIVOT[1] + np.sin(angle) * 260))
    cv2.line(img, PIVOT, end, (170, 170, 170), 26, cv2.LINE_AA)
    cv2.circle(img, end, 48, SKIN, -1, cv2.LINE_AA)


def turning(turns: int, tool=draw_handle, hz: float = 1.0, amplitude: float = 0.7, fps: int = 15, idle_s: float = 1.0):
    """Yields frames: rest, `turns` movements, rest."""
    base = table()
    rng = np.random.default_rng(1)
    rest = [0.0] * round(idle_s * fps)
    active = round(turns * fps / hz)
    angles = rest + [amplitude * np.sin(2 * np.pi * hz * i / fps) for i in range(active + 1)] + rest
    for angle in angles:
        img = base.copy()
        tool(img, angle)
        yield np.clip(img.astype(np.int16) + rng.integers(-3, 4, img.shape, dtype=np.int16), 0, 255).astype(np.uint8)


def passing(fps: int = 15):
    """A hand comes in, stays a moment and leaves: no turn at all."""
    base = table()
    path = list(np.linspace(1400, 700, fps)) + [700.0] * round(fps * 1.5) + list(np.linspace(700, 1400, fps))
    for x in path:
        img = base.copy()
        cv2.circle(img, (round(x), 380), 70, SKIN, -1, cv2.LINE_AA)
        yield img


def main(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    turns = 6
    frames = list(turning(turns))
    for view in ("top", "side"):
        writer = cv2.VideoWriter(str(folder / f"schroef_{turns}x_{view}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 15, (W, H))
        for frame in frames:
            writer.write(frame)
        writer.release()
    print(f"wrote clip with {turns} turns, {len(frames)} frames")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
