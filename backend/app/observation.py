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


class ModelObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible_objects: list[str]
    observed_relationships: list[str]
    evidence: str = Field(min_length=1)
    status: ObservationStatus

    @model_validator(mode="after")
    def completed_needs_visual_support(self) -> "ModelObservation":
        if self.status is ObservationStatus.COMPLETED and not self.visible_objects:
            raise ValueError("completed observation lists no visible objects")
        return self


class InvalidObservation(Exception):
    """The model response cannot be used as evidence."""


def parse_model_response(raw: str, done_reason: str | None = None) -> ModelObservation:
    if done_reason == "length":
        raise InvalidObservation("response was cut off at the output token limit")
    try:
        return ModelObservation.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InvalidObservation(str(exc)) from exc


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
