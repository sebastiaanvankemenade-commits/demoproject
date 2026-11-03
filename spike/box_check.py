"""Can the model draw boxes? Compares its boxes with the known block positions in the scenes.

Generated scenes, so a good score is an upper bound, like the rest of the spike.
Run from backend/: .venv/bin/python ../spike/box_check.py ../spike/scenes
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd().parent / "spike"))

from app.inference_service import encode_frame
from app.ollama_client import OllamaClient
from make_scenes import BLOCK_SIZE, H, SLOTS, W

MODEL = "qwen3-vl:4b-instruct"
REPEATS = 2
IOU_HIT = 0.5
SCHEMA = {
    "type": "object",
    "properties": {
        "objects": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "box_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                },
                "required": ["label", "box_2d"],
            },
        }
    },
    "required": ["objects"],
}
BASE = (
    "Give the bounding box of each object as box_2d [x1, y1, x2, y2], with coordinates from 0 to 1000 "
    "relative to the image width and height. Box only what is really visible. "
    "If nothing is visible, return an empty list. Respond with JSON only."
)
PROMPTS = {
    "algemeen": "Find the separate physical objects lying on the work surface. Printed markings are not objects. " + BASE,
    "gericht": "Find these objects if they are visible: red block, blue block, green block. " + BASE,
}
A, B, C = SLOTS["A"], SLOTS["B"], SLOTS["C"]
SCENES = {
    "1_leeg": [],
    "2_rood_op_a": [A],
    "4_blauw_op_b": [A, B],
    "5_alles_geplaatst": [A, B, C],
    "red_beside_A": [(A[0], A[1] + 260)],
}


def truth_box(centre: tuple[int, int], view: str) -> tuple[float, float, float, float]:
    half = BLOCK_SIZE / 2
    corners = np.float32(
        [[centre[0] + dx * half, centre[1] + dy * half] for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    )
    if view == "side":
        src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
        dst = np.float32([[260, 260], [W - 260, 260], [W, H], [0, H]])
        corners = cv2.perspectiveTransform(corners[None], cv2.getPerspectiveTransform(src, dst))[0]
    return (
        corners[:, 0].min() / W * 1000,
        corners[:, 1].min() / H * 1000,
        corners[:, 0].max() / W * 1000,
        corners[:, 1].max() / H * 1000,
    )


def iou(a, b) -> float:
    width = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    overlap = width * height
    area = lambda box: max(0, box[2] - box[0]) * max(0, box[3] - box[1])
    union = area(a) + area(b) - overlap
    return overlap / union if union else 0.0


async def main(scenes: Path) -> None:
    client = OllamaClient()
    rng = np.random.default_rng()
    with open("../spike/results/boxes.jsonl", "a") as out:
        for prompt_name, prompt in PROMPTS.items():
            for scene, centres in SCENES.items():
                for view in ("top", "side"):
                    image = cv2.imread(str(scenes / f"{scene}_{view}.png"))
                    truth = [truth_box(centre, view) for centre in centres]
                    for attempt in range(REPEATS):
                        noisy = np.clip(image + rng.normal(0, 2, image.shape), 0, 255).astype(np.uint8)
                        body = {
                            "model": MODEL,
                            "format": SCHEMA,
                            "think": False,
                            "keep_alive": "10m",
                            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 300},
                            "messages": [{"role": "user", "content": prompt, "images": [encode_frame(noisy, 768)]}],
                        }
                        started = time.monotonic()
                        result = await client.chat(body, 120)
                        row = {"prompt": prompt_name, "scene": scene, "view": view, "try": attempt}
                        row["s"] = round(time.monotonic() - started, 1)
                        try:
                            objects = json.loads(result.content)["objects"]
                            boxes = [o["box_2d"] for o in objects]
                            scores = [max((iou(t, b) for b in boxes), default=0.0) for t in truth]
                            matched = sum(any(iou(t, b) >= IOU_HIT for t in truth) for b in boxes)
                            row |= {
                                "truth": len(truth),
                                "hits": int(sum(score >= IOU_HIT for score in scores)),
                                "extra": int(len(boxes) - matched),
                                "iou": [round(float(score), 2) for score in scores],
                                "objects": objects,
                            }
                        except (json.JSONDecodeError, KeyError, TypeError) as exc:
                            row |= {"invalid": str(exc), "done": result.done_reason, "raw": result.content[:300]}
                        out.write(json.dumps(row) + "\n")
                        out.flush()
                        print(row, flush=True)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
