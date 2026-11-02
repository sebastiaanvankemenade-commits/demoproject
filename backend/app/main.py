"""FastAPI entry point. Serves the API, camera previews and the built dashboard."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from .camera_manager import SLOT_LABELS, CameraManager
from .event_log import EventLog
from .ollama_client import OllamaClient
from .runtime import Runtime
from .settings_store import SettingsStore

PREVIEW_FPS = 12
FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = SettingsStore()
    app.state.runtime = Runtime(store, OllamaClient(), CameraManager(store), EventLog())
    await app.state.runtime.start()
    yield
    await app.state.runtime.stop()


app = FastAPI(title="AssemblyVision", lifespan=lifespan)


def runtime() -> Runtime:
    return app.state.runtime


class NameBody(BaseModel):
    name: str


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
    await runtime().select_model(body.name)


@app.post("/api/settings")
async def update_settings(changes: dict) -> None:
    allowed = {"camera_mode", "interval_s", "image_width"}
    try:
        await runtime().update_settings({k: v for k, v in changes.items() if k in allowed})
    except ValidationError as exc:
        raise HTTPException(422, "Ongeldige instelling.") from exc


@app.post("/api/cameras/swap")
async def swap_cameras() -> None:
    await runtime().swap_cameras()


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
