"""Turns camera frames into validated observations. Never touches workflow state."""
import base64
from dataclasses import dataclass

import cv2
import numpy as np
from pydantic import BaseModel

from .frame_quality import FrameIssue, assess_frame
from .observation import OLLAMA_FORMAT, Observation, ObservationStatus, parse_model_response
from .ollama_client import ModelInfo, OllamaClient
from .workflow_models import Workflow, WorkflowStep

SYSTEM_PROMPT = (
    "You inspect camera images of a work area. Describe only what is visually observable. "
    "Do not guess about hidden objects and do not claim mechanical properties such as tightness. "
    "Keep every list item under 8 words and evidence to one short sentence. "
    "Then choose status: "
    '"completed" = the image clearly shows the criterion is met. '
    '"incomplete" = the image is clear and shows the criterion is not met, for example a part is absent, '
    "in another position, or the wrong part. "
    '"uncertain" = the image is too dark, blocked or unclear to judge. '
    "A clear image of an unmet criterion is incomplete, not uncertain. "
    "Write all text values in Dutch, but keep the status value in English. Respond with JSON only."
)

ISSUE_TEXT = {
    FrameIssue.TOO_DARK: "Beeld te donker om te beoordelen.",
    FrameIssue.TOO_BRIGHT: "Beeld overbelicht, niet te beoordelen.",
    FrameIssue.NO_DETAIL: "Beeld bevat te weinig detail om te beoordelen.",
}


class InferenceSettings(BaseModel):
    image_width: int = 768
    temperature: float = 0.0
    num_ctx: int = 8192
    # Valid answers in the spike needed well under 300 tokens; longer ones were runaway output.
    num_predict: int = 300
    timeout_s: float = 120.0
    keep_alive: str = "10m"


@dataclass(frozen=True)
class CameraFrame:
    camera: int
    sequence: int
    image: np.ndarray


def encode_frame(image: np.ndarray, width: int) -> str:
    height, current = image.shape[:2]
    if current > width:
        image = cv2.resize(image, (width, round(height * width / current)), interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("frame could not be encoded")
    return base64.b64encode(buffer).decode()


def build_request(
    model: ModelInfo, workflow: Workflow, step: WorkflowStep, images: list[str], settings: InferenceSettings
) -> dict:
    objects = f"\nExpected objects: {', '.join(step.expected_objects)}" if step.expected_objects else ""
    body = {
        "model": model.name,
        "format": OLLAMA_FORMAT,
        "keep_alive": settings.keep_alive,
        "options": {
            "temperature": settings.temperature,
            "num_ctx": settings.num_ctx,
            "num_predict": settings.num_predict,
        },
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Work instruction: {workflow.name}\nCurrent step: {step.instruction}\n"
                f"Completion criterion: {step.completion_criterion}{objects}\n"
                "Is the criterion satisfied in the image(s)?",
                "images": images,
            },
        ],
    }
    if model.thinking:
        body["think"] = False
    return body


class InferenceService:
    def __init__(self, client: OllamaClient, settings: InferenceSettings | None = None):
        self.client = client
        self.settings = settings or InferenceSettings()

    async def observe(
        self, model: ModelInfo, workflow: Workflow, step: WorkflowStep, frames: list[CameraFrame]
    ) -> Observation:
        """Raises OllamaUnavailable or InvalidObservation; callers must not treat those as evidence."""
        sequences = {frame.camera: frame.sequence for frame in frames}
        for frame in frames:
            issue = assess_frame(frame.image)
            if issue:
                return Observation(
                    step_id=step.id,
                    status=ObservationStatus.UNCERTAIN,
                    evidence=ISSUE_TEXT[issue],
                    frames=sequences,
                )

        images = [encode_frame(frame.image, self.settings.image_width) for frame in frames]
        body = build_request(model, workflow, step, images, self.settings)
        result = await self.client.chat(body, self.settings.timeout_s)
        parsed = parse_model_response(result.content, result.done_reason)
        return Observation(
            step_id=step.id,
            status=parsed.status,
            evidence=parsed.evidence,
            visible_objects=parsed.visible_objects,
            observed_relationships=parsed.observed_relationships,
            frames=sequences,
            model=model.name,
        )
