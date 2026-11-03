"""A printed work mat with four markers, so each camera finds the work area by itself.

The setup is often taken down and rebuilt, after which no reference picture matches any
more. The markers do not depend on where a camera stands: every check finds them anew.
Areas are kept in mat coordinates (0..1 between the outer marker corners), so they land on
the same spot of the mat whatever the camera angle. Print scale does not matter.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .settings_store import Roi

DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
CORNER_IDS = (0, 1, 2, 3)  # top left, top right, bottom right, bottom left
MIN_MARKERS = 3  # a hand on one corner must not lose the mat
MARGIN = 0.02  # around the mat, as a share of the image

# Layout in millimetres, A4 landscape.
MAT_W, MAT_H = 297.0, 210.0
EDGE, MARKER = 10.0, 40.0
SLOT = 45.0
SLOTS_MM = {"A": (88.0, 120.0), "B": (148.5, 120.0), "C": (209.0, 120.0)}


@dataclass(frozen=True)
class MatView:
    homography: np.ndarray  # mat coordinates (0..1) -> image pixels
    markers: int


def _marker_corners_mat() -> dict[int, np.ndarray]:
    """Outer corners of each marker in mat coordinates, in OpenCV's corner order."""
    span_w, span_h = MAT_W - 2 * EDGE, MAT_H - 2 * EDGE
    size_u, size_v = MARKER / span_w, MARKER / span_h
    origins = {0: (0.0, 0.0), 1: (1 - size_u, 0.0), 2: (1 - size_u, 1 - size_v), 3: (0.0, 1 - size_v)}
    return {
        marker: np.float32([[u, v], [u + size_u, v], [u + size_u, v + size_v], [u, v + size_v]])
        for marker, (u, v) in origins.items()
    }


MARKER_CORNERS = _marker_corners_mat()


def render(dpi: int = 200) -> np.ndarray:
    """The printable mat as a white A4 page."""
    scale = dpi / 25.4
    page = np.full((round(MAT_H * scale), round(MAT_W * scale)), 255, np.uint8)
    px = lambda mm: round(mm * scale)
    positions = {0: (EDGE, EDGE), 1: (MAT_W - EDGE - MARKER, EDGE), 2: (MAT_W - EDGE - MARKER, MAT_H - EDGE - MARKER), 3: (EDGE, MAT_H - EDGE - MARKER)}
    for marker, (x, y) in positions.items():
        image = cv2.aruco.generateImageMarker(DICTIONARY, marker, px(MARKER))
        page[px(y) : px(y) + image.shape[0], px(x) : px(x) + image.shape[1]] = image
    for name, (x, y) in SLOTS_MM.items():
        half = SLOT / 2
        cv2.rectangle(page, (px(x - half), px(y - half)), (px(x + half), px(y + half)), 0, max(2, px(1.2)))
        cv2.putText(page, name, (px(x - 4), px(y - half - 5)), cv2.FONT_HERSHEY_SIMPLEX, scale * 0.35, 0, max(2, px(0.8)), cv2.LINE_AA)
    label = "AssemblyVision werkmat - op elk formaat te printen, markers niet afdekken"
    cv2.putText(page, label, (px(EDGE + MARKER + 6), px(EDGE + 6)), cv2.FONT_HERSHEY_SIMPLEX, scale * 0.12, 90, max(1, px(0.3)), cv2.LINE_AA)
    return page


def locate(image: np.ndarray) -> MatView | None:
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = cv2.aruco.ArucoDetector(DICTIONARY, cv2.aruco.DetectorParameters()).detectMarkers(gray)
    if ids is None:
        return None
    found = {int(marker): points[0] for marker, points in zip(ids.flatten(), corners) if int(marker) in CORNER_IDS}
    if len(found) < MIN_MARKERS:
        return None
    source = np.concatenate([MARKER_CORNERS[marker] for marker in found])
    target = np.concatenate([found[marker] for marker in found]).astype(np.float32)
    homography, _ = cv2.findHomography(source, target, cv2.RANSAC, 5.0)
    if homography is None:
        return None
    return MatView(homography=homography, markers=len(found))


def _bounds(points: np.ndarray, width: int, height: int, margin: float) -> Roi | None:
    left = max(0.0, points[:, 0].min() / width - margin)
    top = max(0.0, points[:, 1].min() / height - margin)
    right = min(1.0, points[:, 0].max() / width + margin)
    bottom = min(1.0, points[:, 1].max() / height + margin)
    try:
        return Roi(x=left, y=top, w=right - left, h=bottom - top)
    except ValueError:
        return None


def _rectangle(x: float, y: float, w: float, h: float) -> np.ndarray:
    return np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


def mat_area(view: MatView, size: tuple[int, int]) -> Roi | None:
    """The whole mat as a work area in the image."""
    points = cv2.perspectiveTransform(_rectangle(0, 0, 1, 1)[None], view.homography)[0]
    return _bounds(points, *size, MARGIN)


def to_image(view: MatView, area: Roi, size: tuple[int, int]) -> Roi | None:
    """An area stored in mat coordinates, as it lies in this image."""
    points = cv2.perspectiveTransform(_rectangle(area.x, area.y, area.w, area.h)[None], view.homography)[0]
    return _bounds(points, *size, 0.0)


def to_mat(view: MatView, area: Roi, size: tuple[int, int]) -> Roi | None:
    """An area drawn on the image, in mat coordinates."""
    width, height = size
    corners = _rectangle(area.x * width, area.y * height, area.w * width, area.h * height)
    points = cv2.perspectiveTransform(corners[None], np.linalg.inv(view.homography))[0]
    return _bounds(points, 1, 1, 0.0)
