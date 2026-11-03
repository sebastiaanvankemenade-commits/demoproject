"""Measures boxes the way the app asks for them: per step, through InferenceService.detect.

A box counts as right if its centre lies on the block of the colour it names. Generated scenes.
Run from backend/: .venv/bin/python ../spike/box_step_check.py ../spike/scenes
"""
import asyncio
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd().parent / "spike"))

import app.inference_service as service
from app.default_workflows import OBJECT_PLACEMENT
from app.ollama_client import OllamaClient
from box_check import truth_box
from make_scenes import BLOCK_SIZE, SLOT_SIZE, SLOTS

MODEL = "qwen3-vl:4b-instruct"
REPEATS = 2
A, B, C = SLOTS["A"], SLOTS["B"], SLOTS["C"]
SCENES = {
    "1_leeg": {},
    "2_rood_op_a": {"red": A},
    "red_in_B": {"red": B},
    "4_blauw_op_b": {"red": A, "blue": B},
    "5_alles_geplaatst": {"red": A, "blue": B, "green": C},
}
CASES = [
    ("place-red", "1_leeg", "red"),
    ("place-red", "2_rood_op_a", "red"),
    ("place-red", "red_in_B", "red"),
    ("place-blue", "2_rood_op_a", "blue"),
    ("place-blue", "4_blauw_op_b", "blue"),
    ("place-green", "4_blauw_op_b", "green"),
    ("place-green", "5_alles_geplaatst", "green"),
]
COLOUR_WORDS = {"red": ("rood", "rode", "red"), "blue": ("blauw", "blue"), "green": ("groen", "green")}
DUTCH = service.DETECTION_RULE
ENGLISH = DUTCH.replace(" Write each label in Dutch.", "")
VARIANTS = {"huidig": (False, DUTCH), "zonder-positie": (True, DUTCH), "zonder-positie-engels": (True, ENGLISH)}


def colour_of(label: str) -> str | None:
    lowered = label.lower()
    return next((colour for colour, words in COLOUR_WORDS.items() if any(word in lowered for word in words)), None)


def on_block(box, centre, view: str) -> bool:
    x, y = (box.x + box.w / 2) * 1000, (box.y + box.h / 2) * 1000
    left, top, right, bottom = truth_box(centre, view)
    # The model often boxes the printed square around the block, which is still the right place.
    margin = (SLOT_SIZE - BLOCK_SIZE) / BLOCK_SIZE / 2
    dx, dy = (right - left) * margin, (bottom - top) * margin
    return left - dx <= x <= right + dx and top - dy <= y <= bottom + dy


async def main(scenes: Path) -> None:
    client = OllamaClient()
    model = {m.name: m for m in await client.list_models()}[MODEL]
    inference = service.InferenceService(client)
    steps = {step.id: step for step in OBJECT_PLACEMENT.steps}
    rng = np.random.default_rng()
    sequence = 0
    with open("../spike/results/boxes_steps.jsonl", "a") as out:
        for name, (drop_positions, rule) in VARIANTS.items():
            service.DETECTION_RULE = rule
            for step_id, scene, wanted in CASES:
                step = steps[step_id]
                if drop_positions:
                    objects = [o for o in step.expected_objects if not o.startswith("position")]
                    step = step.model_copy(update={"expected_objects": objects})
                blocks = SCENES[scene]
                for view in ("top", "side"):
                    image = cv2.imread(str(scenes / f"{scene}_{view}.png"))
                    for _ in range(REPEATS):
                        sequence += 1
                        noisy = np.clip(image + rng.normal(0, 2, image.shape), 0, 255).astype(np.uint8)
                        found = await inference.detect(model, step, service.CameraFrame(1, sequence, noisy))
                        right = wrong = neutral = 0
                        for box in found:
                            colour = colour_of(box.label)
                            if colour is None:
                                neutral += 1
                            elif colour in blocks and on_block(box, blocks[colour], view):
                                right += 1
                            else:
                                wrong += 1
                        row = {
                            "variant": name, "step": step_id, "scene": scene, "view": view, "wanted": wanted,
                            "present": wanted in blocks, "right": right, "wrong": wrong, "neutral": neutral,
                            "labels": [box.label for box in found],
                        }
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        out.flush()
                        print(row, flush=True)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
