"""Application runtime: owns the engine and runs the single-flight monitoring loop."""
import asyncio
import base64
import json
import statistics
import time
from collections import deque
from pathlib import Path

import cv2
from fastapi import WebSocket

from .camera_manager import CameraManager
from .default_workflows import DEFAULT_WORKFLOWS
from .demonstration import Filmstrip, StepSegmenter, small_gray
from .device_profile import PROFILES, Device, ProfileName, detect_device, model_limit_gb
from .event_log import EventLog, describe
from .inference_service import CameraFrame, InferenceService, encode_frame
from .motion_counter import TurnCounter
from .observation import InvalidObservation, Observation, ObservationStatus
from .ollama_client import ModelInfo, OllamaClient, OllamaUnavailable
from .performance import PerformanceTracker
from .settings_store import DATA_DIR, Roi, Settings, SettingsStore
from .workflow_engine import StepState, WorkflowEngine
from .workflow_models import Workflow, WorkflowStep
from .workflow_repository import WorkflowRepository

PREFERRED_MODEL = "qwen3-vl:4b-instruct"
HEALTH_INTERVAL_S = 5.0
CALIBRATION_EVERY = 6  # health ticks, so about every 30 s
COUNT_INTERVAL_S = 1 / 15
PROFILE_LABELS = {"light": "Licht", "power": "Krachtig"}
MAX_DEMO_STEPS = 15
DEMO_SAMPLE_S = 0.5
DEMO_WIDTH = 1024  # stored pictures; the model gets at most image_width anyway
MIN_SUGGESTED_TURNS = 2  # a single counted turn is too little to suggest a count for the step

SIMULATED = {
    "valid": (ObservationStatus.COMPLETED, "Gesimuleerd: de stap lijkt voltooid.", None),
    "incomplete": (ObservationStatus.INCOMPLETE, "Gesimuleerd: de stap is nog niet voltooid.", None),
    "uncertain": (ObservationStatus.UNCERTAIN, "Gesimuleerd: onvoldoende visueel bewijs.", None),
    "wrong": (ObservationStatus.INCOMPLETE, "Gesimuleerd: verkeerde handeling.", "verkeerd onderdeel geplaatst"),
}


class Busy(Exception):
    """The model is in use; a second request would break the single-flight rule."""


class NoFrames(Exception):
    pass


class DemoState(Exception):
    """The demonstration is not in a state that allows this."""


class ModelTooLarge(Exception):
    """The model would not load fully on this device, or under this profile."""


