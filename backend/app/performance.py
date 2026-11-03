"""Bounded performance history. Only values that were measured; nothing is estimated."""
import math
import os
import statistics
import subprocess
import time
from collections import deque

MAX_ANALYSES = 300
MAX_SAMPLES = 360  # One hour at the five-second health interval.


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


class ProcessMonitor:
    """CPU from the process's own clocks and memory from ps, which both exist on macOS and Linux."""

    def __init__(self) -> None:
        self._last_cpu = sum(os.times()[:2])
        self._last_wall = time.monotonic()

    def read(self) -> dict:
        cpu, wall = sum(os.times()[:2]), time.monotonic()
        elapsed = wall - self._last_wall
        percent = (cpu - self._last_cpu) / elapsed * 100 if elapsed > 0 else None
        self._last_cpu, self._last_wall = cpu, wall
        return {"cpu_percent": None if percent is None else round(percent, 1), "memory_mb": self._memory_mb()}

    @staticmethod
    def _memory_mb() -> float | None:
        try:
            output = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True, timeout=2
            ).stdout
            return round(int(output.strip()) / 1024, 1)
        except (OSError, ValueError, subprocess.SubprocessError):
            return None


class PerformanceTracker:
    def __init__(self) -> None:
        self.analyses: deque[dict] = deque(maxlen=MAX_ANALYSES)
        self.samples: deque[dict] = deque(maxlen=MAX_SAMPLES)
        self.skipped = 0
        self.system: dict = {}
        self._process = ProcessMonitor()
        self._last_start: float | None = None

    def record_analysis(self, duration_s: float, images: int, width: int, interval_s: float) -> None:
        now = time.time()
        started = now - duration_s
        gap = None if self._last_start is None else round(started - self._last_start, 2)
        self._last_start = started
        # Every interval that passed during this analysis was an opportunity to start one.
        self.skipped += max(0, int(duration_s // interval_s) - 1) if interval_s else 0
        self.analyses.append(
            {"t": round(now, 1), "duration_s": round(duration_s, 2), "gap_s": gap, "images": images, "width": width}
        )

    def stop(self) -> None:
        """The pause between two monitoring runs is not an analysis interval."""
        self._last_start = None

    def sample(self, cameras: list[dict]) -> None:
        self.system = self._process.read()
        self.samples.append({"t": round(time.time(), 1), "fps": {str(c["slot"]): c["fps"] for c in cameras}})

    def report(self) -> dict:
        durations = [entry["duration_s"] for entry in self.analyses]
        gaps = [entry["gap_s"] for entry in self.analyses if entry["gap_s"] is not None]
        stats = {
            "total": len(durations),
            "skipped": self.skipped,
            "last_s": durations[-1] if durations else None,
            "average_s": round(statistics.fmean(durations), 2) if durations else None,
            "median_s": round(statistics.median(durations), 2) if durations else None,
            "p95_s": round(percentile(durations, 0.95), 2) if durations else None,
            "per_minute": round(60 / statistics.fmean(gaps), 2) if gaps else None,
        }
        return {
            "analyses": list(self.analyses),
            "samples": list(self.samples),
            "stats": stats,
            "system": self.system,
        }
