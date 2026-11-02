"""Activity history: a short list for the dashboard, everything in local SQLite."""
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path

from .settings_store import DATA_DIR
from .workflow_engine import EngineEvent, EventType, IgnoreReason
from .workflow_models import Workflow

IGNORE_TEXT = {
    IgnoreReason.STALE_FRAME: "geen vers beeld",
    IgnoreReason.WRONG_STEP: "hoort niet bij de actieve stap",
    IgnoreReason.NOT_RUNNING: "werkinstructie loopt niet",
    IgnoreReason.NO_FRAMES: "geen beeld ontvangen",
    IgnoreReason.SIMULATION_MISMATCH: "simulatie en live lopen door elkaar",
    IgnoreReason.AWAITING_TRANSITION: "stap moet eerst onafgerond gezien zijn",
}


def describe(event: EngineEvent, workflow: Workflow) -> str:
    titles = {step.id: f"Stap {i}" for i, step in enumerate(workflow.steps, start=1)}
    step = titles.get(event.step_id, "Stap")
    match event.type:
        case EventType.STARTED:
            return "Werkinstructie gestart."
        case EventType.STEP_ACTIVATED:
            return f"{step} geactiveerd."
        case EventType.OBSERVATION_COUNTED:
            return f"{step}: bevestiging {event.detail}."
        case EventType.OBSERVATION_IGNORED:
            return f"{step}: observatie niet meegeteld ({IGNORE_TEXT[IgnoreReason(event.detail)]})."
        case EventType.NOT_COMPLETE:
            return f"{step}: nog niet voltooid."
        case EventType.UNCERTAIN:
            return f"Onvoldoende bewijs voor {step.lower()}."
        case EventType.DEVIATION_SUSPECTED:
            return f"{step}: mogelijke afwijking — {event.detail}"
        case EventType.DEVIATION_CONFIRMED:
            return f"{step}: afwijking gedetecteerd — {event.detail}"
        case EventType.STEP_CONFIRMED:
            how = "handmatig bevestigd" if event.detail == "manual" else "visueel bevestigd"
            return f"{step} {how}."
        case EventType.COMPLETION_REJECTED:
            return f"{step}: voltooiing afgewezen door operator."
        case EventType.STEP_RESET:
            return f"{step} teruggezet."
        case EventType.COUNTERS_RESET:
            return f"{step}: bevestigingen gewist."
        case EventType.WORKFLOW_COMPLETED:
            return "Werkinstructie voltooid."


class EventLog:
    def __init__(self, path: Path | None = None, keep: int = 200):
        path = path or DATA_DIR / "events.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS events (at TEXT NOT NULL, text TEXT NOT NULL)")
        self.recent: deque[dict] = deque(maxlen=keep)

    def add(self, text: str) -> None:
        now = datetime.now()
        self.recent.appendleft({"time": now.strftime("%H:%M:%S"), "text": text})
        self._db.execute("INSERT INTO events VALUES (?, ?)", (now.isoformat(), text))
        self._db.commit()
