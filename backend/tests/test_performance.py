import asyncio
import json

import httpx

from app.camera_manager import CameraManager
from app.event_log import EventLog
from app.ollama_client import OllamaClient
from app.performance import PerformanceTracker, percentile
from app.runtime import Runtime
from app.settings_store import Roi, Settings, SettingsStore
from app.workflow_repository import WorkflowRepository

import pytest
from pydantic import ValidationError


def build(tmp_path) -> Runtime:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "m:1", "capabilities": ["vision"]}]})

    store = SettingsStore(tmp_path / "s.json")
    client = OllamaClient(transport=httpx.MockTransport(handler))
    cameras = CameraManager(store, backend=object())
    return Runtime(store, client, cameras, EventLog(tmp_path / "e.sqlite"), WorkflowRepository(tmp_path / "w"))


def test_percentile_uses_nearest_rank():
    assert percentile(list(range(1, 101)), 0.95) == 95
    assert percentile([7.0], 0.95) == 7.0


def test_empty_report_invents_nothing():
    stats = PerformanceTracker().report()["stats"]
    assert stats["last_s"] is None and stats["median_s"] is None and stats["per_minute"] is None


def test_slow_analysis_counts_skipped_opportunities():
    tracker = PerformanceTracker()
    tracker.record_analysis(20, 2, 768, 3)
    tracker.record_analysis(2, 1, 768, 3)
    assert tracker.skipped == 5


def test_history_is_bounded():
    tracker = PerformanceTracker()
    for _ in range(400):
        tracker.record_analysis(1, 1, 768, 3)
    assert len(tracker.analyses) == 300


def test_pause_between_runs_is_not_an_interval():
    tracker = PerformanceTracker()
    tracker.record_analysis(1, 1, 768, 3)
    tracker.stop()
    tracker.record_analysis(1, 1, 768, 3)
    assert tracker.analyses[-1]["gap_s"] is None


def test_sample_reports_real_process_values():
    tracker = PerformanceTracker()
    tracker.sample([{"slot": 1, "fps": 30.0}])
    assert tracker.samples[0]["fps"] == {"1": 30.0}
    assert tracker.system["memory_mb"] > 0


def test_inference_settings_reach_the_service(tmp_path):
    rt = build(tmp_path)
    inference = rt.store.settings.inference.model_dump() | {"image_width": 1024, "temperature": 0.2}
    asyncio.run(rt.update_settings({"inference": inference}))
    assert rt.inference.settings.image_width == 1024
    assert SettingsStore(tmp_path / "s.json").settings.inference.temperature == 0.2


@pytest.mark.parametrize("change", [{"image_width": 999}, {"num_ctx": 1}, {"keep_alive": "altijd"}])
def test_invalid_inference_settings_are_refused(tmp_path, change):
    rt = build(tmp_path)
    inference = rt.store.settings.inference.model_dump() | change
    with pytest.raises(ValidationError):
        asyncio.run(rt.update_settings({"inference": inference}))


def test_old_settings_file_still_loads(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"image_width": 512, "interval_s": 5}))
    assert SettingsStore(path).settings.interval_s == 5


def test_reset_keeps_the_camera_assignment_but_clears_work_areas(tmp_path):
    rt = build(tmp_path)
    rt.store.settings = Settings(interval_s=7, camera_keys={"1": "A"}, rois={"A": Roi(x=0, y=0, w=0.5, h=0.5)})

    async def run():
        await rt.reset_preferences()

    asyncio.run(run())
    assert rt.store.settings.interval_s == 3
    assert rt.store.settings.camera_keys == {"1": "A"}
    assert rt.store.settings.rois == {}


def test_clearing_events_empties_log_and_database(tmp_path):
    rt = build(tmp_path)
    rt.log.add("iets")
    asyncio.run(rt.clear_events())
    assert not rt.log.recent and rt.log.rows() == []


def test_delete_snapshots_removes_only_images(tmp_path):
    (tmp_path / "a_top.jpg").write_bytes(b"x")
    (tmp_path / "notitie.txt").write_text("blijft")
    rt = build(tmp_path)
    assert asyncio.run(rt.delete_snapshots(tmp_path)) == 1
    assert (tmp_path / "notitie.txt").exists()
