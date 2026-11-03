"""Which hardware the app runs on, and what that allows.

A profile sets starting values; the operator can still change each of them afterwards.
The model stays a free choice among the models that fit: a bigger model is not a better
one, so the profile never switches to one by itself.
"""
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

ProfileName = Literal["light", "power"]

POWER_MIN_VRAM_GB = 16
LIGHT_MODEL_LIMIT_GB = 12
VRAM_SHARE = 0.85  # The rest goes to context, images and the desktop.
UNIFIED_SHARE = 0.5  # On a Mac the model shares this memory with everything else.


@dataclass(frozen=True)
class Profile:
    image_width: int
    interval_s: float
    boxes_all_cameras: bool
    # Pictures per demonstrated step. Eight need a larger context, and on the Air the model
    # loaded that way pushed 22 GB into swap; four fit in the default 8192.
    strip_pictures: int


PROFILES: dict[ProfileName, Profile] = {
    "light": Profile(image_width=768, interval_s=3.0, boxes_all_cameras=False, strip_pictures=4),
    "power": Profile(image_width=1024, interval_s=1.0, boxes_all_cameras=True, strip_pictures=8),
}


class Device(BaseModel):
    name: str
    memory_gb: float | None = None
    # Largest model that should load fully; None means it could not be determined.
    model_budget_gb: float | None = None
    recommended: ProfileName = "light"


def parse_nvidia_smi(output: str) -> tuple[str, float] | None:
    """Takes `name, memory in MiB` per GPU and returns the one with the most memory."""
    gpus = []
    for line in output.strip().splitlines():
        name, _, memory = line.rpartition(",")
        try:
            gpus.append((name.strip(), float(memory) / 1024))
        except ValueError:
            continue
    return max(gpus, key=lambda gpu: gpu[1], default=None)


def _read(*command: str) -> str | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=5, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def _system_memory_gb() -> float | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (AttributeError, OSError, ValueError):
        return None  # Windows has no sysconf.


def describe_device(gpu: tuple[str, float] | None, chip: str | None, memory_gb: float | None) -> Device:
    if gpu:
        name, vram = gpu
        return Device(
            name=name,
            memory_gb=round(vram, 1),
            model_budget_gb=round(vram * VRAM_SHARE, 1),
            recommended="power" if vram >= POWER_MIN_VRAM_GB else "light",
        )
    return Device(
        name=chip or "Onbekend apparaat",
        memory_gb=round(memory_gb, 1) if memory_gb else None,
        model_budget_gb=round(memory_gb * UNIFIED_SHARE, 1) if memory_gb else None,
    )


def detect_device() -> Device:
    gpu = None
    if shutil.which("nvidia-smi"):
        output = _read("nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits")
        gpu = parse_nvidia_smi(output) if output else None
    chip = None
    if sys.platform == "darwin":
        chip = (_read("sysctl", "-n", "machdep.cpu.brand_string") or "").strip() or None
    return describe_device(gpu, chip, _system_memory_gb())


def model_limit_gb(device: Device, profile: ProfileName) -> float | None:
    """Light means small models, also when the hardware could carry more."""
    if profile == "power":
        return device.model_budget_gb
    if device.model_budget_gb is None:
        return LIGHT_MODEL_LIMIT_GB
    return min(device.model_budget_gb, LIGHT_MODEL_LIMIT_GB)
