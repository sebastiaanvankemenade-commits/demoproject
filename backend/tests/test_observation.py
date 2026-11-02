import json

import numpy as np
import pytest

from app.frame_quality import FrameIssue, assess_frame
from app.observation import InvalidObservation, ObservationStatus, parse_model_response


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
