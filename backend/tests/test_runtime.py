import asyncio
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
from pydantic import ValidationError

from app.camera_manager import CameraManager
from app.event_log import EventLog
from app.inference_service import CameraFrame
from app.ollama_client import OllamaClient
from app.runtime import Busy, Runtime
from app.settings_store import SettingsStore
from app.workflow_models import Workflow, WorkflowStep
from app.workflow_repository import LastWorkflow, WorkflowRepository

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
    repository = WorkflowRepository(tmp_path / "workflows")
    return Runtime(store, client, FakeCameras(store), EventLog(tmp_path / "events.sqlite"), repository)


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


def test_simulation_runs_through_the_engine_and_is_labelled(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))

    async def run():
        await rt.set_simulation(True)
        await rt.simulate("incomplete")
        for _ in range(2):
            await rt.simulate("valid")
        assert rt.engine.records[0].method is None
        await rt.simulate("valid")

    asyncio.run(run())
    assert rt.engine.records[0].method.value == "simulated"
    assert rt.snapshot()["observations"][0]["simulated"] is True


def test_monitoring_cannot_start_in_simulation(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))

    async def run():
        await rt.set_simulation(True)
        await rt.start_monitoring()

    asyncio.run(run())
    assert rt.monitoring == "idle"


def test_ollama_failure_never_switches_to_simulation(tmp_path):
    rt = build(tmp_path, ollama("", fail=True))

    async def run():
        await rt.refresh_models()
        await rt._analyse_once()

    asyncio.run(run())
    assert rt.simulated is False


def test_model_is_only_activated_after_a_successful_image_request(tmp_path):
    fail = {"on": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            names = [{"name": "a:1", "capabilities": ["vision"]}, {"name": "b:1", "capabilities": ["vision"]}]
            return httpx.Response(200, json={"models": names})
        if fail["on"]:
            raise httpx.ConnectError("weg")
        assert json.loads(request.content)["messages"][-1]["images"]
        return httpx.Response(200, json={"message": {"content": "ok"}, "done_reason": "stop"})

    rt = build(tmp_path, handler)

    async def run():
        await rt.refresh_models()
        await rt.select_model("b:1")
        assert rt.store.settings.model == "b:1"
        fail["on"] = True
        await rt.select_model("a:1")

    asyncio.run(run())
    assert rt.store.settings.model == "b:1"
    assert "kon niet worden geactiveerd" in rt.message
    assert rt.switching_model is False


def test_playground_never_touches_the_workflow(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))

    async def run():
        await rt.refresh_models()
        return await rt.run_playground(["m:1", "ontbreekt:1"], "Wat zie je?", "1", True)

    result = asyncio.run(run())
    assert result["results"][0]["valid"] is True
    assert "error" in result["results"][1]
    assert rt.engine.records[0].confirmations == 0
    assert rt.observations == type(rt.observations)(maxlen=20)


def test_playground_refuses_while_monitoring(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))

    async def run():
        rt._task = object()
        with pytest.raises(Busy):
            await rt.run_playground(["m:1"], "?", "1", False)

    asyncio.run(run())


def workflow(workflow_id: str = "eigen") -> Workflow:
    step = WorkflowStep(id="s1", title="Stap", instruction="Doe iets", completion_criterion="Visible")
    return Workflow(id=workflow_id, name="Eigen", steps=[step])


def test_saved_workflow_survives_a_restart(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))
    asyncio.run(rt.save_workflow(workflow()))
    assert "eigen" in WorkflowRepository(tmp_path / "workflows").all()


def test_saving_the_active_workflow_restarts_it(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))

    async def run():
        await rt.save_workflow(workflow())
        await rt.select_workflow("eigen")
        await rt.confirm_step()
        await rt.save_workflow(workflow())

    asyncio.run(run())
    assert rt.engine.progress == 0


def test_deleting_the_active_workflow_selects_another(tmp_path):
    rt = build(tmp_path, ollama(json.dumps(ANSWER)))

    async def run():
        await rt.save_workflow(workflow())
        await rt.select_workflow("eigen")
        await rt.delete_workflow("eigen")

    asyncio.run(run())
    assert rt.engine.workflow.id != "eigen"


