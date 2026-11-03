"""Runs the turn counter over a video with a known number of turns.

From backend/: .venv/bin/python ../spike/turn_check.py film.mp4 [x y w h]
x y w h are the counting area as fractions, for example 0.3 0.2 0.4 0.5. Prints when each turn is counted.
"""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path.cwd()))

from app.motion_counter import TurnCounter


def main(path: str, area: list[float]) -> None:
    clip = cv2.VideoCapture(path)
    fps = clip.get(cv2.CAP_PROP_FPS)
    # The app samples at about 15 FPS, so a 60 FPS phone clip must not be measured at full rate.
    step = max(1, round(fps / 15))
    counter = TurnCounter()
    total = index = 0
    while True:
        ok, frame = clip.read()
        if not ok:
            break
        index += 1
        if index % step:
            continue
        if area:
            height, width = frame.shape[:2]
            x, y, w, h = area
            frame = frame[round(y * height) : round((y + h) * height), round(x * width) : round((x + w) * width)]
        turns = counter.feed(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), index / fps)
        if turns:
            total += turns
            print(f"{index / fps:6.1f} s  +{turns}  totaal {total}")
    print(f"Geteld: {total} ({index} beelden, {fps:.0f} FPS, elke {step}e gebruikt)")


if __name__ == "__main__":
    main(sys.argv[1], [float(value) for value in sys.argv[2:6]])
