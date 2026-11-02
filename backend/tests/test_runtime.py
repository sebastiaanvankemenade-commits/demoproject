import asyncio
import json
from pathlib import Path

import httpx
import numpy as np

from app.camera_manager import CameraManager
from app.event_log import EventLog
from app.inference_service import CameraFrame
from app.ollama_client import OllamaClient
from app.runtime import Runtime
from app.settings_store import SettingsStore

ANSWER = {"visible_objects": ["blok"], "observed_relationships": [], "evidence": "Blok ligt goed.", "status": "completed"}


class FakeCameras(CameraManager):
    """Delivers a new frame per call, or nothing when `online` is false."""

    def __init__(self, store):
        super().__init__(store, backend=object())
        self.online = True
        self.sequence = 0

    def sync(self):
        pass

    def all_healthy(self):
        return True

    def frames(self, mode):
        if not self.online:
            return []
        self.sequence += 1
        noise = np.random.default_rng(self.sequence).integers(60, 200, (108, 192, 3)).astype(np.uint8)
        return [CameraFrame(1, self.sequence, noise)]


def build(tmp_path: Path, handler) -> Runtime:
    store = SettingsStore(tmp_path / "settings.json")
    store.settings.interval_s = 1
    client = OllamaClient(transport=httpx.MockTransport(handler))
    return Runtime(store, client, FakeCameras(store), EventLog(tmp_path / "events.sqlite"))


def ollama(content: str, done_reason: str = "stop", fail: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "m:1", "capabilities": ["vision"]}, {"name": "text:1"}]})
        if fail:
            raise httpx.ConnectError("weg")
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": done_reason})

    return handler


def test_only_vision_models_are_offered_and_one_is_selected(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))
    asyncio.run(rt.refresh_models())
    assert [m.name for m in rt.vision_models()] == ["m:1"]
    assert rt.store.settings.model == "m:1"


def test_three_analyses_are_needed_for_one_step(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))
    # The first default step requires having seen it unfinished.
    rt.engine.workflow.steps[0].requires_transition = False

    async def run():
        await rt.refresh_models()
        for _ in range(2):
            await rt._analyse_once()
        assert rt.engine.records[0].confirmations == 2
        await rt._analyse_once()

    asyncio.run(run())
    rt.engine.workflow.steps[0].requires_transition = True
    assert rt.engine.records[0].method.value == "ai"
    assert rt.metrics()["total"] == 3


def test_invalid_output_counts_nothing(tmp_path):
    rt = build(tmp_path, ollama("kapot"))

    async def run():
        await rt.refresh_models()
        await rt._analyse_once()

    asyncio.run(run())
    assert rt.invalid == 1
    assert rt.engine.records[0].confirmations == 0


def test_ollama_failure_is_reported_and_never_confirms(tmp_path):
    rt = build(tmp_path, ollama("", fail=True))

    async def run():
        await rt.refresh_models()
        await rt._analyse_once()

    asyncio.run(run())
    assert rt.monitoring == "error"
    assert rt.failed == 1
    assert rt.engine.records[0].confirmations == 0


def test_missing_camera_is_a_state_not_a_crash(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))
    rt.cameras.online = False

    async def run():
        await rt.refresh_models()
        await rt._analyse_once()

    asyncio.run(run())
    assert rt.message == "Geen camerabeeld beschikbaar."


def test_snapshot_is_json_serialisable(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))
    json.dumps(rt.snapshot())
