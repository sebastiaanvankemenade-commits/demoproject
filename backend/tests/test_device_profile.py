import asyncio
import json

import httpx
import pytest

from app.camera_manager import CameraManager
from app.device_profile import Device, describe_device, model_limit_gb, parse_nvidia_smi
from app.event_log import EventLog
from app.ollama_client import OllamaClient
from app.runtime import ModelTooLarge, Runtime
from app.settings_store import SettingsStore
from app.workflow_repository import WorkflowRepository

SMALL, LARGE = 3_300_000_000, 40_000_000_000
WORKSTATION = Device(name="NVIDIA RTX PRO 6000", memory_gb=96, model_budget_gb=81.6, recommended="power")
AIR = Device(name="Apple M3", memory_gb=24, model_budget_gb=12, recommended="light")


def tags(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/tags":
        models = [
            {"name": "klein:4b", "size": SMALL, "capabilities": ["vision"]},
            {"name": "groot:90b", "size": LARGE, "capabilities": ["vision"]},
        ]
        return httpx.Response(200, json={"models": models})
    return httpx.Response(200, json={"message": {"content": "ok"}, "done_reason": "stop"})


def build(tmp_path, device: Device) -> Runtime:
    store = SettingsStore(tmp_path / "settings.json")
    client = OllamaClient(transport=httpx.MockTransport(tags))
    cameras = CameraManager(store, backend=object())
    return Runtime(store, client, cameras, EventLog(tmp_path / "e.sqlite"), WorkflowRepository(tmp_path / "w"), device)


async def started(rt: Runtime) -> None:
    await rt.refresh_models()
    await rt.settle_profile()


def test_the_largest_gpu_is_the_one_that_counts():
    assert parse_nvidia_smi("NVIDIA T400, 4096\nNVIDIA RTX PRO 6000 Blackwell, 97887\n") == pytest.approx(
        ("NVIDIA RTX PRO 6000 Blackwell", 95.6), abs=0.1
    )


@pytest.mark.parametrize("output", ["", "geen getal", "naam, [N/A]"])
def test_unreadable_nvidia_output_means_no_gpu(output):
    assert parse_nvidia_smi(output) is None


def test_a_workstation_gets_the_power_profile():
    device = describe_device(("NVIDIA RTX PRO 6000", 96), None, 128)
    assert (device.recommended, device.model_budget_gb) == ("power", 81.6)


def test_a_small_gpu_stays_light():
    assert describe_device(("NVIDIA GTX 1650", 4), None, 32).recommended == "light"


def test_a_mac_stays_light_and_shares_its_memory():
    device = describe_device(None, "Apple M3", 24)
    assert (device.name, device.recommended, device.model_budget_gb) == ("Apple M3", "light", 12)


def test_unknown_hardware_is_treated_carefully():
    device = describe_device(None, None, None)
    assert device.recommended == "light"
    assert model_limit_gb(device, "light") == 12


def test_the_light_profile_limits_models_even_on_a_big_machine():
    assert model_limit_gb(WORKSTATION, "light") == 12
    assert model_limit_gb(WORKSTATION, "power") == 81.6


def test_the_air_cannot_select_a_model_that_does_not_fit(tmp_path):
    rt = build(tmp_path, AIR)

    async def run():
        await started(rt)
        with pytest.raises(ModelTooLarge):
            await rt.select_model("groot:90b")

    asyncio.run(run())
    assert rt.store.settings.model == "klein:4b"
    assert {m["name"]: m["fits"] for m in rt.snapshot()["models"]} == {"klein:4b": True, "groot:90b": False}


def test_the_workstation_may_choose_the_large_model_but_is_never_moved_to_it(tmp_path):
    rt = build(tmp_path, WORKSTATION)

    async def run():
        await started(rt)
        rt.store.settings.model = "klein:4b"
        await rt.refresh_models()
        assert rt.store.settings.model == "klein:4b"
        await rt.select_model("groot:90b")

    asyncio.run(run())
    assert rt.store.settings.model == "groot:90b"


def test_the_profile_is_applied_once_so_later_changes_survive_a_restart(tmp_path):
    rt = build(tmp_path, WORKSTATION)

    async def run():
        await started(rt)
        assert rt.store.settings.inference.image_width == 1024
        assert rt.store.settings.boxes_all_cameras
        await rt.update_settings({"interval_s": 5})
        await rt.settle_profile()

    asyncio.run(run())
    assert rt.store.settings.interval_s == 5


def test_a_settings_file_from_another_machine_follows_the_new_device(tmp_path):
    rt = build(tmp_path, AIR)
    asyncio.run(started(rt))
    assert rt.store.settings.inference.image_width == 768

    moved = build(tmp_path, WORKSTATION)
    asyncio.run(started(moved))
    assert moved.store.settings.inference.image_width == 1024
    assert moved.store.settings.applied_profile == "power"


def test_choosing_light_by_hand_replaces_a_model_that_no_longer_fits(tmp_path):
    rt = build(tmp_path, WORKSTATION)

    async def run():
        await started(rt)
        await rt.select_model("groot:90b")
        await rt.set_device_profile("light")

    asyncio.run(run())
    assert rt.store.settings.device_profile == "light"
    assert rt.store.settings.model == "klein:4b"
    assert rt.store.settings.inference.image_width == 768


def test_a_chosen_profile_survives_a_restart(tmp_path):
    rt = build(tmp_path, WORKSTATION)
    asyncio.run(started(rt))
    asyncio.run(rt.set_device_profile("light"))

    again = build(tmp_path, WORKSTATION)
    asyncio.run(started(again))
    assert again.active_profile == "light"
    assert json.loads((tmp_path / "settings.json").read_text())["device_profile"] == "light"


def test_all_cameras_get_boxes_only_when_the_profile_allows_it(tmp_path):
    import numpy as np

    from app.inference_service import CameraFrame

    asked = []
    rt = build(tmp_path, WORKSTATION)

    async def fake(model, step, frame):
        asked.append(frame.camera)
        return []

    rt.inference.detect = fake
    frames = [CameraFrame(1, 1, np.zeros((8, 8, 3), np.uint8)), CameraFrame(2, 1, np.zeros((8, 8, 3), np.uint8))]

    async def run():
        await started(rt)
        await rt._detect(rt.active_model(), rt.engine.active_step, frames)
        assert asked == [1, 2]
        asked.clear()
        await rt.set_device_profile("light")
        await rt._detect(rt.active_model(), rt.engine.active_step, frames)
        assert len(asked) == 1

    asyncio.run(run())


def test_a_light_device_keeps_demonstrations_within_the_default_context():
    from app.device_profile import PROFILES
    from app.inference_service import TOKENS_PER_IMAGE, InferenceSettings

    light = PROFILES["light"].strip_pictures
    assert TOKENS_PER_IMAGE * light + 2048 <= InferenceSettings().num_ctx
    assert PROFILES["power"].strip_pictures > light
