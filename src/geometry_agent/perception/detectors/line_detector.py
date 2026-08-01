"""Line / segment detection (design/02 §2).

LSD as primary, HoughP as fallback补, collinear segment merging, least-squares
equation fitting, endpoint snapping to known points.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from ...config import ParserConfig
from ...logging_util import info, log_step
from ...types import Line, LineEquation, LineType, Point
from ..fitting import fit_line, line_direction_angle_deg

MERGE_ANGLE_DEG = 3.0
MERGE_DIST_PX_FACTOR = 0.01  # 1% of line length
SNAP_DIST_PX = 5.0


def _lsd_segments(binary: np.ndarray) -> np.ndarray:
    """Run cv2 LineSegmentDetector. Returns (N, 5) [x1,y1,x2,y2,width] or empty.

    Handles both cv4 (returns (lines, _, _)) and cv5 (returns 4-tuple) signatures,
    and both (N,1,5)/(N,4)/(N,5) line array shapes.
    """
    try:
        lsd = cv2.createLineSegmentDetector()
        ret = lsd.detect(binary)
    except Exception:
        return np.zeros((0, 5), dtype=np.float32)
    lines = None
    if isinstance(ret, tuple) and len(ret) > 0:
        lines = ret[0]
    else:
        lines = ret
    if lines is None:
        return np.zeros((0, 5), dtype=np.float32)
    arr = np.asarray(lines).reshape(-1, 4 if np.asarray(lines).shape[-1] == 4 else 5)
    if arr.shape[1] == 4:
        arr = np.hstack([arr, np.ones((arr.shape[0], 1), dtype=arr.dtype)])  # width=1
    return arr.astype(np.float32)


def _hough_segments(binary: np.ndarray, min_len: int = 25) -> np.ndarray:
    lines = cv2.HoughLinesP(binary, 1, np.pi / 180, 40, minLineLength=min_len, maxLineGap=8)
    if lines is None:
        return np.zeros((0, 5), dtype=np.float32)
    arr = np.asarray(lines).reshape(-1, 4)
    out = np.hstack([arr, np.ones((arr.shape[0], 1), dtype=arr.dtype)])
    return out.astype(np.float32)


def _seg_len(s: np.ndarray) -> float:
    return float(np.hypot(s[2] - s[0], s[3] - s[1]))


def _seg_dir(s: np.ndarray) -> tuple[float, float]:
    dx, dy = s[2] - s[0], s[3] - s[1]
    n = float(np.hypot(dx, dy))
    if n < 1e-9:
        return (1.0, 0.0)
    return (dx / n, dy / n)


def _point_seg_distance(p: np.ndarray, s: np.ndarray) -> float:
    """Perpendicular distance from p to the infinite line through segment s."""
    x1, y1, x2, y2 = s[0], s[1], s[2], s[3]
    dx, dy = x2 - x1, y2 - y1
    n = float(np.hypot(dx, dy))
    if n < 1e-9:
        return float(np.hypot(p[0] - x1, p[1] - y1))
    # |cross| / n
    return float(abs((p[0] - x1) * dy - (p[1] - y1) * dx) / n)


def _projection_param(p: np.ndarray, s: np.ndarray) -> float:
    """Projection of p onto segment direction, parameter in [0, len]."""
    x1, y1 = s[0], s[1]
    dx, dy = s[2] - x1, s[3] - y1
    n = float(np.hypot(dx, dy))
    if n < 1e-9:
        return 0.0
    return ((p[0] - x1) * dx + (p[1] - y1) * dy) / n


def _merge_collinear(segs: np.ndarray) -> np.ndarray:
    """Greedy merge of collinear / overlapping segments. segs: (N, 5)."""
    if segs.shape[0] == 0:
        return segs
    # sort by length desc so we anchor on the longest
    order = np.argsort([-_seg_len(s) for s in segs])
    segs = segs[order]
    merged: list[np.ndarray] = []
    used = np.zeros(segs.shape[0], dtype=bool)
    for i in range(segs.shape[0]):
        if used[i]:
            continue
        cur = segs[i].copy()
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j in range(segs.shape[0]):
                if used[j]:
                    continue
                cand = segs[j]
                # direction match
                d1 = _seg_dir(cur)
                d2 = _seg_dir(cand)
                if line_direction_angle_deg(d1, d2) > MERGE_ANGLE_DEG:
                    continue
                # collinearity: both endpoints of cand near cur's infinite line
                tol = max(2.0, MERGE_DIST_PX_FACTOR * _seg_len(cur))
                if _point_seg_distance(cand[:2], cur) > tol and _point_seg_distance(cand[2:4], cur) > tol:
                    continue
                # projection overlap or adjacency
                t1 = _projection_param(cand[:2], cur)
                t2 = _projection_param(cand[2:4], cur)
                L = _seg_len(cur)
                gap = max(0.0, min(t1, t2) - L, -max(t1, t2))
                if gap > 8.0:  # too far apart along direction
                    continue
                # merge: take farthest two endpoints among the 4
                pts = np.array([cur[:2], cur[2:4], cand[:2], cand[2:4]])
                # project onto direction
                d = np.array(d1)
                proj = pts @ d
                i_min, i_max = int(np.argmin(proj)), int(np.argmax(proj))
                cur = np.array(
                    [pts[i_min, 0], pts[i_min, 1], pts[i_max, 0], pts[i_max, 1], cur[4]],
                    dtype=np.float32,
                )
                used[j] = True
                changed = True
        merged.append(cur)
    return np.asarray(merged, dtype=np.float32)


def _rasterize_segment(s: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Pixel coordinates along a segment (for least-squares fit)."""
    x1, y1, x2, y2 = int(s[0]), int(s[1]), int(s[2]), int(s[3])
    n = max(2, int(_seg_len(s)))
    xs = np.linspace(x1, x2, n)
    ys = np.linspace(y1, y2, n)
    return np.stack([xs, ys], axis=1)