def test_last_workflow_cannot_be_deleted(tmp_path):
    repository = WorkflowRepository(tmp_path / "w")
    repository.delete("bolt-assembly")
    repository.delete("screw-tightening")
    with pytest.raises(LastWorkflow):
        repository.delete("object-placement")


def test_import_rejects_path_tricks_and_unknown_fields():
    with pytest.raises(ValidationError):
        workflow("../../etc/passwd")
    data = workflow().model_dump() | {"run": "rm -rf /"}
    with pytest.raises(ValidationError):
        Workflow.model_validate(data)


def test_damaged_workflow_file_is_skipped(tmp_path):
    repository = WorkflowRepository(tmp_path / "w")
    (tmp_path / "w" / "kapot.json").write_text("{")
    assert len(repository.all()) == 3


def boxes_and_verdict(fail_boxes: bool = False):
    """Answers verdict requests with ANSWER and box requests with one box, or with an outage."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "m:1", "capabilities": ["vision"]}]})
        body = json.loads(request.content)
        if "objects" not in body["format"]["properties"]:
            return httpx.Response(200, json={"message": {"content": json.dumps(ANSWER)}, "done_reason": "stop"})
        if fail_boxes:
            raise httpx.ConnectError("weg")
        content = json.dumps({"objects": [{"label": "blok", "box_2d": [100, 100, 300, 300]}]})
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": "stop"})

    return handler


def test_boxes_arrive_after_the_verdict_and_end_with_the_step(tmp_path):
    rt = build(tmp_path, boxes_and_verdict())
    rt.engine.workflow.steps[0].requires_transition = False
    rt.cameras.slots[1].key = "cam"

    async def run():
        await rt.refresh_models()
        await rt._analyse_once()
        assert rt._camera_views()[0]["detections"]["boxes"][0]["label"] == "blok"
        rt.engine.confirm_manually()
        assert rt._camera_views()[0]["detections"] is None

    asyncio.run(run())


def test_failing_boxes_do_not_touch_the_verdict(tmp_path):
    rt = build(tmp_path, boxes_and_verdict(fail_boxes=True))
    rt.engine.workflow.steps[0].requires_transition = False

    async def run():
        await rt.refresh_models()
        await rt._analyse_once()

    asyncio.run(run())
    assert rt.engine.active_record.confirmations == 1
    assert rt.failed == 0
    assert rt.detections == {}


def test_switching_boxes_off_sends_only_the_verdict_request(tmp_path):
    calls = []
    verdict = boxes_and_verdict()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            calls.append(request)
        return verdict(request)

    rt = build(tmp_path, handler)
    rt.store.settings.show_boxes = False

    async def run():
        await rt.refresh_models()
        await rt._analyse_once()

    asyncio.run(run())
    assert len(calls) == 1


def test_boxes_are_asked_for_parts_not_for_marked_positions(tmp_path):
    prompts = []
    verdict = boxes_and_verdict()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            prompts.append(json.loads(request.content)["messages"][-1]["content"])
        return verdict(request)

    rt = build(tmp_path, handler)
    rt.engine.workflow.steps[0].expected_objects = ["red component", "position A"]

    async def run():
        await rt.refresh_models()
        await rt._analyse_once()

    asyncio.run(run())
    assert "red component" in prompts[-1]
    assert "position A" not in prompts[-1]


DRAFT = {
    "changes": ["rood blok op A gelegd"],
    "expected_objects": ["red block", "position A"],
    "completion_criterion": "A red block lies inside position A.",
    "titel": "Rood blok plaatsen",
    "instructie": "Leg het rode blok op positie A.",
}


def demonstration(draft=DRAFT, fail: bool = False):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "m:1", "capabilities": ["vision"]}]})
        if fail:
            raise httpx.ConnectError("weg")
        body = json.loads(request.content)
        calls.append(body)
        content = json.dumps(draft) if "changes" in body.get("format", {}).get("properties", {}) else json.dumps(ANSWER)
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": "stop"})

    return handler, calls


async def wait_for_demo(rt: Runtime) -> None:
    for _ in range(100):
        if rt.demo["state"] not in ("recording", "generating"):
            return
        await asyncio.sleep(0.02)


def test_a_demonstration_becomes_an_inactive_workflow_to_review(tmp_path):
    handler, calls = demonstration()
    rt = build(tmp_path, handler)
    active = rt.engine.workflow.id

    async def run():
        await rt.refresh_models()
        await rt.start_demo("Blokken leggen", ["red block"])
        await rt.mark_demo_step("rood op A")
        await rt.mark_demo_step(None)
        await rt.finish_demo()
        await wait_for_demo(rt)

    asyncio.run(run())
    assert rt.demo["state"] == "done"
    workflow = rt.workflows[rt.demo["workflow_id"]]
    assert [step.title for step in workflow.steps] == ["Rood blok plaatsen", "Rood blok plaatsen"]
    assert all(step.requires_transition for step in workflow.steps)
    assert rt.engine.workflow.id == active  # never activated by itself
    assert "rood op A" in calls[0]["messages"][0]["content"]
    assert "The parts are called: red block" in calls[0]["messages"][0]["content"]
    assert len(calls[0]["messages"][0]["images"]) == 2  # before and after
    assert rt._demo_states == []  # pictures are dropped


def test_an_unreadable_description_leaves_the_step_empty_instead_of_inventing_one(tmp_path):
    handler, _ = demonstration(draft={"title": "x"})
    rt = build(tmp_path, handler)

    async def run():
        await rt.refresh_models()
        await rt.start_demo("Test")
        await rt.mark_demo_step("bout eruit")
        await rt.finish_demo()
        await wait_for_demo(rt)

    asyncio.run(run())
    step = rt.workflows[rt.demo["workflow_id"]].steps[0]
    assert rt.demo["failed"] == [1]
    assert step.title == "bout eruit"
    assert "Vul zelf in" in step.instruction


def test_a_model_outage_saves_nothing(tmp_path):
    handler, _ = demonstration(fail=True)
    rt = build(tmp_path, handler)
    before = set(rt.workflows)

    async def run():
        await rt.refresh_models()
        await rt.start_demo("Test")
        await rt.mark_demo_step(None)
        await rt.finish_demo()
        await wait_for_demo(rt)

    asyncio.run(run())
    assert rt.demo["state"] == "failed"
    assert set(rt.workflows) == before


def test_monitoring_and_playground_wait_while_recording(tmp_path):
    handler, _ = demonstration()
    rt = build(tmp_path, handler)

    async def run():
        await rt.refresh_models()
        await rt.start_demo("Test")
        await rt.start_monitoring()
        assert rt._task is None
        with pytest.raises(Busy):
            await rt.run_playground(["m:1"], "Wat zie je?", "1", False)
        await rt.cancel_demo()
        assert rt.demo is None

    asyncio.run(run())


def test_finishing_without_steps_is_refused(tmp_path):
    from app.runtime import DemoState

    handler, _ = demonstration()
    rt = build(tmp_path, handler)

    async def run():
        await rt.refresh_models()
        await rt.start_demo("Test")
        with pytest.raises(DemoState):
            await rt.finish_demo()
        await rt.cancel_demo()

    asyncio.run(run())


def test_counted_turns_during_a_step_are_suggested_for_it(tmp_path):
    handler, _ = demonstration()
    rt = build(tmp_path, handler)

    async def run():
        await rt.refresh_models()
        await rt.start_demo("Schroef")
        rt._demo_turns = 5
        await rt.mark_demo_step(None)
        rt._demo_turns = 1
        await rt.mark_demo_step(None)
        await rt.finish_demo()
        await wait_for_demo(rt)

    asyncio.run(run())
    steps = rt.workflows[rt.demo["workflow_id"]].steps
    assert [step.expected_turns for step in steps] == [5, None]
