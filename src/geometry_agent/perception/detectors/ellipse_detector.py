"""Ellipse detection (design/02 §4).

Mask + contour + cv2.fitEllipse (Fitzgibbon) + RANSAC + foci / eccentricity.
Contours that are nearly circular (semi_major/semi_minor < 1.05) are skipped
(circle detector owns them).
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from ...config import ParserConfig
from ...logging_util import info, log_step
from ...types import Ellipse
from ..fitting import (
    EllipseFit,
    confidence_from_residual,
    ellipse_foci,
    fit_ellipse_fitzgibbon,
    fit_ellipse_ransac,
)

CIRCLE_RATIO = 1.08  # if a/b < this, treat as circle (skip)


def _contour_points(cnt: np.ndarray) -> np.ndarray:
    return cnt.reshape(-1, 2).astype(np.float64)


class EllipseDetector:
    """Contour-based ellipse detection with Fitzgibbon + RANSAC."""

    def __init__(self, config: ParserConfig):
        self.config = config

    def detect(
        self,
        binary_clean: np.ndarray,
        min_size: float = 12.0,
        ransac_threshold_px: float = 2.5,
    ) -> list[Ellipse]:
        contours, _ = cv2.findContours(
            binary_clean, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
        )
        ellipses: list[Ellipse] = []
        for ei, cnt in enumerate(contours):
            if cnt.shape[0] < 5:
                continue
            x0, y0, w, h = cv2.boundingRect(cnt)
            if min(w, h) < min_size:
                continue
            pts = _contour_points(cnt)
            with log_step("perception.ellipse", "fit", contour_pts=int(pts.shape[0])):
                fit: Optional[EllipseFit] = fit_ellipse_fitzgibbon(pts)
                if fit is None:
                    continue
                # RANSAC robust path if residual large
                if fit.residual > 1.5:
                    cand = fit_ellipse_ransac(
                        pts, threshold_px=ransac_threshold_px, max_iters=60
                    )
                    if cand is not None and cand.residual <= fit.residual:
                        fit = cand
            if fit is None:
                continue
            # skip near-circles (let circle detector own them)
            if fit.semi_minor <= 0 or fit.semi_major / fit.semi_minor < CIRCLE_RATIO:
                continue
            foci, ecc = ellipse_foci(fit)
            tol = max(2.0, 0.03 * fit.semi_major)
            conf = confidence_from_residual(fit.residual, tol)
            ellipses.append(
                Ellipse(
                    id=f"E_{ei:03d}",
                    center=(float(fit.cx), float(fit.cy)),
                    semi_major=float(fit.semi_major),
                    semi_minor=float(fit.semi_minor),
                    rotation=float(fit.rotation),
                    foci=[(float(f[0]), float(f[1])) for f in foci],
                    eccentricity=float(ecc),
                    fit_residual=float(fit.residual),
                    confidence=float(max(0.0, min(1.0, conf))),
                )
            )
        info("perception.ellipse", "done", count=len(ellipses))
        return ellipses
