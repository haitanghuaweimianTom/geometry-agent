"""Point detection (design/02 §1).

Sources: Shi-Tomasi corners + skeleton endpoints + analytic line/line, line/circle,
circle/circle intersections. Subpixel refinement via cornerSubPix.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from ...config import ParserConfig
from ...logging_util import info, log_step
from ...types import Circle, Line, Point, PointSource
from ..fitting import refine_corners_subpixel

MERGE_DIST_PX = 3.0


def _skeleton_endpoints(skeleton: np.ndarray) -> np.ndarray:
    """Pixels of a 1px skeleton with exactly one white 8-neighbor (or isolated)."""
    sk = (skeleton > 0).astype(np.uint8)
    if sk.sum() == 0:
        return np.zeros((0, 2), dtype=np.float32)
    # count white neighbors per pixel via convolution
    k = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)
    cnt = cv2.filter2D(sk, -1, k, borderType=cv2.BORDER_CONSTANT)
    # only consider skeleton pixels; endpoints have neighbor count == 1,
    # isolated pixels have count == 0
    endpoint_mask = (sk > 0) & ((cnt == 1) | (cnt == 0))
    ys, xs = np.where(endpoint_mask)
    return np.stack([xs, ys], axis=1).astype(np.float32)


def _nms_points(pts: np.ndarray, min_dist: float = MERGE_DIST_PX) -> np.ndarray:
    if pts.shape[0] == 0:
        return pts
    keep: list[int] = []
    order = np.arange(pts.shape[0])
    used = np.zeros(pts.shape[0], dtype=bool)
    for i in order:
        if used[i]:
            continue
        keep.append(i)
        d = np.hypot(pts[:, 0] - pts[i, 0], pts[:, 1] - pts[i, 1])
        used = used | (d < min_dist)
    return pts[keep]


def _line_line_intersections(lines: list[Line]) -> np.ndarray:
    pts: list[list[float]] = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            li, lj = lines[i], lines[j]
            if li.equation is None or lj.equation is None:
                continue
            a1, b1, c1 = li.equation.a, li.equation.b, li.equation.c
            a2, b2, c2 = lj.equation.a, lj.equation.b, lj.equation.c
            det = a1 * b2 - a2 * b1
            if abs(det) < 1e-9:
                continue
            x = (b1 * c2 - b2 * c1) / det
            y = (c1 * a2 - c2 * a1) / det
            # only keep if within both segments' bounding boxes (with margin)
            def in_seg(x, y, seg: Line, margin: float = 5.0) -> bool:
                if not seg.endpoints:
                    return True
                xs = [p[0] for p in seg.endpoints]
                ys = [p[1] for p in seg.endpoints]
                return (
                    min(xs) - margin <= x <= max(xs) + margin
                    and min(ys) - margin <= y <= max(ys) + margin
                )
            if in_seg(x, y, li) and in_seg(x, y, lj):
                pts.append([x, y])
    return np.asarray(pts, dtype=np.float64).reshape(-1, 2)


def _line_circle_intersections(lines: list[Line], circles: list[Circle]) -> np.ndarray:
    pts: list[list[float]] = []
    for line in lines:
        if line.equation is None:
            continue
        a, b, c = line.equation.a, line.equation.b, line.equation.c
        for circ in circles:
            cx, cy, r = circ.center[0], circ.center[1], circ.radius
            # signed distance from center to line
            d = a * cx + b * cy + c
            if abs(d) > r + 1e-6:
                continue
            # foot of perpendicular
            fx = cx - a * d
            fy = cy - b * d
            dd = r * r - d * d
            if dd < 0:
                dd = 0.0
            off = float(np.sqrt(dd))
            p1 = (fx + b * off, fy - a * off)
            p2 = (fx - b * off, fy + a * off)
            for p in (p1, p2):
                if line.endpoints:
                    xs = [q[0] for q in line.endpoints]
                    ys = [q[1] for q in line.endpoints]
                    if not (
                        min(xs) - 5 <= p[0] <= max(xs) + 5
                        and min(ys) - 5 <= p[1] <= max(ys) + 5
                    ):
                        continue
                pts.append([p[0], p[1]])
    return np.asarray(pts, dtype=np.float64).reshape(-1, 2)


def _circle_circle_intersections(circles: list[Circle]) -> np.ndarray:
    pts: list[list[float]] = []
    for i in range(len(circles)):
        for j in range(i + 1, len(circles)):
            c1, c2 = circles[i], circles[j]
            x1, y1, r1 = c1.center[0], c1.center[1], c1.radius
            x2, y2, r2 = c2.center[0], c2.center[1], c2.radius
            dx, dy = x2 - x1, y2 - y1
            d = float(np.hypot(dx, dy))
            if d < 1e-9 or d > r1 + r2 or d < abs(r1 - r2):
                continue
            a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
            h2 = r1 * r1 - a * a
            if h2 < 0:
                continue
            h = float(np.sqrt(h2))
            px = x1 + a * dx / d
            py = y1 + a * dy / d
            pts.append([px + h * dy / d, py - h * dx / d])
            pts.append([px - h * dy / d, py + h * dx / d])
    return np.asarray(pts, dtype=np.float64).reshape(-1, 2)


class PointDetector:
    """Detects points from corners, skeleton endpoints, and analytic intersections."""

    def __init__(self, config: ParserConfig):
        self.config = config

    def detect(
        self,
        gray: np.ndarray,
        binary_clean: np.ndarray,
        skeleton: np.ndarray,
        lines: Optional[list[Line]] = None,
        circles: Optional[list[Circle]] = None,
        max_corners: int = 300,
    ) -> list[Point]:
        all_pts: list[np.ndarray] = []

        # 1. Shi-Tomasi corners
        try:
            with log_step("perception.point", "shi_tomasi"):
                corners = cv2.goodFeaturesToTrack(
                    binary_clean, max_corners, 0.05, 8.0, blockSize=7
                )
            if corners is not None and len(corners) > 0:
                refined = refine_corners_subpixel(gray, corners)
                all_pts.append(refined.astype(np.float64))
        except Exception as e:
            info("perception.point", "shi_tomasi_failed", error=repr(e))

        # 2. Skeleton endpoints
        try:
            with log_step("perception.point", "skeleton_endpoints"):
                ends = _skeleton_endpoints(skeleton)
            if ends.shape[0] > 0:
                all_pts.append(ends.astype(np.float64))
        except Exception as e:
            info("perception.point", "endpoints_failed", error=repr(e))

        # 3. Analytic intersections补全
        try:
            with log_step("perception.point", "intersections", lines=len(lines or []), circles=len(circles or [])):
                ll = _line_line_intersections(lines or [])
                lc = _line_circle_intersections(lines or [], circles or [])
                cc = _circle_circle_intersections(circles or [])
                for arr in (ll, lc, cc):
                    if arr.shape[0] > 0:
                        all_pts.append(arr)
        except Exception as e:
            info("perception.point", "intersection_failed", error=repr(e))

        if not all_pts:
            return []

        combined = np.concatenate(all_pts, axis=0)
        combined = _nms_points(combined, MERGE_DIST_PX)

        # clip to image bounds
        H, W = gray.shape
        mask = (
            (combined[:, 0] >= 0)
            & (combined[:, 0] < W)
            & (combined[:, 1] >= 0)
            & (combined[:, 1] < H)
        )
        combined = combined[mask]

        points: list[Point] = []
        for i, (x, y) in enumerate(combined):
            src = PointSource.CORNER
            points.append(
                Point(
                    id=f"P_{i:03d}",
                    coords=(float(x), float(y)),
                    confidence=0.9,
                    source=src,
                    subpixel=True,
                )
            )
        return points
