"""Local preferences in a JSON file."""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Settings(BaseModel):
    model: str | None = None
    workflow_id: str | None = None
    camera_mode: Literal["both", "1", "2"] = "both"
    interval_s: float = Field(default=3.0, ge=1, le=10)
    image_width: Literal[384, 512, 768, 1024] = 768
    camera_keys: dict[str, str] = Field(default_factory=dict)


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
