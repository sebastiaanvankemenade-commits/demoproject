import asyncio
import json

import httpx
import numpy as np
import pytest

from app.inference_service import CameraFrame, InferenceService
from app.observation import InvalidObservation, ObservationStatus
from app.ollama_client import ModelInfo, OllamaClient, OllamaUnavailable
from app.workflow_models import Workflow, WorkflowStep

STEP = WorkflowStep(id="s1", title="t", instruction="doe", completion_criterion="zichtbaar")
WORKFLOW = Workflow(id="wf", name="Test", steps=[STEP])
VISION = ModelInfo(name="vision:1", capabilities=["vision"])
ANSWER = {"visible_objects": ["blok"], "observed_relationships": [], "evidence": "Blok ligt in A.", "status": "completed"}


def frame(sequence: int = 1, camera: int = 1, level: int = 130) -> CameraFrame:
    noise = np.random.default_rng(sequence).integers(-30, 30, (108, 192, 3))
    return CameraFrame(camera, sequence, np.clip(level + noise, 0, 255).astype(np.uint8))


def service(handler) -> InferenceService:
    return InferenceService(OllamaClient(transport=httpx.MockTransport(handler)))


def reply(content: str, done_reason: str = "stop"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": done_reason})

    return handler


def test_observation_carries_the_frames_it_was_made_from():
    obs = asyncio.run(service(reply(json.dumps(ANSWER))).observe(VISION, WORKFLOW, STEP, [frame(7), frame(9, 2)]))
    assert obs.status is ObservationStatus.COMPLETED
    assert obs.frames == {1: 7, 2: 9}
    assert obs.model == "vision:1"


def test_truncated_answer_raises():
    with pytest.raises(InvalidObservation):
        asyncio.run(service(reply(json.dumps(ANSWER), "length")).observe(VISION, WORKFLOW, STEP, [frame()]))


def test_dark_frame_never_reaches_the_model():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("model must not be called")

    obs = asyncio.run(service(handler).observe(VISION, WORKFLOW, STEP, [frame(level=10)]))
    assert obs.status is ObservationStatus.UNCERTAIN


def test_one_bad_camera_blocks_the_whole_analysis():
    obs = asyncio.run(service(reply(json.dumps(ANSWER))).observe(VISION, WORKFLOW, STEP, [frame(), frame(2, 2, level=10)]))
    assert obs.status is ObservationStatus.UNCERTAIN


def test_ollama_failure_raises_instead_of_inventing_a_result():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("geen verbinding")

    with pytest.raises(OllamaUnavailable):
        asyncio.run(service(handler).observe(VISION, WORKFLOW, STEP, [frame()]))


def test_thinking_is_only_disabled_for_models_that_support_it():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps(ANSWER)}, "done_reason": "stop"})

    thinking = ModelInfo(name="vision:2", capabilities=["vision", "thinking"])
    asyncio.run(service(handler).observe(VISION, WORKFLOW, STEP, [frame()]))
    asyncio.run(service(handler).observe(thinking, WORKFLOW, STEP, [frame()]))
    assert "think" not in bodies[0]
    assert bodies[1]["think"] is False


def test_model_list_reports_only_what_ollama_says():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "a:1", "capabilities": ["vision"]}, {"name": "b:1"}]})

    models = asyncio.run(OllamaClient(transport=httpx.MockTransport(handler)).list_models())
    assert [model.vision for model in models] == [True, False]
    assert models[1].family is None
