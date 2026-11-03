"""Checks the turn counter and the model's boxes in the real app, in headless Chrome, with the real model.

Needs the app running with --test-beelden. From backend/: .venv/bin/python ../spike/overlay_check.py <map voor screenshots>
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import ui_check
from ui_check import APP, Page, check, state

CLIP_FRAMES = 121
CLIP_TURNS = 6


def post(path: str, body=None) -> None:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{APP}{path}", data=data, method="POST", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(request).read()


def count_turns(page: Page, shots: str) -> None:
    post("/api/workflow/select", {"name": "screw-tightening"})
    post("/api/test-source/scene", {"name": "schroef_6x"})
    check(page.contains("Teken een telgebied"), "checklist vraagt om een telgebied")
    box = page.eval("(() => { const r = document.querySelector('section').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
    page.eval("document.querySelector('[aria-label^=\"Telgebied Bovenaanzicht\"]').click()")
    check(page.contains("Sleep een kader om de plek"), "telgebied-modus opent")
    time.sleep(0.5)
    page.drag(box[0] + box[2] * 0.2, box[1] + box[3] * 0.2, box[0] + box[2] * 0.8, box[1] + box[3] * 0.9)
    check(page.click("Opslaan"), "telgebied opslaan")
    time.sleep(0.5)
    check(state()["cameras"][0]["count_area"], "telgebied staat op camera 1")

    post("/api/monitoring/start")
    check(page.wait("document.body.innerText.includes('/ 6 draaibewegingen')", 20), "teller staat op het beeld")
    started = time.monotonic()
    first = state()["workflow"]["steps"][0]["turns"]
    measured = 32
    time.sleep(measured)
    now = state()
    counted = now["workflow"]["steps"][0]["turns"] - first
    # The clip slows down with the machine, so the real playback rate sets what to expect.
    expected = CLIP_TURNS * (time.monotonic() - started) * now["cameras"][0]["fps"] / CLIP_FRAMES
    print(f"Tijdens analyses: {counted} geteld in {measured:.0f} s, verwacht ±{expected:.0f}", flush=True)
    check(abs(counted - expected) <= 3, f"telling houdt het tempo van de clip bij ({counted} tegen ±{expected:.0f})")
    page.screenshot(f"{shots}/teller.png")
    post("/api/monitoring/stop")
    post(f"/api/cameras/1/count-area")


def boxes(page: Page, shots: str) -> None:
    post("/api/workflow/select", {"name": "object-placement"})
    post("/api/test-source/scene", {"name": "2_rood_op_a"})
    time.sleep(1)  # The capture thread still holds a frame of the previous scene.
    post("/api/monitoring/start")
    check(page.contains("Vakken van het model", 90), "vakken verschijnen")
    check(page.wait("[...document.querySelectorAll('span')].filter(e => e.textContent.startsWith('Vakken van het model')).length === 2", 60), "vakken op beide camera's")
    found = state()["cameras"]
    print(json.dumps([c["detections"] for c in found], ensure_ascii=False), flush=True)
    page.screenshot(f"{shots}/vakken.png")
    post("/api/monitoring/stop")

    post("/api/cameras/1/roi", {"x": 0.1, "y": 0.2, "w": 0.6, "h": 0.6})
    post("/api/monitoring/start")
    check(page.contains("Vakken van het model", 90), "vakken verschijnen met een werkgebied")
    print(json.dumps(state()["cameras"][0]["detections"], ensure_ascii=False), flush=True)
    page.screenshot(f"{shots}/vakken-werkgebied.png")
    post("/api/monitoring/stop")
    post("/api/cameras/1/roi")
    check(page.wait("!document.body.innerText.includes('Vakken van het model')", 5), "vakken verdwijnen na stoppen")


def calibration(page: Page, shots: str) -> None:
    post("/api/test-source/scene", {"name": "2_rood_op_a"})
    time.sleep(1)
    post("/api/cameras/1/roi", {"x": 0.2, "y": 0.3, "w": 0.4, "h": 0.4})
    check(state()["cameras"][0]["calibrated_at"], "werkgebied tekenen bewaart een referentie")
    check(page.wait("!!document.querySelector('[aria-label^=\"Referentiebeeld Bovenaanzicht\"]')"), "knop referentiebeeld verschijnt")

    post("/api/test-source/scene", {"name": "2_rood_op_a_camera_verschoven"})
    time.sleep(1)
    post("/api/calibration/check")
    camera = state()["cameras"][0]
    print("na verschuiving:", camera["calibration"], camera["roi"], flush=True)
    check(camera["calibration"]["state"] == "corrected", "verschoven camera wordt herkend")
    check(abs(camera["roi"]["x"] - (0.2 + 70 / 1920)) < 0.02, "werkgebied schuift mee met de camera")
    check(page.contains("verschoven, gebieden meebewogen"), "melding staat op het beeld")
    check(page.contains("werkgebied en telgebied zijn meebewogen"), "verschuiving staat in de activiteit")
    page.eval("document.querySelector('[aria-label^=\"Referentiebeeld Bovenaanzicht\"]').click()")
    check(page.wait("[...document.images].some(i => i.src.includes('reference.jpg') && i.complete && i.naturalWidth > 0)"), "referentiebeeld ligt over het live beeld")
    page.screenshot(f"{shots}/kalibratie.png")
    page.eval("document.querySelector('[aria-label^=\"Referentiebeeld Bovenaanzicht\"]').click()")

    post("/api/test-source/scene", {"name": "2_rood_op_a"})
    time.sleep(1)
    post("/api/calibration/check")
    camera = state()["cameras"][0]
    check(camera["calibration"]["state"] == "ok" and abs(camera["roi"]["x"] - 0.2) < 0.005, "terug op zijn plek: werkgebied ook")
    post("/api/cameras/1/roi")


def mat(page: Page, shots: str) -> None:
    post("/api/test-source/scene", {"name": "werkmat_opbouw_1"})
    time.sleep(1)
    post("/api/calibration/check")
    check(page.contains("Werkmat gevonden: werkgebied automatisch"), "werkmat gevonden op het beeld")
    first = [camera["roi"] for camera in state()["cameras"]]
    check(all(first), f"beide camera's krijgen vanzelf een werkgebied: {first}")
    check(page.eval("document.querySelector('[aria-label^=\"Werkgebied Bovenaanzicht\"]').disabled"), "werkgebied tekenen staat uit zolang de mat het bepaalt")
    post("/api/cameras/1/count-area", {"x": first[0]["x"] + 0.05, "y": first[0]["y"] + 0.2, "w": 0.12, "h": 0.15})
    count_before = state()["cameras"][0]["count_area"]
    page.screenshot(f"{shots}/werkmat-1.png")

    post("/api/test-source/scene", {"name": "werkmat_opbouw_2"})
    time.sleep(1)
    post("/api/calibration/check")
    now = state()["cameras"]
    print("opbouw 1:", first, count_before, flush=True)
    print("opbouw 2:", [c["roi"] for c in now], now[0]["count_area"], flush=True)
    check(all(abs(a["x"] - b["roi"]["x"]) > 0.05 for a, b in zip(first, now)), "na opnieuw opbouwen staat het werkgebied op de nieuwe plek")
    check(abs(now[0]["count_area"]["x"] - count_before["x"]) > 0.05, "telgebied verhuist mee met de mat")
    check(page.contains("werkmat gevonden, werkgebied automatisch ingesteld"), "werkmat staat in de activiteit")
    page.screenshot(f"{shots}/werkmat-2.png")

    post("/api/test-source/scene", {"name": "2_rood_op_a"})
    time.sleep(1)
    for _ in range(3):
        post("/api/calibration/check")
    check(page.contains("Werkmat niet in beeld"), "melding als de mat weg is")
    post("/api/settings", {"auto_work_area": False})
    check(page.wait("!document.body.innerText.includes('Werkmat niet in beeld')"), "werkmat uitzetten haalt de melding weg")
    post("/api/cameras/1/count-area")
    post("/api/cameras/1/roi")
    post("/api/cameras/2/roi")


def run(page: Page, shots: str) -> None:
    check(page.contains("TESTBEELDEN"), "testbeelden staan zichtbaar gelabeld")
    mat(page, shots)
    calibration(page, shots)
    count_turns(page, shots)
    boxes(page, shots)
    post("/api/settings", {"auto_work_area": True})


if __name__ == "__main__":
    ui_check.run = run
    ui_check.main(sys.argv[1])
