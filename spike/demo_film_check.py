"""Demonstrates Workflow B to a running test server and prints the steps the app makes of it.

Start the test server first, then from backend/:
ASSEMBLYVISION_URL=http://127.0.0.1:8421 .venv/bin/python ../spike/demo_film_check.py
"""
import json
import os
import sys
import time
import urllib.request

APP = os.environ.get("ASSEMBLYVISION_URL", "http://127.0.0.1:8420")


def call(path: str, body=None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{APP}{path}", data=data, method="POST" if body is not None or path != "/api/state" else "GET", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def main(notes: bool) -> None:
    call("/api/demo/cancel", {})
    call("/api/test-source/scene", {"name": "1_leeg"})
    time.sleep(1.5)
    call("/api/demo/start", {"name": "Blokken voordoen", "parts": ["red block", "blue block", "green block"]})
    call("/api/test-source/scene", {"name": "voordoen_blokken"})
    started = time.monotonic()
    while time.monotonic() - started < 40:
        demo = call("/api/state")["demo"]
        if len(demo["steps"]) >= 3:
            break
        time.sleep(0.5)
    call("/api/test-source/scene", {"name": "5_alles_geplaatst"})
    steps = demo["steps"]
    print("herkende stappen:", [(s["time"], s["auto"], s["pictures"], s["seconds"]) for s in steps], flush=True)
    if notes:
        for index, note in enumerate(["rood blok op A", "blauw blok op B", "groen blok op C"][: len(steps)]):
            call("/api/demo/options", {"step": index, "note": note})
    call("/api/demo/finish", {})
    started = time.monotonic()
    while True:
        demo = call("/api/state")["demo"]
        if demo["state"] not in ("generating", "recording"):
            break
        time.sleep(2)
    print(f"klaar na {time.monotonic() - started:.0f} s, status {demo['state']}, mislukt {demo['failed']}", flush=True)
    if demo["workflow_id"]:
        with urllib.request.urlopen(f"{APP}/api/workflows") as response:
            workflow = next(w for w in json.load(response) if w["id"] == demo["workflow_id"])
        for step in workflow["steps"]:
            print(json.dumps({k: step[k] for k in ("title", "instruction", "completion_criterion", "expected_objects")}, ensure_ascii=False))
    call("/api/demo/cancel", {})


if __name__ == "__main__":
    main(len(sys.argv) > 1)
