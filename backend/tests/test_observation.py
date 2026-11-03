import json

import numpy as np
import pytest

from app.frame_quality import FrameIssue, assess_frame
from app.observation import OLLAMA_FORMAT, InvalidObservation, ObservationStatus, ollama_format, parse_model_response


def valid(**overrides) -> dict:
    data = {
        "visible_objects": ["rood blok"],
        "observed_relationships": ["blok in vak A"],
        "evidence": "Het blok ligt in vak A.",
        "status": "completed",
    }
    return data | overrides


def test_valid_response_is_parsed():
    assert parse_model_response(json.dumps(valid())).status is ObservationStatus.COMPLETED


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "geen json",
        '{"status": "completed"',
        json.dumps(valid(status="done")),
        json.dumps(valid(evidence="")),
        json.dumps(valid(visible_objects=[])),
        json.dumps(valid(step_id="s9")),
        json.dumps({k: v for k, v in valid().items() if k != "status"}),
    ],
)
def test_unusable_responses_are_rejected(raw):
    with pytest.raises(InvalidObservation):
        parse_model_response(raw)


def test_truncated_response_is_rejected_even_if_it_parses():
    with pytest.raises(InvalidObservation):
        parse_model_response(json.dumps(valid()), done_reason="length")


def test_incomplete_may_list_no_objects():
    raw = json.dumps(valid(status="incomplete", visible_objects=[]))
    assert parse_model_response(raw).status is ObservationStatus.INCOMPLETE


def test_steps_without_deviations_keep_the_measured_schema():
    assert ollama_format([]) is OLLAMA_FORMAT


def test_deviation_field_comes_before_the_verdict():
    assert list(ollama_format(["fout"])["properties"])[-2:] == ["deviation", "status"]
    assert ollama_format(["fout"])["properties"]["deviation"]["enum"] == ["none", "fout"]


def test_named_deviation_is_parsed():
    raw = json.dumps(valid(status="incomplete", deviation="fout"))
    assert parse_model_response(raw, allowed_deviations=("fout",)).named_deviation == "fout"


def test_none_is_not_a_deviation():
    raw = json.dumps(valid(status="incomplete", deviation="none"))
    assert parse_model_response(raw, allowed_deviations=("fout",)).named_deviation is None


def test_invented_deviation_is_rejected():
    with pytest.raises(InvalidObservation):
        parse_model_response(json.dumps(valid(status="incomplete", deviation="verzonnen")))


def test_completed_with_a_deviation_is_inconsistent():
    with pytest.raises(InvalidObservation):
        parse_model_response(json.dumps(valid(deviation="fout")), allowed_deviations=("fout",))


def noisy(level: int) -> np.ndarray:
    noise = np.random.default_rng(1).integers(-30, 30, (120, 160, 3))
    return np.clip(level + noise, 0, 255).astype(np.uint8)


def test_normal_frame_has_no_issue():
    assert assess_frame(noisy(130)) is None


def test_dark_frame_is_flagged():
    assert assess_frame(noisy(130) // 16) is FrameIssue.TOO_DARK


def test_bright_frame_is_flagged():
    assert assess_frame(np.full((120, 160, 3), 250, np.uint8)) is FrameIssue.TOO_BRIGHT


def test_flat_frame_is_flagged():
    assert assess_frame(np.full((120, 160, 3), 128, np.uint8)) is FrameIssue.NO_DETAIL


def test_detections_become_fractions_and_impossible_boxes_are_dropped():
    from app.observation import parse_detections

    raw = json.dumps(
        {
            "objects": [
                {"label": "rood blok", "box_2d": [250, 400, 350, 600]},
                {"label": "groen blok", "box_2d": [0, 0, 0, 0]},
                {"label": "omgekeerd", "box_2d": [500, 500, 400, 600]},
                {"label": "buiten beeld", "box_2d": [900, 100, 1200, 300]},
                {"label": "alles", "box_2d": [0, 0, 1000, 1000]},
                {"label": "", "box_2d": [100, 100, 200, 200]},
                {"label": "te kort", "box_2d": [100, 100]},
            ]
        }
    )
    found = parse_detections(raw)
    assert [box.label for box in found] == ["rood blok"]
    assert (found[0].x, found[0].y, found[0].w, found[0].h) == pytest.approx((0.25, 0.4, 0.1, 0.2))


@pytest.mark.parametrize("raw", ["", "{", "[]", '{"objects": 3}', '{"objects": [3]}'])
def test_a_bad_detection_answer_gives_no_boxes(raw):
    from app.observation import parse_detections

    assert parse_detections(raw) == []


def test_a_cut_off_detection_answer_gives_no_boxes():
    from app.observation import parse_detections

    assert parse_detections('{"objects": []}', "length") == []
