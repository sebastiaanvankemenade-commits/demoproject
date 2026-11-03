"""Model output schema and validation.

The model only ever produces a ModelObservation. Step id, cameras and frame numbers are
attached by the application, so the model cannot claim evidence it was not given.
"""
import json
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ObservationStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    UNCERTAIN = "uncertain"


# Field order matters: the verdict comes last so the model states its evidence first.
# In the spike this took schema validity from 6/18 to 18/18 on qwen3-vl:4b-instruct.
OLLAMA_FORMAT = {
    "type": "object",
    "properties": {
        "visible_objects": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "observed_relationships": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "evidence": {"type": "string", "maxLength": 200},
        "status": {"type": "string", "enum": [s.value for s in ObservationStatus]},
    },
    "required": ["visible_objects", "observed_relationships", "evidence", "status"],
}


NO_DEVIATION = "none"


def ollama_format(deviations: list[str]) -> dict:
    """Steps without named deviations keep the measured schema exactly as it is."""
    if not deviations:
        return OLLAMA_FORMAT
    properties = {key: value for key, value in OLLAMA_FORMAT["properties"].items() if key != "status"}
    properties["deviation"] = {"type": "string", "enum": [NO_DEVIATION, *deviations]}
    properties["status"] = OLLAMA_FORMAT["properties"]["status"]
    return {"type": "object", "properties": properties, "required": list(properties)}


class ModelObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible_objects: list[str]
    observed_relationships: list[str]
    evidence: str = Field(min_length=1)
    deviation: str | None = None
    status: ObservationStatus

    @model_validator(mode="after")
    def completed_needs_visual_support(self) -> "ModelObservation":
        if self.status is ObservationStatus.COMPLETED and not self.visible_objects:
            raise ValueError("completed observation lists no visible objects")
        if self.status is ObservationStatus.COMPLETED and self.named_deviation:
            raise ValueError("completed observation also reports a deviation")
        return self

    @property
    def named_deviation(self) -> str | None:
        return None if self.deviation in (None, NO_DEVIATION) else self.deviation


# Separate from OLLAMA_FORMAT on purpose: boxes are for display, the verdict schema stays as measured.
DETECTION_FORMAT = {
    "type": "object",
    "properties": {
        "objects": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "maxLength": 40},
                    "box_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                },
                "required": ["label", "box_2d"],
            },
        }
    },
    "required": ["objects"],
}
MIN_BOX = 5  # of 1000; the model answers [0, 0, 0, 0] for an object it did not find
MAX_BOX_AREA = 0.9


class Detection(BaseModel):
    """A box as fractions of the image it was found in."""

    label: str
    x: float
    y: float
    w: float
    h: float


def parse_detections(raw: str, done_reason: str | None = None) -> list[Detection]:
    """Keeps only boxes that can be drawn. A bad answer means no boxes, never invented ones."""
    if done_reason == "length":
        return []
    try:
        objects = json.loads(raw)["objects"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    found = []
    for item in objects if isinstance(objects, list) else []:
        try:
            label, (left, top, right, bottom) = item["label"].strip(), item["box_2d"]
            inside = 0 <= left < right <= 1000 and 0 <= top < bottom <= 1000
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        width, height = right - left, bottom - top
        if label and inside and min(width, height) >= MIN_BOX and width * height <= MAX_BOX_AREA * 1e6:
            found.append(Detection(label=label, x=left / 1000, y=top / 1000, w=width / 1000, h=height / 1000))
    return found


# Verdict-last again: the model first lists what changed, then names the step.
STEP_DRAFT_FORMAT = {
    "type": "object",
    "properties": {
        "changes": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "expected_objects": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "completion_criterion": {"type": "string", "maxLength": 200},
        # Dutch field names: with English ones the model wrote English titles in 4 of 6 steps.
        "titel": {"type": "string", "maxLength": 60},
        "instructie": {"type": "string", "maxLength": 200},
    },
    "required": ["changes", "expected_objects", "completion_criterion", "titel", "instructie"],
}


class StepDraft(BaseModel):
    """A work step suggested from a demonstration. Always reviewed by a person before use."""

    model_config = ConfigDict(extra="forbid")

    changes: list[str]
    expected_objects: list[str]
    completion_criterion: str = Field(min_length=5)
    titel: str = Field(min_length=2)
    instructie: str = Field(min_length=5)


def parse_step_draft(raw: str, done_reason: str | None = None) -> StepDraft:
    if done_reason == "length":
        raise InvalidObservation("response was cut off at the output token limit")
    try:
        return StepDraft.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InvalidObservation(str(exc)) from exc


class InvalidObservation(Exception):
    """The model response cannot be used as evidence."""


def parse_model_response(
    raw: str, done_reason: str | None = None, allowed_deviations: tuple[str, ...] = ()
) -> ModelObservation:
    if done_reason == "length":
        raise InvalidObservation("response was cut off at the output token limit")
    try:
        parsed = ModelObservation.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InvalidObservation(str(exc)) from exc
    if parsed.named_deviation and parsed.named_deviation not in allowed_deviations:
        raise InvalidObservation(f"unknown deviation: {parsed.named_deviation}")
    return parsed


class Observation(BaseModel):
    """A validated observation plus the frames it was made from."""

    step_id: str
    status: ObservationStatus
    evidence: str
    visible_objects: list[str] = Field(default_factory=list)
    observed_relationships: list[str] = Field(default_factory=list)
    # camera number -> capture sequence number of the frame that was analysed
    frames: dict[int, int]
    model: str | None = None
    simulated: bool = False
    deviation: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
