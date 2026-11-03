"""Notices when a camera has moved since its areas were drawn, and moves the areas along.

Compares the live picture with a reference picture through image features (ORB), without
the model. Parts and hands in view change between the two, so only a consistent movement
of many points counts; anything less is reported as unknown rather than guessed.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .settings_store import Roi

WIDTH = 960
STILL = 0.01  # Shift as a share of the image width that counts as not moved.
MAX_SHIFT = 0.2  # Beyond this the areas would land somewhere else entirely.
MIN_INLIERS = 20
MIN_INLIER_SHARE = 0.25


@dataclass(frozen=True)
class Shift:
    matrix: np.ndarray  # reference pixels -> current pixels, both at WIDTH
    amount: float  # largest corner movement, as a share of the width
    inliers: int


def prepare(image: np.ndarray) -> np.ndarray:
    """Grayscale at a fixed width, so pictures of any resolution compare."""
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    return cv2.resize(gray, (WIDTH, round(height * WIDTH / width)), interpolation=cv2.INTER_AREA)


def measure(reference: np.ndarray, current: np.ndarray) -> Shift | None:
    """None when the two pictures cannot be matched reliably."""
    if reference.shape != current.shape:
        return None
    orb = cv2.ORB_create(1500)
    points_a, features_a = orb.detectAndCompute(reference, None)
    points_b, features_b = orb.detectAndCompute(current, None)
    if features_a is None or features_b is None or len(points_a) < MIN_INLIERS or len(points_b) < MIN_INLIERS:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(features_a, features_b, k=2)
    # Repeated shapes, like three identical marked squares, match equally well twice: drop those.
    good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance]
    if len(good) < MIN_INLIERS:
        return None
    source = np.float32([points_a[m.queryIdx].pt for m in good])
    target = np.float32([points_b[m.trainIdx].pt for m in good])
    matrix, mask = cv2.estimateAffinePartial2D(source, target, method=cv2.RANSAC, ransacReprojThreshold=4.0)
    if matrix is None:
        return None
    inliers = int(mask.sum())
    if inliers < MIN_INLIERS or inliers / len(good) < MIN_INLIER_SHARE:
        return None
    height, width = reference.shape
    corners = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    moved = cv2.transform(corners[None], matrix)[0]
    amount = float(np.linalg.norm(moved - corners, axis=1).max() / width)
    return Shift(matrix=matrix, amount=amount, inliers=inliers)


def move_area(area: Roi, shift: Shift, size: tuple[int, int]) -> Roi | None:
    """The area as it lies in the current picture, or None if it no longer fits in it."""
    width, height = size
    corners = np.float32(
        [
            [area.x * width, area.y * height],
            [(area.x + area.w) * width, area.y * height],
            [(area.x + area.w) * width, (area.y + area.h) * height],
            [area.x * width, (area.y + area.h) * height],
        ]
    )
    moved = cv2.transform(corners[None], shift.matrix)[0]
    left, top = max(0.0, moved[:, 0].min() / width), max(0.0, moved[:, 1].min() / height)
    right, bottom = min(1.0, moved[:, 0].max() / width), min(1.0, moved[:, 1].max() / height)
    try:
        return Roi(x=left, y=top, w=right - left, h=bottom - top)
    except ValueError:
        return None
