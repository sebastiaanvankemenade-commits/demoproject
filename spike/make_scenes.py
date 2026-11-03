"""Generate synthetic 1080p test scenes for Workflow B (coloured parts on marked positions).

These are NOT camera images. They measure latency and schema behaviour, and give a
rough upper bound on recognition: real photos will be harder.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

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


def shifted(img: np.ndarray, dx: int, dy: int, angle: float) -> np.ndarray:
    """The same table seen by a camera that was bumped a little."""
    matrix = cv2.getRotationMatrix2D((W / 2, H / 2), angle, 1.0)
    matrix[:, 2] += (dx, dy)
    return cv2.warpAffine(img, matrix, (W, H), borderValue=(60, 60, 60))


def on_mat(blocks: list[str], top: list, side: list, seed: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """The printed work mat with blocks on it, lying on the table, seen by both cameras."""
    from app import workmat

    page = cv2.cvtColor(workmat.render(dpi=120), cv2.COLOR_GRAY2BGR)
    scale = page.shape[1] / workmat.MAT_W
    for colour, slot in blocks:
        x, y = (round(value * scale) for value in workmat.SLOTS_MM[slot])
        half = round(15 * scale)
        cv2.rectangle(page, (x - half, y - half), (x + half, y + half), COLOURS[colour], -1)
    height, width = page.shape[:2]
    corners = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    views = []
    for target in (top, side):
        matrix = cv2.getPerspectiveTransform(corners, np.float32(target))
        img = table(seed)
        warped = cv2.warpPerspective(page, matrix, (W, H))
        mask = cv2.warpPerspective(np.full((height, width), 255, np.uint8), matrix, (W, H)) > 0
        img[mask] = warped[mask]
        views.append(img)
    return views[0], views[1]


def main(out: Path) -> None:
    ax, ay = SLOTS["A"]
    bx, by = SLOTS["B"]
    cx, cy = SLOTS["C"]
    red, blue, green = ("red", ax, ay), ("blue", bx, by), ("green", cx, cy)
    scenes = {
        "1_leeg": scene([]),
        "2_rood_op_a": scene([red]),
        "3_blauw_verkeerd_op_c": scene([red, ("blue", cx, cy)]),
        "4_blauw_op_b": scene([red, blue]),
        "5_alles_geplaatst": scene([red, blue, green]),
        "empty": scene([]),
        "red_in_A": scene([("red", ax, ay)]),
        "red_in_B": scene([("red", bx, by)]),
        "red_beside_A": scene([("red", ax, ay + 260)]),
        "blue_in_A": scene([("blue", ax, ay)]),
        "dark_red_in_A": scene([("red", ax, ay)], gain=0.07),
    }
    out.mkdir(parents=True, exist_ok=True)
    # Two builds of the same setup: the cameras stand somewhere else the second time.
    first = ([[520, 260], [1400, 280], [1380, 900], [540, 880]], [[700, 520], [1250, 520], [1620, 930], [330, 930]])
    rebuilt = ([[300, 120], [1100, 180], [1060, 760], [280, 700]], [[820, 420], [1500, 440], [1760, 860], [640, 840]])
    for name, (top, side) in {"werkmat_opbouw_1": first, "werkmat_opbouw_2": rebuilt}.items():
        mat_top, mat_side = on_mat([("red", "A")], top, side)
        cv2.imwrite(str(out / f"{name}_top.png"), mat_top)
        cv2.imwrite(str(out / f"{name}_side.png"), mat_side)
    scenes["2_rood_op_a_camera_verschoven"] = shifted(scenes["2_rood_op_a"], 70, 40, 1.5)
    for name, img in scenes.items():
        cv2.imwrite(str(out / f"{name}_top.png"), img)
        cv2.imwrite(str(out / f"{name}_side.png"), side_view(img))
    print(f"wrote {len(scenes) * 2} images to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
