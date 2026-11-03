"""Turns camera frames into validated observations. Never touches workflow state."""
import base64
import time
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, Field

from .frame_quality import FrameIssue, assess_frame
from .observation import (
    DETECTION_FORMAT,
    OLLAMA_FORMAT,
    STEP_DRAFT_FORMAT,
    Detection,
    InvalidObservation,
    StepDraft,
    Observation,
    ObservationStatus,
    ollama_format,
    parse_detections,
    parse_step_draft,
    parse_model_response,
)
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

DEVIATION_RULE = (
    "Report one in the deviation field only if the part it names is itself visible in the image. "
    'If the required part cannot be seen anywhere, it is simply not placed yet: use "none".'
)

DETECTION_RULE = (
    "Give the bounding box of each object as box_2d [x1, y1, x2, y2], with coordinates from 0 to 1000 "
    "relative to the image width and height. Box only what is really visible. "
    "If nothing is visible, return an empty list. Write each label in Dutch. Respond with JSON only."
)

POSITION_WORDS = ("position", "positie")
TOKENS_PER_IMAGE = 1200  # measured ±1000 per picture; the rest is margin for the text

FILMSTRIP_PROMPT = (
    "These {count} images are frames from one camera, in time order and about {gap} seconds apart, "
    "while an operator performed one work step on a work mat. The first shows the situation before the step, "
    "the last the situation after it. Printed squares, letters and black corner markers belong to the mat; "
    "they are not parts. In changes, describe in order what the hands did: which part was picked up, "
    "joined, screwed together, placed or removed. Then name the parts involved and write a completion criterion: "
    "one English sentence about the last image only, stating what must be visible when the step is done, "
    "for example which part is attached to which. Do not mention hands in the criterion. "
    "Then a short titel and an instructie for the operator, both in Dutch (Nederlands). "
    "Keep the parts and the criterion in English. Respond with JSON only."
)

DESCRIBE_PROMPT = (
    "Two images of the same work area: the first before an operator performed one work step, the second after it. "
    "Printed squares, letters and black corner markers belong to the work mat; they are not parts. "
    "Compare the parts: which were joined, attached, screwed together, removed, turned over or moved. "
    "List the visible changes. Then name the parts involved and write a completion criterion: one English sentence "
    "that states only what must be visible when the step is done, for example which part is attached to which. "
    "Do not mention hands or the act itself, and nothing that cannot be seen. "
    "Then a short titel and an instructie for the operator, both in Dutch (Nederlands). "
    "Keep the parts and the criterion in English. Respond with JSON only."
)

ISSUE_TEXT = {
    FrameIssue.TOO_DARK: "Beeld te donker om te beoordelen.",
    FrameIssue.TOO_BRIGHT: "Beeld overbelicht, niet te beoordelen.",
    FrameIssue.NO_DETAIL: "Beeld bevat te weinig detail om te beoordelen.",
}