class Runtime:
    def __init__(
        self,
        store: SettingsStore,
        client: OllamaClient,
        cameras: CameraManager,
        log: EventLog,
        repository: WorkflowRepository,
        device: Device | None = None,
    ):
        self.store = store
        self.client = client
        self.cameras = cameras
        self.log = log
        self.repository = repository
        self.device = device or detect_device()
        self.inference = InferenceService(client, store.settings.inference)
        self.performance = PerformanceTracker()
        self.model_memory_mb: float | None = None
        self.simulated = False
        self.switching_model = False
        self._playground = asyncio.Lock()
        self._simulated_sequence = 0
        self.workflows = repository.all()
        workflow = (
            self.workflows.get(store.settings.workflow_id)
            or self.workflows.get(DEFAULT_WORKFLOWS[0].id)
            or next(iter(self.workflows.values()))
        )
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
        self._count_task: asyncio.Task | None = None
        self.detections: dict[int, dict] = {}
        # Demonstration: pictures stay in memory only and are dropped once the steps are written.
        self.demo: dict | None = None
        self._demo_states: list[list[CameraFrame]] = []
        self._demo_turns = 0
        self._demo_task: asyncio.Task | None = None
        self._demo_capture: asyncio.Task | None = None
        self._demo_camera = 1
        self._segmenter = StepSegmenter()
        self._strip = Filmstrip()
        self._demo_strips: list[list[CameraFrame]] = []
        self._detect_turn = 0
        self.turn_counter = TurnCounter()
        self._health_task: asyncio.Task | None = None
        self._sockets: set[WebSocket] = set()

    async def start(self) -> None:
        await asyncio.to_thread(self.cameras.sync)
        await self.refresh_models()
        await self.settle_profile()
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        await self.stop_monitoring()
        if self._health_task:
            self._health_task.cancel()
        await asyncio.to_thread(self.cameras.stop)
        await self.client.close()

    async def _health_loop(self) -> None:
        ticks = 0
        while True:
            await asyncio.sleep(HEALTH_INTERVAL_S)
            ticks += 1
            # The mat is cheap to find, so a rebuilt setup is picked up within seconds.
            await self.check_calibration(reference=ticks % CALIBRATION_EVERY == 1)
            if not self.cameras.all_healthy():
                await asyncio.to_thread(self.cameras.sync)
            await self.refresh_models()
            status = self.cameras.status()
            await asyncio.to_thread(self.performance.sample, status)
            self.model_memory_mb = await self.client.loaded_memory_mb()

    async def refresh_models(self) -> None:
        try:
            self.models = await self.client.list_models()
            self.ollama_connected = True
        except OllamaUnavailable:
            self.ollama_connected = False
            await self.push()
            return
        names = {model.name for model in self.vision_models() if self.fits(model)}
        if self.store.settings.model not in names:
            choice = PREFERRED_MODEL if PREFERRED_MODEL in names else next(iter(sorted(names)), None)
            self.store.settings.model = choice
            self.store.save()
        await self.push()

    def vision_models(self) -> list[ModelInfo]:
        return [model for model in self.models if model.vision]

    @property
    def active_profile(self) -> ProfileName:
        choice = self.store.settings.device_profile
        return self.device.recommended if choice == "auto" else choice

    def fits(self, model: ModelInfo) -> bool:
        limit = model_limit_gb(self.device, self.active_profile)
        return limit is None or model.size is None or model.size / 1e9 <= limit

    async def settle_profile(self) -> None:
        """Applies the profile only when it changed, so later adjustments stay as they are."""
        if self.store.settings.applied_profile == self.active_profile:
            return
        profile = PROFILES[self.active_profile]
        settings = self.store.settings
        settings.inference = settings.inference.model_copy(update={"image_width": profile.image_width})
        settings.interval_s = profile.interval_s
        settings.boxes_all_cameras = profile.boxes_all_cameras
        settings.applied_profile = self.active_profile
        self.inference.settings = settings.inference
        self.store.save()
        self.log.add(f"Apparaatprofiel toegepast: {PROFILE_LABELS[self.active_profile]}.")
        await self.refresh_models()

    async def set_device_profile(self, choice: str) -> None:
        await self.stop_monitoring()
        self.store.settings.device_profile = choice
        self.store.save()
        await self.settle_profile()
        await self.refresh_models()

    def active_model(self) -> ModelInfo | None:
        return next((m for m in self.models if m.name == self.store.settings.model), None)

    def _record(self, events) -> None:
        for event in events:
            self.log.add(describe(event, self.engine.workflow))

    async def start_monitoring(self) -> None:
        if self._task or self.simulated or self.switching_model or self._playground.locked() or self.demo_busy:
            return
        if self.engine.finished:
            self._record(self.engine.start())
        self.message = None
        await self.check_calibration()
        self.monitoring = "running"
        self.log.add("Monitoring gestart.")
        self._task = asyncio.create_task(self._loop())
        self._count_task = asyncio.create_task(self._count_loop())
        await self.push()

    async def stop_monitoring(self) -> None:
        task, self._task = self._task, None
        if self._count_task:
            self._count_task.cancel()
            self._count_task = None
        if task:
            # Cancelling drops an in-flight request; its result can no longer reach the engine.
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.performance.stop()
            self.log.add("Monitoring gestopt.")
        self.monitoring = "idle"
        self.detections.clear()
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

    async def _count_loop(self) -> None:
        # Beside the analysis loop, not in it: a turn is over long before an analysis returns.
        counted_step = None
        sequence = -1
        while (step := self.engine.active_step) is not None:
            await asyncio.sleep(COUNT_INTERVAL_S)
            if step.expected_turns is None:
                continue
            if step.id != counted_step:
                counted_step = step.id
                self.turn_counter.reset()
            frame = self.cameras.count_frame()
            if frame is None or frame.sequence == sequence:
                continue
            sequence = frame.sequence
            turns = await asyncio.to_thread(self.turn_counter.feed, frame.image, frame.captured_at)
            if turns:
                self.engine.add_turns(turns)
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
            duration = time.monotonic() - started
            self.durations.append(duration)
            self.performance.record_analysis(
                duration, len(frames), self.store.settings.inference.image_width, self.store.settings.interval_s
            )
        events = self.engine.apply(obs)
        self._record(events)
        self._remember(obs, events)
        self.monitoring = "running"
        await self.push()
        if obs.model and self.store.settings.show_boxes and self.engine.active_step is step:
            await self._detect(model, step, frames)

    async def _detect(self, model: ModelInfo, step: WorkflowStep, frames: list[CameraFrame]) -> None:
        """Runs after the verdict, so boxes can never influence or delay a decision already made.

        On light hardware one camera per round, taking turns: both would double every round.
        """
        if not self.store.settings.boxes_all_cameras:
            frames = [frames[self._detect_turn % len(frames)]]
            self._detect_turn += 1
        for frame in frames:
            try:
                found = await self.inference.detect(model, step, frame)
            except OllamaUnavailable:
                return
            self.detections[frame.camera] = {
                "step_id": step.id,
                "time": time.strftime("%H:%M:%S"),
                "boxes": [self.cameras.to_full_image(frame.camera, box).model_dump() for box in found],
            }
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
                "simulated": obs.simulated,
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
        self.turn_counter.reset()
        self._record(self.engine.reject_completion())
        await self.push()

    async def reset_step(self) -> None:
        self.turn_counter.reset()
        self._record(self.engine.reset_active_step())
        await self.push()

    async def restart_workflow(self) -> None:
        self._record(self.engine.start())
        self.observations.clear()
        self.detections.clear()
        await self.push()

    async def select_workflow(self, workflow_id: str) -> None:
        await self.stop_monitoring()
        self.engine = WorkflowEngine(self.workflows[workflow_id], simulated=self.simulated)
        self.store.settings.workflow_id = workflow_id
        self.store.save()
        await self.restart_workflow()

    async def save_workflow(self, workflow: Workflow) -> None:
        self.repository.save(workflow)
        self.workflows = self.repository.all()
        self.log.add(f"Werkinstructie opgeslagen: {workflow.name}.")
        if workflow.id == self.engine.workflow.id:
            await self.select_workflow(workflow.id)
        else:
            await self.push()

    async def delete_workflow(self, workflow_id: str) -> None:
        self.repository.delete(workflow_id)
        self.workflows = self.repository.all()
        if workflow_id == self.engine.workflow.id:
            await self.select_workflow(next(iter(self.workflows)))
        else:
            await self.push()

    async def select_model(self, name: str) -> None:
        was_running = self._task is not None
        await self.stop_monitoring()
        model = next(m for m in self.models if m.name == name)
        if not self.fits(model):
            raise ModelTooLarge
        self.switching_model = True
        self.message = f"Model {name} laden en controleren…"
        await self.push()
        try:
            await self.inference.verify_model(model)
        except OllamaUnavailable:
            failure = f"Model {name} kon niet worden geactiveerd; {self.store.settings.model} blijft actief."
            self.log.add(failure)
        else:
            failure = None
            self.store.settings.model = name
            self.store.save()
            self._record(self.engine.reset_counters())
            self.log.add(f"AI-model gewijzigd naar {name}.")
        self.switching_model = False
        self.message = None
        if was_running:
            await self.start_monitoring()
        self.message = failure
        await self.push()

    async def set_simulation(self, enabled: bool) -> None:
        """Only an explicit choice gets here: a live failure never falls back to simulation."""
        await self.stop_monitoring()
        self.simulated = enabled
        self.engine = WorkflowEngine(self.engine.workflow, simulated=enabled)
        self.message = None
        self.log.add("Simulatiemodus ingeschakeld." if enabled else "Simulatiemodus uitgeschakeld.")
        await self.restart_workflow()

    async def simulate(self, kind: str) -> None:
        step = self.engine.active_step
        if not self.simulated or step is None:
            return
        status, evidence, deviation = SIMULATED[kind]
        self._simulated_sequence += 1
        obs = Observation(
            step_id=step.id,
            status=status,
            evidence=evidence,
            frames={1: self._simulated_sequence},
            simulated=True,
            deviation=deviation,
        )
        events = self.engine.apply(obs)
        self._record(events)
        self._remember(obs, events)
        await self.push()

    async def run_playground(self, models: list[str], question: str, mode: str, structured: bool) -> dict:
        """Uses the model but never the engine, so a test cannot complete a work step."""
        if self._task or self.switching_model or self._playground.locked() or self.demo_busy:
            raise Busy
        async with self._playground:
            frames = self.cameras.frames(mode)
            if not frames:
                raise NoFrames
            results = []
            # Sequential on purpose: two loaded models can exhaust the Air's memory.
            for name in models:
                model = next((m for m in self.models if m.name == name), None)
                try:
                    if model is None:
                        raise OllamaUnavailable("model niet gevonden")
                    results.append(await self.inference.ask(model, frames, question, structured))
                except OllamaUnavailable:
                    results.append({"model": name, "error": "Dit model gaf geen antwoord."})
        return {
            "question": question,
            "images": [{"camera": f.camera, "jpeg": encode_frame(f.image, 480)} for f in frames],
            "results": results,
        }

    async def set_roi(self, number: int, roi: Roi | None) -> None:
        self.cameras.set_roi(number, roi)
        self.detections.pop(number, None)
        self._record(self.engine.reset_counters())
        self.log.add(f"Werkgebied camera {number} {'ingesteld' if roi else 'verwijderd'}.")
        await self.push()

    async def set_count_area(self, number: int, roi: Roi | None) -> None:
        self.cameras.set_count_area(number, roi)
        self.turn_counter.reset()
        self.log.add(f"Telgebied {'ingesteld op camera ' + str(number) if roi else 'verwijderd'}.")
        await self.push()

    async def calibrate(self, number: int) -> bool:
        saved = await asyncio.to_thread(self.cameras.calibrate, number)
        if saved:
            self.log.add(f"Camera {number} gekalibreerd: huidig beeld is de nieuwe referentie.")
        await self.push()
        return saved

    async def check_calibration(self, reference: bool = True) -> None:
        """A bumped camera would otherwise analyse the wrong spot without anyone noticing.

        A camera that sees the work mat takes its areas from it; the reference picture is the
        fallback for a setup without mat.
        """
        moved = False
        for number in self.cameras.slots:
            mat = await asyncio.to_thread(self.cameras.check_workmat, number)
            if mat is not None:
                moved |= mat["moved"]
                if mat["changed"]:
                    self.log.add(
                        f"Camera {number}: werkmat gevonden, werkgebied automatisch ingesteld."
                        if mat["found"]
                        else f"Camera {number}: werkmat niet meer in beeld; het laatste werkgebied blijft staan."
                    )
                if mat["found"]:
                    if mat["moved"]:
                        self.detections.pop(number, None)
                    continue
            if not reference:
                continue
            outcome = await asyncio.to_thread(self.cameras.check_calibration, number)
            if outcome is None:
                continue
            # Areas moved, so earlier confirmations were about a slightly different spot.
            moved |= outcome.get("moved", False)
            if not outcome["changed"]:
                continue
            percent = f"{outcome['shift'] * 100:.1f}".replace(".", ",") if outcome["shift"] is not None else None
            if outcome["state"] == "corrected":
                self.log.add(f"Camera {number} is {percent}% verschoven: werkgebied en telgebied zijn meebewogen.")
            elif outcome["state"] == "lost":
                self.log.add(f"Camera {number} lijkt verplaatst of het beeld wijkt te veel af: kalibreer opnieuw.")
            else:
                self.log.add(f"Camera {number} staat weer op de gekalibreerde plek.")
            self.detections.pop(number, None)
        if moved:
            self._record(self.engine.reset_counters())
            self.turn_counter.reset()
        await self.push()

    @property
    def demo_busy(self) -> bool:
        return self.demo is not None and self.demo["state"] in ("recording", "generating")

    def _demo_frames(self) -> list[CameraFrame]:
        frames = []
        for frame in self.cameras.frames("both"):
            height, width = frame.image.shape[:2]
            image = frame.image
            if width > DEMO_WIDTH:
                size = (DEMO_WIDTH, round(height * DEMO_WIDTH / width))
                image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
            frames.append(CameraFrame(frame.camera, frame.sequence, image))
        return frames

    async def start_demo(self, name: str, parts: list[str] | None = None) -> None:
        if self.demo_busy or self.simulated:
            raise DemoState
        await self.stop_monitoring()
        frames = self._demo_frames()
        if not frames:
            raise NoFrames
        self._demo_states = [frames]
        self._demo_turns = 0
        self._demo_strips = []
        # The top view if there is one: it sees the hands on the mat best.
        self._demo_camera = min(frame.camera for frame in frames)
        self._segmenter.reset()
        self._strip = Filmstrip()
        self._strip.add(time.monotonic(), 0.0, self._camera_frame(frames))
        self.demo = {
            "name": name,
            "parts": parts or [],
            "auto": True,
            "moving": False,
            "state": "recording",
            "steps": [],
            "progress": 0,
            "workflow_id": None,
            "failed": [],
        }
        self.log.add(f"Voordoen gestart: {name}. Beginsituatie vastgelegd.")
        self._demo_task = asyncio.create_task(self._demo_count_loop())
        self._demo_capture = asyncio.create_task(self._demo_capture_loop())
        await self.push()

    def _camera_frame(self, frames: list[CameraFrame]) -> CameraFrame | None:
        return next((frame for frame in frames if frame.camera == self._demo_camera), None)

    async def _demo_capture_loop(self) -> None:
        """Keeps pictures of the step in progress and notices when it is done."""
        while self.demo and self.demo["state"] == "recording":
            await asyncio.sleep(DEMO_SAMPLE_S)
            frame = self._camera_frame(self._demo_frames())
            if frame is None:
                continue
            now = time.monotonic()
            movement, finished = await asyncio.to_thread(
                lambda: self._segmenter.feed(small_gray(frame.image), now)
            )
            self._strip.add(now, movement, frame)
            if self.demo["moving"] != self._segmenter.moving:
                self.demo["moving"] = self._segmenter.moving
                await self.push()
            if finished and self.demo["auto"] and len(self.demo["steps"]) < MAX_DEMO_STEPS:
                await self.mark_demo_step(None, automatic=True)

    async def set_demo_options(self, auto: bool | None = None, step: int | None = None, note: str | None = None) -> None:
        if not self.demo or self.demo["state"] != "recording":
            raise DemoState
        if auto is not None:
            self.demo["auto"] = auto
        if step is not None:
            if not 0 <= step < len(self.demo["steps"]):
                raise DemoState
            self.demo["steps"][step]["note"] = note or None
        await self.push()

    async def _demo_count_loop(self) -> None:
        self.turn_counter.reset()
        sequence = -1
        while self.demo and self.demo["state"] == "recording":
            await asyncio.sleep(COUNT_INTERVAL_S)
            frame = self.cameras.count_frame()
            if frame is None or frame.sequence == sequence:
                continue
            sequence = frame.sequence
            turns = await asyncio.to_thread(self.turn_counter.feed, frame.image, frame.captured_at)
            if turns:
                self._demo_turns += turns
                await self.push()

    async def mark_demo_step(self, note: str | None, automatic: bool = False) -> None:
        if not self.demo or self.demo["state"] != "recording" or len(self.demo["steps"]) >= MAX_DEMO_STEPS:
            raise DemoState
        frames = self._demo_frames()
        if not frames:
            raise NoFrames
        after = self._camera_frame(frames)
        strip = self._strip.select(after, PROFILES[self.active_profile].strip_pictures) if after else []
        self._demo_strips.append(strip)
        self._demo_states.append(frames)
        self.demo["steps"].append(
            {
                "time": time.strftime("%H:%M:%S"),
                "note": note or None,
                "turns": self._demo_turns,
                "auto": automatic,
                "pictures": len(strip),
                "seconds": round(self._strip.span_s()),
            }
        )
        # The end of this step is the start of the next one.
        self._strip = Filmstrip()
        if after:
            self._strip.add(time.monotonic(), 0.0, after)
        self._segmenter.reset()
        self.demo["moving"] = False
        self._demo_turns = 0
        self.turn_counter.reset()
        how = "automatisch herkend" if automatic else "vastgelegd"
        self.log.add(f"Voordoen: stap {len(self.demo['steps'])} {how}.")
        await self.push()

    async def cancel_demo(self) -> None:
        for task in (self._demo_task, self._demo_capture):
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self._demo_task = self._demo_capture = None
        if self.demo and self.demo["state"] in ("recording", "generating"):
            self.log.add("Voordoen geannuleerd.")
        self.demo = None
        self._demo_states = []
        self._demo_strips = []
        self._strip = Filmstrip()
        await self.push()

    async def finish_demo(self) -> None:
        if not self.demo or self.demo["state"] != "recording" or not self.demo["steps"]:
            raise DemoState
        for task in (self._demo_task, self._demo_capture):
            if task:
                task.cancel()
        self.demo["state"] = "generating"
        self._demo_task = asyncio.create_task(self._write_demo_steps())
        await self.push()

    def demo_thumbnail(self, index: int) -> bytes | None:
        if not 0 <= index < len(self._demo_states) or not self._demo_states[index]:
            return None
        return base64.b64decode(encode_frame(self._demo_states[index][0].image, 320))

    async def _write_demo_steps(self) -> None:
        """One model request per step, one at a time, like every other model use."""
        demo = self.demo
        model = self.active_model()
        steps = []
        try:
            if model is None:
                raise OllamaUnavailable("geen model")
            for index, mark in enumerate(demo["steps"]):
                demo["progress"] = index + 1
                await self.push()
                steps.append(await self._describe(model, index, mark))
        except OllamaUnavailable:
            demo["state"] = "failed"
            self.log.add("Voordoen mislukt: het model gaf geen antwoord.")
            self._demo_states = []
            self._demo_strips = []
            return await self.push()
        workflow = Workflow(
            id=f"voorgedaan-{time.strftime('%Y%m%d-%H%M%S')}",
            name=demo["name"],
            steps=steps,
        )
        self.repository.save(workflow)
        self.workflows = self.repository.all()
        demo |= {"state": "done", "workflow_id": workflow.id}
        self._demo_states = []
        self._demo_strips = []
        self.log.add(f"Werkinstructie gemaakt uit voorbeeld: {workflow.name} ({len(steps)} stappen). Nog niet actief.")
        await self.push()

    async def _describe(self, model: ModelInfo, index: int, mark: dict) -> WorkflowStep:
        before, after = self._demo_states[index], self._demo_states[index + 1]
        strip = self._demo_strips[index] if index < len(self._demo_strips) else []
        if len(strip) < 2:
            # One camera seen before and after; a camera that dropped out in between cannot compare.
            shared = sorted({f.camera for f in before} & {f.camera for f in after})
            strip = [next(f for f in frames if f.camera == shared[0]) for frames in (before, after)] if shared else []
        gap = mark["seconds"] / max(1, len(strip) - 1) if mark.get("seconds") else DEMO_SAMPLE_S
        turns = mark["turns"] if mark["turns"] >= MIN_SUGGESTED_TURNS else None
        number = index + 1
        for _ in range(2 if len(strip) >= 2 else 0):
            try:
                draft = await self.inference.describe_step(model, strip, mark["note"], self.demo["parts"], gap)
            except InvalidObservation:
                continue
            return WorkflowStep(
                id=f"stap-{number}",
                title=draft.titel,
                instruction=draft.instructie,
                completion_criterion=draft.completion_criterion,
                expected_objects=draft.expected_objects,
                requires_transition=True,
                expected_turns=turns,
            )
        # Never invent a step: leave it visibly empty for the operator to fill in.
        self.demo["failed"].append(number)
        return WorkflowStep(
            id=f"stap-{number}",
            title=mark["note"] or f"Stap {number}",
            instruction="Niet herkend uit het voorbeeld. Vul zelf in.",
            completion_criterion="Fill in what must be visible when this step is done.",
            requires_transition=True,
            expected_turns=turns,
        )

    async def save_snapshot(self, name: str) -> int:
        saved = await asyncio.to_thread(self.cameras.save_snapshot, name)
        self.log.add(f"Testopname '{name}' opgeslagen ({saved} beeld(en)).")
        await self.push()
        return saved

    async def select_test_scene(self, scene: str) -> None:
        self.cameras.test_source.select(scene)
        self.detections.clear()
        self.log.add(f"Testscène gekozen: {scene}.")
        await self.push()

    async def update_settings(self, changes: dict) -> None:
        merged = self.store.settings.model_dump() | changes
        self.store.settings = Settings.model_validate(merged)
        self.inference.settings = self.store.settings.inference
        self.store.save()
        await self.push()

    async def reset_preferences(self) -> None:
        """Everything back to defaults, except which physical camera is which view."""
        await self.stop_monitoring()
        self.store.settings = Settings(camera_keys=self.store.settings.camera_keys)
        self.inference.settings = self.store.settings.inference
        self.store.save()
        self.log.add("Voorkeuren teruggezet.")
        await self.settle_profile()
        await self.refresh_models()

    async def clear_events(self) -> None:
        self.log.clear()
        await self.push()

    async def delete_snapshots(self, folder: Path | None = None) -> int:
        paths = list((folder or DATA_DIR / "snapshots").glob("*.jpg"))
        for path in paths:
            path.unlink(missing_ok=True)
        self.log.add(f"{len(paths)} opgeslagen beelden verwijderd.")
        await self.push()
        return len(paths)

    def performance_report(self) -> dict:
        report = self.performance.report()
        report["stats"] |= {"failed": self.failed, "invalid": self.invalid}
        report["system"] = report["system"] | {"model_memory_mb": self.model_memory_mb}
        report["cameras"] = self.cameras.status()
        return report

    async def swap_cameras(self) -> None:
        self.cameras.swap()
        self.detections.clear()
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

    def _camera_views(self) -> list[dict]:
        active = self.engine.active_step
        views = self.cameras.status()
        for view in views:
            found = self.detections.get(view["slot"])
            # Boxes name the objects of one step, so they end with that step.
            view["detections"] = found if found and active and found["step_id"] == active.id else None
        return views

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
                    "turns": record.turns,
                    "expected_turns": step.expected_turns,
                }
            )
        source = self.cameras.test_source
        return {
            "ollama_connected": self.ollama_connected,
            "models": [m.model_dump(exclude={"capabilities"}) | {"fits": self.fits(m)} for m in self.vision_models()],
            "device": self.device.model_dump()
            | {"profile": self.active_profile, "model_limit_gb": model_limit_gb(self.device, self.active_profile)},
            "monitoring": self.monitoring,
            "message": self.message,
            "simulated": self.simulated,
            "switching_model": self.switching_model,
            "test_source": {"scene": source.scene, "scenes": source.scenes()} if source else None,
            "settings": self.store.settings.model_dump(exclude={"camera_keys", "rois", "count_area", "applied_profile"}),
            "cameras": self._camera_views(),
            "workflows": [{"id": w.id, "name": w.name} for w in self.workflows.values()],
            "workflow": {"id": engine.workflow.id, "name": engine.workflow.name, "steps": steps},
            "progress": round(engine.progress * 100),
            "observations": list(self.observations),
            "log": list(self.log.recent),
            "metrics": self.metrics(),
            "demo": self.demo,
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
