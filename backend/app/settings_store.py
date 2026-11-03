"""Local preferences in a JSON file."""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from .device_profile import ProfileName
from .inference_service import InferenceSettings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Roi(BaseModel):
    """Work area as fractions of the full image, so it does not depend on the resolution."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0.05, le=1)
    h: float = Field(ge=0.05, le=1)

    @model_validator(mode="after")
    def stays_inside_the_image(self) -> "Roi":
        if self.x + self.w > 1.001 or self.y + self.h > 1.001:
            raise ValueError("work area extends outside the image")
        return self


class CountArea(BaseModel):
    """Where turning movements are counted: one area, because two views would count double."""

    key: str
    roi: Roi
    # The same area on the work mat, so it survives the setup being rebuilt.
    mat: Roi | None = None


class Calibration(BaseModel):
    """The areas as drawn on the reference picture. Corrections always start from these,
    so small errors never add up."""

    roi: Roi | None = None
    count_area: Roi | None = None
    saved_at: str


class Settings(BaseModel):
    model: str | None = None
    workflow_id: str | None = None
    camera_mode: Literal["both", "1", "2"] = "both"
    interval_s: float = Field(default=3.0, ge=1, le=10)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    # An extra model request per analysis; the verdict does not use it.
    show_boxes: bool = True
    boxes_all_cameras: bool = False
    device_profile: Literal["auto", "light", "power"] = "auto"
    # What the values above were last set from, so a profile is applied once per change.
    applied_profile: ProfileName | None = None
    camera_keys: dict[str, str] = Field(default_factory=dict)
    # Keyed by camera, so a work area follows the camera when the views are swapped.
    rois: dict[str, Roi] = Field(default_factory=dict)
    count_area: CountArea | None = None
    calibrations: dict[str, Calibration] = Field(default_factory=dict)
    auto_work_area: bool = True


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "settings.json"
        self.settings = self._load()

    def _load(self) -> Settings:
        try:
            return Settings.model_validate_json(self.path.read_text())
        except (OSError, ValidationError, json.JSONDecodeError):
            return Settings()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.settings.model_dump_json(indent=2))
