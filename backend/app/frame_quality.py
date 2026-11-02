"""Cheap image checks that run before inference.

In the spike qwen3-vl:4b-instruct called a nearly black image "clearly" completed, so
unusable frames must be stopped here rather than left to the model.
"""
from enum import StrEnum

import cv2
import numpy as np

MIN_MEAN_LUMA = 35.0
MAX_MEAN_LUMA = 235.0
MIN_LUMA_STDDEV = 6.0


class FrameIssue(StrEnum):
    TOO_DARK = "too_dark"
    TOO_BRIGHT = "too_bright"
    NO_DETAIL = "no_detail"


def assess_frame(frame: np.ndarray) -> FrameIssue | None:
    luma = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean = float(luma.mean())
    if mean < MIN_MEAN_LUMA:
        return FrameIssue.TOO_DARK
    if mean > MAX_MEAN_LUMA:
        return FrameIssue.TOO_BRIGHT
    if float(luma.std()) < MIN_LUMA_STDDEV:
        return FrameIssue.NO_DETAIL
    return None
