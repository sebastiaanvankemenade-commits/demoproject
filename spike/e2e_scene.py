"""Real model through the real pipeline: scene -> Ollama -> validation -> engine.

Run from backend/ with its venv: .venv/bin/python ../spike/e2e_scene.py ../spike/scenes
Uses generated scenes, so this proves the wiring, not recognition of real parts.
"""
import asyncio
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path.cwd()))

from app.inference_service import CameraFrame, InferenceService
from app.observation import InvalidObservation
from app.ollama_client import OllamaClient
from app.workflow_engine import WorkflowEngine
from app.workflow_models import Workflow, WorkflowStep

MODEL = "qwen3-vl:4b-instruct"
STEPS = [
    WorkflowStep(
        id="red",
        title="Rood blok",
        instruction="Place the red block inside the square marked A.",
        completion_criterion="A red block lies inside the outlined square labelled A.",
        requires_transition=True,
    )
]
SCRIPT = ["empty", "red_in_B", "red_in_A", "dark_red_in_A", "red_in_A", "red_in_A", "red_in_A"]


async def main(scenes: Path) -> None:
    client = OllamaClient()
    models = {model.name: model for model in await client.list_models()}
    model = models[MODEL]
    workflow = Workflow(id="e2e", name="E2E", steps=STEPS)
    engine = WorkflowEngine(workflow)
    engine.start()
    service = InferenceService(client)
    rng = np.random.default_rng()

    for sequence, scene in enumerate(SCRIPT, start=1):
        image = cv2.imread(str(scenes / f"{scene}_top.png"))
        image = np.clip(image + rng.normal(0, 2, image.shape), 0, 255).astype(np.uint8)
        frame = CameraFrame(1, sequence, image)
        try:
            obs = await service.observe(model, workflow, engine.active_step, [frame])
        except InvalidObservation as exc:
            print(f"{scene:15} invalid output, nothing counted: {exc}")
            continue
        events = engine.apply(obs)
        record = engine.records[0]
        print(f"{scene:15} {obs.status.value:11} -> {[e.type.value for e in events]} "
              f"state={record.state.value} count={record.confirmations} | {obs.evidence}")
    print("finished:", engine.finished, "method:", engine.records[0].method)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
