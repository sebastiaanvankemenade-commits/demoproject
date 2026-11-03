"""Measure false and missed deviations with the real model, old rule against new.

A part that is not placed yet must not count as a deviation, or an operator who is still
working gets a false alarm. Run from backend/: .venv/bin/python ../spike/deviation_check.py ../spike/scenes
"""
import asyncio
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path.cwd()))

import app.inference_service as service
from app.default_workflows import OBJECT_PLACEMENT
from app.observation import InvalidObservation
from app.ollama_client import OllamaClient

MODEL = "qwen3-vl:4b-instruct"
REPEATS = 5
OLD_RULE = (
    'Report one in the deviation field only if the image clearly shows it, otherwise use "none". '
    "A part that is simply not placed yet is not a deviation."
)
# (scene, step index, should a deviation be reported?)
CASES = [
    ("1_leeg", 0, False),
    ("2_rood_op_a", 1, False),
    ("4_blauw_op_b", 2, False),
    ("3_blauw_verkeerd_op_c", 1, True),
    ("red_in_B", 0, True),
    ("blue_in_A", 0, True),
]


def frames(scenes: Path, scene: str, sequence: int, rng) -> list[service.CameraFrame]:
    result = []
    for camera, view in ((1, "top"), (2, "side")):
        image = cv2.imread(str(scenes / f"{scene}_{view}.png"))
        noisy = np.clip(image + rng.normal(0, 2, image.shape), 0, 255).astype(np.uint8)
        result.append(service.CameraFrame(camera, sequence, noisy))
    return result


async def measure(label: str, scenes: Path, out) -> None:
    client = OllamaClient()
    model = {m.name: m for m in await client.list_models()}[MODEL]
    inference = service.InferenceService(client)
    rng = np.random.default_rng()
    sequence = 0
    for scene, index, expected in CASES:
        step = OBJECT_PLACEMENT.steps[index]
        hits = invalid = wrong_status = 0
        for _ in range(REPEATS):
            sequence += 1
            try:
                obs = await inference.observe(model, OBJECT_PLACEMENT, step, frames(scenes, scene, sequence, rng))
            except InvalidObservation:
                invalid += 1
                continue
            hits += obs.deviation is not None
            wrong_status += obs.status.value == "completed"
        row = {"rule": label, "scene": scene, "step": step.id, "expected": expected, "reported": hits, "n": REPEATS, "invalid": invalid, "completed": wrong_status}
        out.write(json.dumps(row) + "\n")
        out.flush()
        print(row, flush=True)
    await client.close()


async def main(scenes: Path) -> None:
    new_rule = service.DEVIATION_RULE
    with open("../spike/results/deviation.jsonl", "a") as out:
        service.DEVIATION_RULE = OLD_RULE
        await measure("oud", scenes, out)
        service.DEVIATION_RULE = new_rule
        await measure("nieuw", scenes, out)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
