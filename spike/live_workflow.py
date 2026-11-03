"""Run Workflow B with the real model on test scenes, including a wrongly placed part.

Needs the app running with --test-beelden. Run: python3 spike/live_workflow.py
Proves the wiring on generated images; it says little about recognising real parts.
"""
import json
import sys
import time
import urllib.request

APP = "http://127.0.0.1:8420"


def post(path: str, body: dict | None = None) -> None:
    data = json.dumps(body).encode() if body is not None else b""
    request = urllib.request.Request(APP + path, data, {"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(request).read()


def state() -> dict:
    with urllib.request.urlopen(f"{APP}/api/state") as response:
        return json.load(response)


def wait_for(condition, timeout: float = 240) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = state()
        if condition(current):
            return current
        time.sleep(1)
    raise SystemExit("TIMEOUT: " + json.dumps(state()["workflow"]["steps"])[:600])


def analyses(current: dict) -> int:
    return current["metrics"]["total"] + current["metrics"]["invalid"]


def step_state(current: dict, index: int) -> str:
    return current["workflow"]["steps"][index]["state"]


def report(current: dict) -> None:
    entry = current["observations"][0]
    print(f"  {entry['status']:10} {entry['evidence'][:90]} | {' '.join(entry['decision'])[:60]}", flush=True)


def scene(name: str) -> None:
    post("/api/test-source/scene", {"name": name})
    time.sleep(1)


def after_analyses(count: int) -> dict:
    target = analyses(state()) + count
    return wait_for(lambda current: analyses(current) >= target)


def until_completed(index: int) -> None:
    seen = analyses(state())
    while step_state(state(), index) != "completed":
        current = wait_for(lambda s: analyses(s) > seen or step_state(s, index) == "completed")
        seen = analyses(current)
        if current["observations"]:
            report(current)


def main() -> None:
    post("/api/workflow/select", {"name": "object-placement"})
    post("/api/settings", {"camera_mode": sys.argv[1] if len(sys.argv) > 1 else "both"})
    scene("1_leeg")
    post("/api/monitoring/start")

    print("Leeg, stap 1 mag niet afgaan")
    report(after_analyses(1))
    assert step_state(state(), 0) != "completed"

    print("Rood op A, stap 1 hoort af te gaan")
    scene("2_rood_op_a")
    until_completed(0)

    print("Blauw op C (fout), stap 2 mag niet afgaan")
    scene("3_blauw_verkeerd_op_c")
    for _ in range(4):
        report(after_analyses(1))
    wrong = state()
    print("  stap 2 na 4 analyses op fout beeld:", step_state(wrong, 1), "|", wrong["workflow"]["steps"][1]["warning"])
    assert step_state(wrong, 1) != "completed", "FOUT: verkeerd geplaatst onderdeel goedgekeurd"
    print("  afwijking herkend:", step_state(wrong, 1) == "deviation")

    print("Blauw op B, stap 2 hoort af te gaan")
    scene("4_blauw_op_b")
    until_completed(1)

    print("Alles geplaatst, stap 3 hoort af te gaan")
    scene("5_alles_geplaatst")
    until_completed(2)

    final = wait_for(lambda current: current["monitoring"] == "idle")
    print("Klaar:", final["progress"], "%", final["metrics"])
    print([(s["title"], s["state"], s["method"]) for s in final["workflow"]["steps"]])


if __name__ == "__main__":
    main()
