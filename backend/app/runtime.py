"""Application runtime: owns the engine and runs the single-flight monitoring loop."""
import asyncio
import json
import statistics
import time
from collections import deque

from fastapi import WebSocket

from .camera_manager import CameraManager
from .default_workflows import DEFAULT_WORKFLOWS
from .event_log import EventLog, describe
from .inference_service import InferenceService
from .observation import InvalidObservation, Observation
from .ollama_client import ModelInfo, OllamaClient, OllamaUnavailable
from .settings_store import SettingsStore
from .workflow_engine import StepState, WorkflowEngine

PREFERRED_MODEL = "qwen3-vl:4b-instruct"
HEALTH_INTERVAL_S = 5.0


class Runtime:
    def __init__(self, store: SettingsStore, client: OllamaClient, cameras: CameraManager, log: EventLog):
        self.store = store
        self.client = client
        self.cameras = cameras
        self.log = log
        self.inference = InferenceService(client)
        self.workflows = {workflow.id: workflow for workflow in DEFAULT_WORKFLOWS}
        workflow = self.workflows.get(store.settings.workflow_id) or DEFAULT_WORKFLOWS[0]
        self.engine = WorkflowEngine(workflow)
        self.engine.start()
        self.models: list[ModelInfo] = []
        self.ollama_connected = False
        self.monitoring = "idle"  # idle | running | analyzing | error
        self.message: str | None = None
        self.observations: deque[dict] = deque(maxlen=20)
        self.durations: deque[float] = deque(maxlen=200)
        self.starts: deque[float] = deque(maxlen=20)
        self.failed = 0
        self.invalid = 0
        self._task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._sockets: set[WebSocket] = set()

    async def start(self) -> None:
        await asyncio.to_thread(self.cameras.sync)
        await self.refresh_models()
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        await self.stop_monitoring()
        if self._health_task:
            self._health_task.cancel()
        await asyncio.to_thread(self.cameras.stop)
        await self.client.close()

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(HEALTH_INTERVAL_S)
            if not self.cameras.all_healthy():
                await asyncio.to_thread(self.cameras.sync)
            await self.refresh_models()

    async def refresh_models(self) -> None:
        try:
            self.models = await self.client.list_models()
            self.ollama_connected = True
        except OllamaUnavailable:
            self.ollama_connected = False
            await self.push()
            return
        names = {model.name for model in self.vision_models()}
        if self.store.settings.model not in names:
            choice = PREFERRED_MODEL if PREFERRED_MODEL in names else next(iter(sorted(names)), None)
            self.store.settings.model = choice
            self.store.save()
        await self.push()

    def vision_models(self) -> list[ModelInfo]:
        return [model for model in self.models if model.vision]

    def active_model(self) -> ModelInfo | None:
        return next((m for m in self.models if m.name == self.store.settings.model), None)

    def _record(self, events) -> None:
        for event in events:
            self.log.add(describe(event, self.engine.workflow))

    async def start_monitoring(self) -> None:
        if self._task:
            return
        if self.engine.finished:
            self._record(self.engine.start())
        self.message = None
        self.monitoring = "running"
        self.log.add("Monitoring gestart.")
        self._task = asyncio.create_task(self._loop())
        await self.push()

    async def stop_monitoring(self) -> None:
        task, self._task = self._task, None
        if task:
            # Cancelling drops an in-flight request; its result can no longer reach the engine.
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.log.add("Monitoring gestopt.")
        self.monitoring = "idle"
        await self.push()

    async def _loop(self) -> None:
        # One request at a time, by construction: the next analysis only starts after this
        # one returns, and it always takes the newest frame. Nothing can queue up.
        while self.engine.active_step is not None:
            started = time.monotonic()
            await self._analyse_once()
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.2, self.store.settings.interval_s - elapsed))
        self._task = None
        self.monitoring = "idle"
        self.log.add("Monitoring gestopt: werkinstructie voltooid.")
        await self.push()

    async def _analyse_once(self) -> None:
        model = self.active_model()
        step = self.engine.active_step
        frames = self.cameras.frames(self.store.settings.camera_mode)
        wanted = 2 if self.store.settings.camera_mode == "both" else 1
        if model is None:
            return await self._set_problem("Geen vision-model beschikbaar in Ollama.")
        if not frames:
            return await self._set_problem("Geen camerabeeld beschikbaar.")

        self.monitoring = "analyzing"
        self.message = "Analyseert met één camera: de andere levert geen beeld." if len(frames) < wanted else None
        self.starts.append(time.monotonic())
        await self.push()

        started = time.monotonic()
        try:
            obs = await self.inference.observe(model, self.engine.workflow, step, frames)
        except InvalidObservation:
            self.invalid += 1
            self.monitoring = "running"
            self.log.add("Ongeldig modelantwoord: niet meegeteld.")
            return await self.push()
        except OllamaUnavailable:
            self.failed += 1
            return await self._set_problem("Ollama reageert niet. Geen enkele stap wordt nu bevestigd.")

        if obs.model:
            self.durations.append(time.monotonic() - started)
        events = self.engine.apply(obs)
        self._record(events)
        self._remember(obs, events)
        self.monitoring = "running"
        await self.push()

    async def _set_problem(self, message: str) -> None:
        if self.message != message:
            self.log.add(message)
        self.monitoring = "error"
        self.message = message
        await self.push()

    def _remember(self, obs: Observation, events) -> None:
        self.observations.appendleft(
            {
                "time": obs.observed_at.astimezone().strftime("%H:%M:%S"),
                "cameras": sorted(obs.frames),
                "model": obs.model,
                "visible_objects": obs.visible_objects,
                "relationships": obs.observed_relationships,
                "evidence": obs.evidence,
                "status": obs.status.value,
                "decision": [describe(event, self.engine.workflow) for event in events],
            }
        )

    async def confirm_step(self) -> None:
        self._record(self.engine.confirm_manually())
        await self.push()

    async def reject_step(self) -> None:
        self._record(self.engine.reject_completion())
        await self.push()

    async def reset_step(self) -> None:
        self._record(self.engine.reset_active_step())
        await self.push()

    async def restart_workflow(self) -> None:
        self._record(self.engine.start())
        self.observations.clear()
        await self.push()

    async def select_workflow(self, workflow_id: str) -> None:
        await self.stop_monitoring()
        self.engine = WorkflowEngine(self.workflows[workflow_id])
        self.store.settings.workflow_id = workflow_id
        self.store.save()
        await self.restart_workflow()

    async def select_model(self, name: str) -> None:
        was_running = self._task is not None
        await self.stop_monitoring()
        self.store.settings.model = name
        self.store.save()
        self._record(self.engine.reset_counters())
        self.log.add(f"AI-model gewijzigd naar {name}.")
        if was_running:
            await self.start_monitoring()
        await self.push()

    async def update_settings(self, changes: dict) -> None:
        merged = self.store.settings.model_dump() | changes
        self.store.settings = type(self.store.settings).model_validate(merged)
        self.store.save()
        await self.push()

    async def swap_cameras(self) -> None:
        self.cameras.swap()
        self._record(self.engine.reset_counters())
        self.log.add("Camera's gewisseld.")
        await self.push()

    def metrics(self) -> dict:
        durations = list(self.durations)
        starts = list(self.starts)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        return {
            "last_s": round(durations[-1], 1) if durations else None,
            "average_s": round(statistics.fmean(durations), 1) if durations else None,
            "actual_interval_s": round(statistics.fmean(gaps), 1) if gaps else None,
            "total": len(durations),
            "failed": self.failed,
            "invalid": self.invalid,
        }

    def snapshot(self) -> dict:
        engine = self.engine
        active = engine.active_record
        steps = []
        for number, (step, record) in enumerate(zip(engine.workflow.steps, engine.records), start=1):
            state = record.state.value
            if record is active and self.monitoring == "analyzing" and record.state is StepState.ACTIVE:
                state = "analyzing"
            steps.append(
                {
                    "id": step.id,
                    "number": number,
                    "title": step.title,
                    "instruction": step.instruction,
                    "state": state,
                    "confirmations": record.confirmations,
                    "required": record.required_confirmations,
                    "method": record.method.value if record.method else None,
                    "confirmed_at": record.confirmed_at.astimezone().strftime("%H:%M:%S") if record.confirmed_at else None,
                    "warning": record.deviation,
                }
            )
        return {
            "ollama_connected": self.ollama_connected,
            "models": [m.model_dump(exclude={"capabilities"}) for m in self.vision_models()],
            "monitoring": self.monitoring,
            "message": self.message,
            "settings": self.store.settings.model_dump(exclude={"camera_keys"}),
            "cameras": self.cameras.status(),
            "workflows": [{"id": w.id, "name": w.name} for w in self.workflows.values()],
            "workflow": {"id": engine.workflow.id, "name": engine.workflow.name, "steps": steps},
            "progress": round(engine.progress * 100),
            "observations": list(self.observations),
            "log": list(self.log.recent),
            "metrics": self.metrics(),
        }

    def add_socket(self, socket: WebSocket) -> None:
        self._sockets.add(socket)

    def remove_socket(self, socket: WebSocket) -> None:
        self._sockets.discard(socket)

    async def push(self) -> None:
        if not self._sockets:
            return
        payload = json.dumps(self.snapshot())
        for socket in list(self._sockets):
            try:
                await socket.send_text(payload)
            except (RuntimeError, ConnectionError):
                self._sockets.discard(socket)