def _snap_endpoint(p: np.ndarray, points: Optional[list[Point]], tol: float = SNAP_DIST_PX) -> tuple[float, float]:
    if not points:
        return (float(p[0]), float(p[1]))
    best = None
    best_d = tol
    for pt in points:
        d = float(np.hypot(pt.coords[0] - p[0], pt.coords[1] - p[1]))
        if d < best_d:
            best_d = d
            best = pt
    if best is not None:
        return best.coords
    return (float(p[0]), float(p[1]))


class LineDetector:
    """LSD + HoughP + collinear merge + least-squares equation fit."""

    def __init__(self, config: ParserConfig):
        self.config = config

    def detect(
        self,
        binary_clean: np.ndarray,
        points: Optional[list[Point]] = None,
        min_length_px: float = 15.0,
    ) -> list[Line]:
        with log_step("perception.line", "lsd"):
            segs = _lsd_segments(binary_clean)
        with log_step("perception.line", "hough"):
            hough = _hough_segments(binary_clean)
        if segs.shape[0] == 0 and hough.shape[0] > 0:
            segs = hough
        elif hough.shape[0] > 0:
            # only keep Hough lines not already covered by LSD
            segs = np.concatenate([segs, hough], axis=0)

        with log_step("perception.line", "merge", n_in=int(segs.shape[0])):
            segs = _merge_collinear(segs)

        lines: list[Line] = []
        H, W = binary_clean.shape
        for idx, s in enumerate(segs):
            if _seg_len(s) < min_length_px:
                continue
            pts = _rasterize_segment(s, (H, W))
            fit = fit_line(pts)
            if fit is None:
                continue
            p1 = _snap_endpoint(s[:2], points)
            p2 = _snap_endpoint(s[2:4], points)
            length = float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
            tol = max(2.0, 0.03 * length)
            conf = float(max(0.0, 1.0 - fit.residual / tol))
            lines.append(
                Line(
                    id=f"L_{idx:03d}",
                    type=LineType.SEGMENT,
                    endpoints=[p1, p2],
                    equation=LineEquation(a=fit.a, b=fit.b, c=fit.c),
                    length=length,
                    confidence=conf,
                )
            )
        info("perception.line", "done", count=len(lines))
        return lines
