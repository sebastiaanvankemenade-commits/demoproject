"""Generate synthetic 1080p test scenes for Workflow B (coloured parts on marked positions).

These are NOT camera images. They measure latency and schema behaviour, and give a
rough upper bound on recognition: real photos will be harder.
"""
from pathlib import Path
import sys

import cv2
import numpy as np

W, H = 1920, 1080
SLOTS = {"A": (560, 560), "B": (960, 560), "C": (1360, 560)}
COLOURS = {"red": (40, 40, 200), "blue": (190, 90, 30), "green": (60, 150, 50)}
SLOT_SIZE = 150
BLOCK_SIZE = 90


def table(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), (150, 165, 175), np.uint8)
    noise = rng.normal(0, 5, (H, W, 1)).astype(np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def draw_slots(img: np.ndarray) -> None:
    for name, (x, y) in SLOTS.items():
        half = SLOT_SIZE // 2
        cv2.rectangle(img, (x - half, y - half), (x + half, y + half), (30, 30, 30), 5)
        cv2.putText(img, name, (x - 22, y - half - 22), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (30, 30, 30), 5, cv2.LINE_AA)


def draw_block(img: np.ndarray, colour: str, x: int, y: int) -> None:
    half = BLOCK_SIZE // 2
    cv2.rectangle(img, (x - half + 8, y - half + 8), (x + half + 8, y + half + 8), (100, 110, 118), -1)
    cv2.rectangle(img, (x - half, y - half), (x + half, y + half), COLOURS[colour], -1)


def scene(blocks: list[tuple[str, int, int]], seed: int = 1, gain: float = 1.0) -> np.ndarray:
    img = table(seed)
    draw_slots(img)
    for colour, x, y in blocks:
        draw_block(img, colour, x, y)
    return np.clip(img.astype(np.float32) * gain, 0, 255).astype(np.uint8)


def side_view(img: np.ndarray) -> np.ndarray:
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = np.float32([[260, 260], [W - 260, 260], [W, H], [0, H]])
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (W, H), borderValue=(60, 60, 60))


def main(out: Path) -> None:
    ax, ay = SLOTS["A"]
    bx, by = SLOTS["B"]
    scenes = {
        "empty": scene([]),
        "red_in_A": scene([("red", ax, ay)]),
        "red_in_B": scene([("red", bx, by)]),
        "red_beside_A": scene([("red", ax, ay + 260)]),
        "blue_in_A": scene([("blue", ax, ay)]),
        "dark_red_in_A": scene([("red", ax, ay)], gain=0.07),
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, img in scenes.items():
        cv2.imwrite(str(out / f"{name}_top.png"), img)
        cv2.imwrite(str(out / f"{name}_side.png"), side_view(img))
    print(f"wrote {len(scenes) * 2} images to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
