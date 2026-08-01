"""Circle / arc detection (design/02 §3).

Mask + findContours + Kasa algebraic fit + LM geometric refinement + coverage
(全圆 / arc)判定. Foreground=255.
"""
from __future__ import annotations

import cv2
import numpy as np

from ...config import ParserConfig
from ...logging_util import info
from ...types import Circle
from ..fitting import (
    circle_coverage,
    confidence_from_residual,
    fit_circle_kasa,
    fit_circle_lm,
)


def _circularity(contour: np.ndarray) -> float:
    area = float(cv2.contourArea(contour))
    perim = float(cv2.arcLength(contour, True))
    if perim <= 0:
        return 0.0
    return float(4 * np.pi * area / (perim * perim))


def _contour_is_closed_curve(contour: np.ndarray, min_pts: int = 12) -> bool:
    return contour.shape[0] >= min_pts


class CircleDetector:
    """Contour-based circle detection with Kasa + LM refinement."""

    def __init__(self, config: ParserConfig):
        self.config = config

    def detect(
        self,
        binary_clean: np.ndarray,
        min_radius: float = 8.0,
        max_residual_ratio: float = 0.05,
    ) -> list[Circle]:
        contours, _ = cv2.findContours(
            binary_clean, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
        )
        circles: list[Circle] = []
        for ci, cnt in enumerate(contours):
            if not _contour_is_closed_curve(cnt):
                continue
            pts = cnt.reshape(-1, 2).astype(np.float64)
            # quick filter: bounding box size
            x0, y0, w, h = cv2.boundingRect(cnt)
            if min(w, h) < 2 * min_radius:
                continue
            kasa = fit_circle_kasa(pts)
            if kasa is None or kasa.r < min_radius:
                continue
            lm = fit_circle_lm(pts, kasa)
            fit = lm if lm.residual < kasa.residual else kasa
            if fit.r < min_radius:
                continue
            coverage, arc = circle_coverage(pts, fit.cx, fit.cy)
            # residual gate
            ratio = fit.residual / fit.r if fit.r > 0 else 1.0
            tol = max(2.0, 0.03 * fit.r)
            conf = confidence_from_residual(fit.residual, tol)
            if conf < 0.05 and ratio > max_residual_ratio:
                continue
            circles.append(
                Circle(
                    id=f"C_{ci:03d}",
                    center=(float(fit.cx), float(fit.cy)),
                    radius=float(fit.r),
                    fit_residual=float(fit.residual),
                    coverage=float(coverage),
                    arc_range=arc,
                    confidence=float(max(0.0, min(1.0, conf))),
                )
            )
        info("perception.circle", "done", count=len(circles))
        return circles
