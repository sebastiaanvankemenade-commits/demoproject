"""FastAPI entry point. Serves the API, camera previews and the built dashboard."""
import asyncio
import csv
import io
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import cv2

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import workmat
from .camera_manager import SLOT_LABELS, CameraManager
from .cameras.testsource import TestSource
from .event_log import EventLog
from .ollama_client import OllamaClient
from .runtime import SIMULATED, Busy, DemoState, ModelTooLarge, NoFrames, Runtime
from .settings_store import DATA_DIR, Roi, SettingsStore
from .workflow_models import Workflow
from .workflow_repository import LastWorkflow, WorkflowRepository

PREVIEW_FPS = 12
FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def build_runtime() -> Runtime:
    test_folder = os.environ.get("ASSEMBLYVISION_TEST_SOURCE")
    if test_folder:
        # Separate settings and history, so test views never mix with the real ones.
        store = SettingsStore(DATA_DIR / "settings-test.json")
        cameras = CameraManager(store, backend=TestSource(Path(test_folder)))
        log = EventLog(DATA_DIR / "events-test.sqlite")
    else:
        store = SettingsStore()
        cameras = CameraManager(store)
        log = EventLog()
    return Runtime(store, OllamaClient(), cameras, log, WorkflowRepository())


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = build_runtime()
    await app.state.runtime.start()
    yield
    await app.state.runtime.stop()


app = FastAPI(title="AssemblyVision", lifespan=lifespan)


def runtime() -> Runtime:
    return app.state.runtime


class NameBody(BaseModel):
    name: str


class SimulationBody(BaseModel):
    enabled: bool


class PlaygroundBody(BaseModel):
    models: list[str] = Field(min_length=1, max_length=2)
    question: str = Field(min_length=1, max_length=500)
    camera_mode: Literal["both", "1", "2"] = "both"
    structured: bool = False


@app.get("/api/state")
def get_state() -> dict:
    return runtime().snapshot()


@app.post("/api/monitoring/start")
async def start_monitoring() -> None:
    await runtime().start_monitoring()


@app.post("/api/monitoring/stop")
async def stop_monitoring() -> None:
    await runtime().stop_monitoring()


@app.post("/api/step/confirm")
async def confirm_step() -> None:
    await runtime().confirm_step()


@app.post("/api/step/reject")
async def reject_step() -> None:
    await runtime().reject_step()


@app.post("/api/step/reset")
async def reset_step() -> None:
    await runtime().reset_step()


@app.post("/api/workflow/restart")
async def restart_workflow() -> None:
    await runtime().restart_workflow()


@app.post("/api/workflow/select")
async def select_workflow(body: NameBody) -> None:
    if body.name not in runtime().workflows:
        raise HTTPException(404, "Werkinstructie niet gevonden.")
    await runtime().select_workflow(body.name)


@app.post("/api/model/select")
async def select_model(body: NameBody) -> None:
    if body.name not in {model.name for model in runtime().vision_models()}:
        raise HTTPException(404, "Model niet beschikbaar.")
    try:
        await runtime().select_model(body.name)
    except ModelTooLarge as exc:
        raise HTTPException(409, "Dit model is te groot voor dit apparaat of profiel.") from exc


@app.post("/api/device-profile")
async def set_device_profile(body: NameBody) -> None:
    if body.name not in ("auto", "light", "power"):
        raise HTTPException(422, "Onbekend profiel.")
    await runtime().set_device_profile(body.name)


@app.post("/api/settings")
async def update_settings(changes: dict) -> None:
    allowed = {"camera_mode", "interval_s", "inference", "show_boxes", "boxes_all_cameras", "auto_work_area"}
    try:
        await runtime().update_settings({k: v for k, v in changes.items() if k in allowed})
    except ValidationError as exc:
        raise HTTPException(422, "Ongeldige instelling.") from exc


@app.get("/api/performance")
def performance() -> dict:
    return runtime().performance_report()


@app.post("/api/models/refresh")
async def refresh_models() -> None:
    await runtime().refresh_models()


@app.get("/api/data/events.csv")
def export_events() -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["tijdstip", "gebeurtenis"])
    writer.writerows(runtime().log.rows())
    headers = {"Content-Disposition": "attachment; filename=assemblyvision-activiteit.csv"}
    return Response(buffer.getvalue(), media_type="text/csv", headers=headers)


@app.post("/api/data/clear-events")
async def clear_events() -> None:
    await runtime().clear_events()


@app.post("/api/data/delete-snapshots")
async def delete_snapshots() -> dict:
    return {"deleted": await runtime().delete_snapshots()}


@app.post("/api/data/reset-preferences")
async def reset_preferences() -> None:
    await runtime().reset_preferences()


@app.get("/api/workflows")
def list_workflows() -> list[Workflow]:
    return list(runtime().workflows.values())


@app.post("/api/workflows")
async def save_workflow(workflow: Workflow) -> None:
    await runtime().save_workflow(workflow)


@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str) -> None:
    if workflow_id not in runtime().workflows:
        raise HTTPException(404, "Werkinstructie niet gevonden.")
    try:
        await runtime().delete_workflow(workflow_id)
    except LastWorkflow as exc:
        raise HTTPException(409, "De laatste werkinstructie kan niet worden verwijderd.") from exc


@app.post("/api/simulation")
async def set_simulation(body: SimulationBody) -> None:
    await runtime().set_simulation(body.enabled)


@app.post("/api/simulation/observe")
async def simulate(body: NameBody) -> None:
    if body.name not in SIMULATED:
        raise HTTPException(404, "Onbekende simulatie.")
    await runtime().simulate(body.name)


