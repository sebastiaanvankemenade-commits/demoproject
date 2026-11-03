"""Does demonstrating Workflow B give steps the model can then judge correctly?

Generates the steps from before/after scenes, then checks each generated criterion on the
scene before the step (should not be completed) and after it (should be).
Run from backend/: .venv/bin/python ../spike/demo_check.py ../spike/scenes [met-notities]
"""
import asyncio
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path.cwd()))

from app.inference_service import CameraFrame, InferenceService
from app.observation import InvalidObservation
from app.ollama_client import OllamaClient
from app.workflow_models import Workflow, WorkflowStep

MODEL = "qwen3-vl:4b-instruct"
STATES = ["1_leeg", "2_rood_op_a", "4_blauw_op_b", "5_alles_geplaatst"]
NOTES = ["rood blok op A", "blauw blok op B", "groen blok op C"]
REPEATS = 2


async def main(scenes: Path, with_notes: bool) -> None:
    client = OllamaClient()
    model = {m.name: m for m in await client.list_models()}[MODEL]
    inference = InferenceService(client)
    rng = np.random.default_rng()
    sequence = 0

    def frame(scene: str) -> CameraFrame:
        nonlocal sequence
        sequence += 1
        image = cv2.imread(str(scenes / f"{scene}_top.png"))
        return CameraFrame(1, sequence, np.clip(image + rng.normal(0, 2, image.shape), 0, 255).astype(np.uint8))

    with open("../spike/results/demo.jsonl", "a") as out:
        for attempt in range(REPEATS):
            steps = []
            for index, (before, after) in enumerate(zip(STATES, STATES[1:])):
                note = NOTES[index] if with_notes else None
                try:
                    draft = await inference.describe_step(model, [frame(before), frame(after)], note)
                except InvalidObservation as exc:
                    print("ongeldig", exc, flush=True)
                    continue
                steps.append((before, after, draft))
            workflow = Workflow(
                id="demo",
                name="demo",
                steps=[
                    WorkflowStep(
                        id=f"stap-{i}",
                        title=d.titel,
                        instruction=d.instructie,
                        completion_criterion=d.completion_criterion,
                        expected_objects=d.expected_objects,
                    )
                    for i, (_, _, d) in enumerate(steps, start=1)
                ],
            )
            for (before, after, draft), step in zip(steps, workflow.steps):
                verdicts = {}
                for label, scene in (("voor", before), ("na", after)):
                    try:
                        verdicts[label] = (await inference.observe(model, workflow, step, [frame(scene)])).status.value
                    except InvalidObservation:
                        verdicts[label] = "ongeldig"
                row = {"notes": with_notes, "try": attempt, "after": after, **draft.model_dump(), "verdicts": verdicts}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                print(row, flush=True)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), len(sys.argv) > 2))
