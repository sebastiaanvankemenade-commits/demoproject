"""A generated demonstration: a hand places a red, blue and green block on A, B and C.

Drawn shapes, not a recording. Tests the step detection and the filmstrip, not real hands.
python spike/demo_clip.py spike/scenes
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from make_scenes import BLOCK_SIZE, COLOURS, SLOTS, side_view, scene

FPS = 15
SKIN = (120, 160, 215)
PICKUP = {"red": (200, 950), "blue": (960, 990), "green": (1720, 950)}
ORDER = [("red", "A"), ("blue", "B"), ("green", "C")]
STILL_S, MOVE_S, PAUSE_S = 2.0, 3.0, 4.0


def draw_hand(img: np.ndarray, x: float, y: float, holding: str | None) -> None:
    if holding:
        half = BLOCK_SIZE // 2
        cv2.rectangle(img, (round(x) - half, round(y) - half), (round(x) + half, round(y) + half), COLOURS[holding], -1)
    cv2.ellipse(img, (round(x) + 40, round(y) + 70), (70, 95), 20, 0, 360, SKIN, -1, cv2.LINE_AA)


def frames():
    placed: list[tuple[str, int, int]] = []
    yield from [scene(placed)] * round(STILL_S * FPS)
    for colour, slot in ORDER:
        start, target = np.array(PICKUP[colour], float), np.array(SLOTS[slot], float)
        moves = round(MOVE_S * FPS)
        for index in range(moves):
            share = index / (moves - 1)
            if share < 0.25:  # hand comes in empty
                position, holding = start + (start - start) * 0, None
                position = np.array([start[0], 1150 - (1150 - start[1]) * share / 0.25])
            elif share < 0.8:  # carries the block
                position, holding = start + (target - start) * (share - 0.25) / 0.55, colour
            else:  # leaves
                position, holding = target + np.array([0, 500]) * (share - 0.8) / 0.2, None
            img = scene(placed + ([(colour, *map(int, target))] if share >= 0.8 else []))
            draw_hand(img, *position, holding)
            yield img
        placed.append((colour, int(target[0]), int(target[1])))
        yield from [scene(placed)] * round(PAUSE_S * FPS)


def main(folder: Path) -> None:
    pictures = list(frames())
    for view, change in (("top", lambda img: img), ("side", side_view)):
        # Half size: the test source holds every frame of a clip in memory.
        writer = cv2.VideoWriter(str(folder / f"voordoen_blokken_{view}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (960, 540))
        for img in pictures:
            writer.write(cv2.resize(change(img), (960, 540), interpolation=cv2.INTER_AREA))
        writer.release()
    print(f"wrote demonstration clip, {len(pictures) / FPS:.0f} s")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