class InferenceSettings(BaseModel):
    image_width: Literal[384, 512, 768, 1024] = 768
    temperature: float = Field(default=0.0, ge=0, le=1)
    num_ctx: int = Field(default=8192, ge=2048, le=32768)
    # Valid answers in the spike needed well under 300 tokens; longer ones were runaway output.
    num_predict: int = Field(default=300, ge=50, le=1000)
    timeout_s: float = Field(default=120.0, ge=10, le=300)
    keep_alive: str = Field(default="10m", pattern=r"^\d+[smh]$")


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
    if step.deviation_conditions:
        known = ", ".join(step.deviation_conditions)
        objects += f"\nKnown deviations: {known}. {DEVIATION_RULE}"
    body = {
        "model": model.name,
        "format": ollama_format(step.deviation_conditions),
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

    async def verify_model(self, model: ModelInfo) -> None:
        """Run one real image request. Raises OllamaUnavailable if the model cannot do it."""
        image = np.random.default_rng(0).integers(0, 255, (64, 64, 3), dtype=np.uint8)
        body = {
            "model": model.name,
            "keep_alive": self.settings.keep_alive,
            "options": {"temperature": 0, "num_predict": 5},
            "messages": [{"role": "user", "content": "What do you see?", "images": [encode_frame(image, 64)]}],
        }
        if model.thinking:
            body["think"] = False
        await self.client.chat(body, self.settings.timeout_s)

    async def ask(self, model: ModelInfo, frames: list[CameraFrame], question: str, structured: bool) -> dict:
        """Free question for the playground. Touches no workflow state."""
        images = [encode_frame(frame.image, self.settings.image_width) for frame in frames]
        body = {
            "model": model.name,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "temperature": self.settings.temperature,
                "num_ctx": self.settings.num_ctx,
                "num_predict": self.settings.num_predict,
            },
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT if structured else "Answer in Dutch. Describe only what is visible."},
                {"role": "user", "content": question, "images": images},
            ],
        }
        if structured:
            body["format"] = OLLAMA_FORMAT
        if model.thinking:
            body["think"] = False
        started = time.monotonic()
        result = await self.client.chat(body, self.settings.timeout_s)
        valid = None
        if structured:
            try:
                parse_model_response(result.content, result.done_reason)
                valid = True
            except InvalidObservation:
                valid = False
        return {
            "model": model.name,
            "response": result.content,
            "duration_s": round(time.monotonic() - started, 1),
            "valid": valid,
            "truncated": result.done_reason == "length",
        }

    async def detect(self, model: ModelInfo, step: WorkflowStep, frame: CameraFrame) -> list[Detection]:
        """Boxes for display only. In the spike, naming the objects kept empty scenes empty."""
        # Asking for marked positions too put boxes on empty spots: 2 of 12 against 0 of 12 without.
        objects = [name for name in step.expected_objects if not name.lower().startswith(POSITION_WORDS)]
        if objects:
            task = f"Find these objects if they are visible: {', '.join(objects)}. "
        else:
            task = "Find the separate physical objects on the work surface. Printed markings are not objects. "
        body = {
            "model": model.name,
            "format": DETECTION_FORMAT,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "temperature": self.settings.temperature,
                "num_ctx": self.settings.num_ctx,
                "num_predict": self.settings.num_predict,
            },
            "messages": [
                {
                    "role": "user",
                    "content": task + DETECTION_RULE,
                    "images": [encode_frame(frame.image, self.settings.image_width)],
                }
            ],
        }
        if model.thinking:
            body["think"] = False
        result = await self.client.chat(body, self.settings.timeout_s)
        return parse_detections(result.content, result.done_reason)

    async def describe_step(
        self,
        model: ModelInfo,
        frames: list[CameraFrame],
        note: str | None = None,
        parts: list[str] | None = None,
        gap_s: float = 0.5,
    ) -> StepDraft:
        """Suggests a work step from a filmstrip, or from a before and after picture.
        Raises InvalidObservation or OllamaUnavailable.

        The operator's own words lead: pictures of small parts say less than the person who did it.
        """
        if len(frames) > 2:
            content = FILMSTRIP_PROMPT.format(count=len(frames), gap=f"{gap_s:.1f}")
        else:
            content = DESCRIBE_PROMPT
        if parts:
            content += f"\nThe parts are called: {', '.join(parts)}. Use exactly these names."
        if note:
            content += f"\nThe operator described this step as: \"{note}\". Base the titel and instructie on that."
        body = {
            "model": model.name,
            "format": STEP_DRAFT_FORMAT,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "temperature": self.settings.temperature,
                # Eight pictures do not fit in the 8192 that two need.
                "num_ctx": max(self.settings.num_ctx, TOKENS_PER_IMAGE * len(frames) + 2048),
                "num_predict": self.settings.num_predict,
            },
            "messages": [
                {
                    "role": "user",
                    "content": content,
                    "images": [encode_frame(frame.image, self.settings.image_width) for frame in frames],
                }
            ],
        }
        if model.thinking:
            body["think"] = False
        result = await self.client.chat(body, self.settings.timeout_s)
        return parse_step_draft(result.content, result.done_reason)

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
        parsed = parse_model_response(result.content, result.done_reason, tuple(step.deviation_conditions))
        return Observation(
            step_id=step.id,
            status=parsed.status,
            evidence=parsed.evidence,
            visible_objects=parsed.visible_objects,
            observed_relationships=parsed.observed_relationships,
            frames=sequences,
            model=model.name,
            # An unclear image cannot support a deviation.
            deviation=parsed.named_deviation if parsed.status is ObservationStatus.INCOMPLETE else None,
        )
