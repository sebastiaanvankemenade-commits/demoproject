"""Workflow definitions. These are plain data, so imported files cannot carry code."""
from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1


SAFE_ID = r"^[a-z0-9][a-z0-9-]{0,63}$"


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=SAFE_ID)
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    completion_criterion: str = Field(min_length=1)
    expected_objects: list[str] = Field(default_factory=list)
    deviation_conditions: list[str] = Field(default_factory=list)
    required_confirmations: int | None = Field(default=None, ge=1, le=10)
    # Only count "completed" after this step was seen unfinished, so a state that was already
    # true when the step became active cannot pass as work that was done.
    requires_transition: bool = False
    # Turning movements to count during this step. Recorded with the step; does not block it.
    expected_turns: int | None = Field(default=None, ge=1, le=100)


class Workflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    # The id doubles as a file name, so it must not be able to leave the workflow folder.
    id: str = Field(pattern=SAFE_ID)
    name: str = Field(min_length=1)
    required_confirmations: int = Field(default=3, ge=1, le=10)
    steps: list[WorkflowStep] = Field(min_length=1)

    @model_validator(mode="after")
    def step_ids_are_unique(self) -> "Workflow":
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        return self