@app.post("/api/playground")
async def playground(body: PlaygroundBody) -> dict:
    try:
        return await runtime().run_playground(body.models, body.question, body.camera_mode, body.structured)
    except Busy as exc:
        raise HTTPException(409, "Het model is bezig. Stop eerst de monitoring.") from exc
    except NoFrames as exc:
        raise HTTPException(409, "Geen camerabeeld beschikbaar.") from exc


@app.post("/api/test-source/scene")
async def select_test_scene(body: NameBody) -> None:
    source = runtime().cameras.test_source
    if source is None or body.name not in source.scenes():
        raise HTTPException(404, "Testscène niet gevonden.")
    await runtime().select_test_scene(body.name)


@app.post("/api/cameras/swap")
async def swap_cameras() -> None:
    await runtime().swap_cameras()


@app.post("/api/cameras/{number}/calibrate")
async def calibrate(number: int) -> None:
    if number not in (1, 2):
        raise HTTPException(404, "Onbekende camera.")
    if not await runtime().calibrate(number):
        raise HTTPException(409, "Geen beeld van deze camera om als referentie te bewaren.")


@app.get("/api/workmat.png")
async def workmat_page() -> Response:
    image = await asyncio.to_thread(workmat.render)
    ok, buffer = cv2.imencode(".png", image)
    headers = {"Content-Disposition": 'attachment; filename="assemblyvision-werkmat.png"'}
    return Response(buffer.tobytes(), media_type="image/png", headers=headers)


class DemoStartBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parts: list[str] = Field(default_factory=list, max_length=12)


class DemoStepBody(BaseModel):
    note: str | None = Field(default=None, max_length=120)


@app.post("/api/demo/start")
async def start_demo(body: DemoStartBody) -> None:
    try:
        await runtime().start_demo(body.name.strip(), [part.strip() for part in body.parts if part.strip()])
    except DemoState as exc:
        raise HTTPException(409, "Voordoen kan nu niet: er loopt al een voorbeeld of de simulatie staat aan.") from exc
    except NoFrames as exc:
        raise HTTPException(409, "Geen camerabeeld om de beginsituatie vast te leggen.") from exc


@app.post("/api/demo/step")
async def demo_step(body: DemoStepBody) -> None:
    try:
        await runtime().mark_demo_step((body.note or "").strip() or None)
    except DemoState as exc:
        raise HTTPException(409, "Er loopt geen opname, of het maximum aantal stappen is bereikt.") from exc
    except NoFrames as exc:
        raise HTTPException(409, "Geen camerabeeld om deze stap vast te leggen.") from exc


class DemoOptionsBody(BaseModel):
    auto: bool | None = None
    step: int | None = None
    note: str | None = Field(default=None, max_length=120)


@app.post("/api/demo/options")
async def demo_options(body: DemoOptionsBody) -> None:
    try:
        await runtime().set_demo_options(body.auto, body.step, (body.note or "").strip() or None)
    except DemoState as exc:
        raise HTTPException(409, "Er loopt geen opname, of die stap bestaat niet.") from exc


@app.post("/api/demo/finish")
async def finish_demo() -> None:
    try:
        await runtime().finish_demo()
    except DemoState as exc:
        raise HTTPException(409, "Leg eerst minstens één stap vast.") from exc


@app.post("/api/demo/cancel")
async def cancel_demo() -> None:
    await runtime().cancel_demo()


@app.get("/api/demo/{index}.jpg")
async def demo_picture(index: int) -> Response:
    image = runtime().demo_thumbnail(index)
    if image is None:
        raise HTTPException(404, "Geen beeld.")
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/calibration/check")
async def check_calibration() -> None:
    await runtime().check_calibration()


@app.get("/api/cameras/{number}/reference.jpg")
async def reference(number: int) -> Response:
    if number not in (1, 2):
        raise HTTPException(404, "Onbekende camera.")
    image = await asyncio.to_thread(runtime().cameras.reference_jpeg, number)
    if image is None:
        raise HTTPException(404, "Geen referentiebeeld.")
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/cameras/{number}/count-area")
async def set_count_area(number: int, roi: Roi | None = None) -> None:
    if number not in (1, 2):
        raise HTTPException(404, "Onbekende camera.")
    try:
        await runtime().set_count_area(number, roi)
    except ValueError as exc:
        raise HTTPException(409, "Geen camera aan deze positie gekoppeld.") from exc


@app.post("/api/cameras/{number}/roi")
async def set_roi(number: int, roi: Roi | None = None) -> None:
    if number not in SLOT_LABELS:
        raise HTTPException(404, "Camera niet gevonden.")
    try:
        await runtime().set_roi(number, roi)
    except ValueError as exc:
        raise HTTPException(409, "Deze camera is niet verbonden.") from exc


@app.post("/api/snapshots")
async def save_snapshot(body: NameBody) -> dict:
    name = re.sub(r"[^a-z0-9-]+", "-", body.name.lower()).strip("-")[:40]
    if not name:
        raise HTTPException(422, "Geef de opname een naam.")
    return {"name": name, "saved": await runtime().save_snapshot(name)}


@app.get("/api/cameras/{number}/stream")
async def camera_stream(number: int) -> StreamingResponse:
    if number not in SLOT_LABELS:
        raise HTTPException(404, "Camera niet gevonden.")

    async def frames():
        while True:
            jpeg = await asyncio.to_thread(runtime().cameras.preview, number)
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            await asyncio.sleep(1 / PREVIEW_FPS)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def websocket(socket: WebSocket) -> None:
    await socket.accept()
    rt = runtime()
    rt.add_socket(socket)
    try:
        # Regular pushes keep measured FPS and connection state current between events.
        while True:
            await socket.send_json(rt.snapshot())
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        rt.remove_socket(socket)


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="dashboard")
