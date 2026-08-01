"""Mark symbol detection (design/01 §7.2).

Lightweight CV-based detection for right-angle squares, equal-length ticks, and
parallel arrows. A YOLO hook is provided (try import ultralytics) but currently
falls back to template / morphology-based detection.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from ...config import ParserConfig
from ...logging_util import info, log_step
from ...types import Line, Mark, MarkType, Point


def _try_yolo(bgr: np.ndarray, weights: str):
    """Optional YOLO inference hook. Returns list of (cls_name, x, y, w, h) or None."""
    if not weights:
        return None
    try:
        from ultralytics import YOLO  # type: ignore
    except Exception:
        return None
    try:
        model = YOLO(weights)
        res = model(bgr, verbose=False)
        out = []
        for r in res:
            for b in r.boxes:
                cls_name = model.names[int(b.cls[0])]
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                out.append((cls_name, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1))
        return out
    except Exception:
        return None


def _find_right_angle_marks(binary: np.ndarray, lines: list[Line]) -> list[Mark]:
    """Detect small filled/square corners near line intersections.

    Heuristic: small square contours (4-vertex approx) with near-equal sides,
    located near a pair of perpendicular line endpoints.
    """
    marks: list[Mark] = []
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < 20 or area > 800:
            continue
        peri = float(cv2.arcLength(cnt, True))
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) != 4:
            continue
        x0, y0, w, h = cv2.boundingRect(approx)
        if w == 0 or h == 0:
            continue
        aspect = max(w, h) / min(w, h)
        if aspect > 1.6:
            continue
        cx, cy = x0 + w / 2.0, y0 + h / 2.0
        # find nearest perpendicular line pair endpoint
        best = _nearest_perp_vertex(cx, cy, lines, tol=25.0)
        if best is None:
            continue
        vertex_id, related = best
        marks.append(
            Mark(
                id=f"M_RA_{len(marks):03d}",
                type=MarkType.RIGHT_ANGLE,
                vertex=vertex_id,
                related=related,
                confidence=0.6,
            )
        )
    return marks


def _nearest_perp_vertex(
    cx: float, cy: float, lines: list[Line], tol: float
) -> Optional[tuple[str, list[str]]]:
    """Find a point where two perpendicular lines meet near (cx, cy).

    Returns (vertex_id_placeholder, [line_id, line_id]) or None. The vertex id
    is filled later by the Labeler (point id matching).
    """
    candidates: list[tuple[float, str, str]] = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            li, lj = lines[i], lines[j]
            if li.equation is None or lj.equation is None:
                continue
            d1 = (li.equation.b, -li.equation.a)
            d2 = (lj.equation.b, -lj.equation.a)
            na, nb = np.hypot(*d1), np.hypot(*d2)
            if na < 1e-9 or nb < 1e-9:
                continue
            cosang = abs((d1[0] * d2[0] + d1[1] * d2[1]) / (na * nb))
            angle = float(np.degrees(np.arccos(np.clip(cosang, -1, 1))))
            if not (87.0 <= angle <= 93.0):
                continue
            # find segment endpoint intersection near (cx, cy)
            for ep in (li.endpoints or []) + (lj.endpoints or []):
                d = float(np.hypot(ep[0] - cx, ep[1] - cy))
                if d < tol:
                    candidates.append((d, li.id, lj.id))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    _, la, lb = candidates[0]
    return ("", [la, lb])


def _find_equal_marks(binary: np.ndarray, lines: list[Line]) -> list[Mark]:
    """Detect short tick marks perpendicular to nearby line segments.

    Heuristic: small thin contours whose principal axis is perpendicular to a
    nearby line. Counts ticks per line for equal-length clustering.
    """
    marks: list[Mark] = []
    if not lines:
        return marks
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    line_ticks: dict[str, int] = {}
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < 5 or area > 80:
            continue
        if cnt.shape[0] < 2:
            continue
        pts = cnt.reshape(-1, 2).astype(np.float64)
        # principal axis via PCA
        mean = pts.mean(axis=0)
        centered = pts - mean
        cov = centered.T @ centered
        eigvals, eigvecs = np.linalg.eigh(cov)
        axis = eigvecs[:, -1]
        length = float(np.hypot(*(pts.max(axis=0) - pts.min(axis=0))))
        if length < 4 or length > 18:
            continue
        # find nearest line whose direction is ~perpendicular to this tick axis
        best_line: Optional[str] = None
        best_d = 15.0
        for ln in lines:
            if ln.endpoints is None:
                continue
            ld = (ln.endpoints[1][0] - ln.endpoints[0][0],
                  ln.endpoints[1][1] - ln.endpoints[0][1])
            ln_len = float(np.hypot(*ld))
            if ln_len < 1e-9:
                continue
            ld = (ld[0] / ln_len, ld[1] / ln_len)
            cosang = abs(ld[0] * axis[0] + ld[1] * axis[1])
            # perpendicular => cosang near 0
            if cosang > 0.4:
                continue
            # distance from tick center to line
            x1, y1 = ln.endpoints[0]
            a_, b_ = -ld[1], ld[0]
            c_ = -(a_ * x1 + b_ * y1)
            d = abs(a_ * mean[0] + b_ * mean[1] + c_)
            if d < best_d:
                best_d = d
                best_line = ln.id
        if best_line is None:
            continue
        line_ticks[best_line] = line_ticks.get(best_line, 0) + 1

    # group lines by tick count (same count => equal length)
    by_count: dict[int, list[str]] = {}
    for lid, c in line_ticks.items():
        by_count.setdefault(c, []).append(lid)
    for c, group in by_count.items():
        if len(group) < 2 or c == 0:
            continue
        mid = f"M_EQ_{len(marks):03d}"
        marks.append(
            Mark(
                id=mid,
                type=MarkType.EQUAL,
                related=group,
                count=c,
                confidence=0.55,
            )
        )
    return marks


class MarkDetector:
    """Detects right-angle / equal / parallel marks. YOLO optional, CV fallback."""

    def __init__(self, config: ParserConfig):
        self.config = config

    def detect(
        self,
        bgr: np.ndarray,
        binary: np.ndarray,
        lines: Optional[list[Line]] = None,
        points: Optional[list[Point]] = None,
    ) -> list[Mark]:
        lines = lines or []
        # try YOLO first
        yolo_res = _try_yolo(bgr, self.config.yolo_weights) if self.config.yolo_weights else None
        if yolo_res:
            return self._marks_from_yolo(yolo_res, points or [])
        marks: list[Mark] = []
        try:
            with log_step("perception.mark", "right_angle"):
                marks.extend(_find_right_angle_marks(binary, lines))
        except Exception as e:
            info("perception.mark", "right_angle_failed", error=repr(e))
        try:
            with log_step("perception.mark", "equal"):
                marks.extend(_find_equal_marks(binary, lines))
        except Exception as e:
            info("perception.mark", "equal_failed", error=repr(e))
        # parallel marks: deferred (template matching for arrows; not implemented)
        info("perception.mark", "done", count=len(marks))
        return marks

    def _marks_from_yolo(self, detections: list, points: list[Point]) -> list[Mark]:
        marks: list[Mark] = []
        for di, (cls, cx, cy, w, h) in enumerate(detections):
            t = {
                "right_angle": MarkType.RIGHT_ANGLE,
                "equal": MarkType.EQUAL,
                "parallel": MarkType.PARALLEL,
                "angle": MarkType.ANGLE,
            }.get(str(cls).lower())
            if t is None:
                continue
            vertex_id = None
            if t in (MarkType.RIGHT_ANGLE, MarkType.ANGLE) and points:
                nearest = min(
                    points,
                    key=lambda p: (p.coords[0] - cx) ** 2 + (p.coords[1] - cy) ** 2,
                )
                vertex_id = nearest.id
            marks.append(
                Mark(
                    id=f"M_YOLO_{di:03d}",
                    type=t,
                    vertex=vertex_id,
                    confidence=0.8,
                )
            )
        return marks
