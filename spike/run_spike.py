"""Measure vision-model latency, schema validity and scene correctness via local Ollama.

Modes:
  matrix  fixed grid of model / scene / image width / camera count
  soak    one configuration repeated for N minutes, to expose thermal throttling
"""
import argparse
import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

OLLAMA = "http://localhost:11434/api/chat"
NUM_CTX = 8192
TIMEOUT_S = 240

STEP = "Place the red block inside the square marked A."
COMPLETION = "A red block lies inside the outlined square labelled A."

# Expected status per scene. dark_red_in_A may honestly be uncertain or completed.
EXPECTED = {
    "empty": {"incomplete"},
    "red_in_A": {"completed"},
    "red_in_B": {"incomplete"},
    "red_beside_A": {"incomplete"},
    "blue_in_A": {"incomplete"},
    "dark_red_in_A": {"uncertain"},
}

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "incomplete", "uncertain"]},
        "visible_objects": {"type": "array", "items": {"type": "string"}},
        "observed_relationships": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "string"},
        "uncertain": {"type": "boolean"},
    },
    "required": ["status", "visible_objects", "observed_relationships", "evidence", "uncertain"],
}

SYSTEM = (
    "You inspect camera images of a work area. Describe only what is visually observable. "
    "Do not guess about hidden objects. If the image does not allow a clear judgement, "
    'use status "uncertain". Respond with JSON only.'
)


# v2: the verdict comes last so the model states its evidence first, and each status is defined.
SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "visible_objects": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "observed_relationships": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "evidence": {"type": "string", "maxLength": 200},
        "status": {"type": "string", "enum": ["completed", "incomplete", "uncertain"]},
    },
    "required": ["visible_objects", "observed_relationships", "evidence", "status"],
}

SYSTEM_V2 = (
    "You inspect camera images of a work area. Describe only what is visually observable. "
    "Do not guess about hidden objects. Keep every list item under 8 words and evidence to one short sentence. "
    "Then choose status: "
    '"completed" = the image clearly shows the criterion is met. '
    '"incomplete" = the image is clear and shows the criterion is not met, for example a part is absent, '
    "in another position, or the wrong part. "
    '"uncertain" = the image is too dark, blocked or unclear to judge. '
    "A clear image of an unmet criterion is incomplete, not uncertain. Respond with JSON only."
)


def encode(path: Path, width: int, noise: float = 0.0) -> str:
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    img = cv2.resize(img, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    if noise:
        # Sensor-like noise makes every frame unique, so Ollama's image cache cannot hide encode time.
        jitter = np.random.default_rng().normal(0, noise, img.shape)
        img = np.clip(img.astype(np.float32) + jitter, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    return base64.b64encode(buf).decode()


def infer(model: str, images: list[str], thinking_capable: bool, v2: bool = False) -> dict:
    body = {
        "model": model,
        "stream": False,
        "format": SCHEMA_V2 if v2 else SCHEMA,
        "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": 300},
        "messages": [
            {"role": "system", "content": SYSTEM_V2 if v2 else SYSTEM},
            {
                "role": "user",
                "content": f"Current step: {STEP}\nCompletion criterion: {COMPLETION}\n"
                "Is the criterion satisfied in the image(s)?",
                "images": images,
            },
        ],
    }
    if thinking_capable:
        body["think"] = False
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"wall_s": round(time.perf_counter() - started, 2), "error": str(exc)}
    result = {
        "wall_s": round(time.perf_counter() - started, 2),
        "load_s": round(data.get("load_duration", 0) / 1e9, 2),
        "prompt_tokens": data.get("prompt_eval_count"),
        "prompt_s": round(data.get("prompt_eval_duration", 0) / 1e9, 2),
        "output_tokens": data.get("eval_count"),
        "eval_s": round(data.get("eval_duration", 0) / 1e9, 2),
        "done_reason": data.get("done_reason"),
    }
    raw = data.get("message", {}).get("content", "")
    try:
        parsed = json.loads(raw)
        result.update(schema_ok=True, status=parsed.get("status"), evidence=parsed.get("evidence"))
    except json.JSONDecodeError:
        result.update(schema_ok=False, raw=raw[:400])
    return result


def run_one(args, log, model: str, scene: str, width: int, cameras: int, rep: int) -> dict:
    paths = [args.scenes / f"{scene}_top.png"]
    if cameras == 2:
        paths.append(args.scenes / f"{scene}_side.png")
    images = [encode(p, width, args.noise) for p in paths]
    result = infer(model, images, thinking_capable=model == "qwen3-vl:8b", v2=args.v2)
    row = {"t": round(time.time()), "model": model, "scene": scene, "width": width, "cameras": cameras, "rep": rep}
    row.update(result)
    row["correct"] = result.get("status") in EXPECTED[scene]
    log.write(json.dumps(row) + "\n")
    log.flush()
    print(json.dumps({k: v for k, v in row.items() if k not in ("evidence", "t")}), flush=True)
    return row


def matrix(args, log) -> None:
    for model in args.models:
        for scene in EXPECTED:
            for rep in range(2):
                run_one(args, log, model, scene, 768, 1, rep)
        for scene in ("red_in_A", "red_in_B"):
            run_one(args, log, model, scene, 768, 2, 0)
            run_one(args, log, model, scene, 512, 1, 0)
            run_one(args, log, model, scene, 1024, 1, 0)


def soak(args, log) -> None:
    deadline = time.time() + args.minutes * 60
    scenes = list(EXPECTED)
    i = 0
    while time.time() < deadline:
        run_one(args, log, args.models[0], scenes[i % len(scenes)], args.width, args.cameras, i)
        i += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["matrix", "soak"])
    parser.add_argument("--scenes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=["qwen3-vl:4b-instruct", "qwen3-vl:8b"])
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--cameras", type=int, default=2)
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--v2", action="store_true", help="use the verdict-last prompt and schema")
    parser.add_argument("--noise", type=float, default=0.0, help="sensor-noise sigma, makes frames unique")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a") as log:
        {"matrix": matrix, "soak": soak}[args.mode](args, log)
