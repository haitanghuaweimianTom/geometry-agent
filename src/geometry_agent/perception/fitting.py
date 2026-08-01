"""Geometric fitting primitives (design/02-Detection-Algorithms.md).

Pure-numpy/scipy/cv2 functions returning parameters + residuals. No schema
types here; callers wrap results into types.py models.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from scipy.optimize import least_squares


# ---------- line fitting ----------

@dataclass
class LineFit:
    a: float
    b: float
    c: float
    residual: float
    direction: tuple[float, float]  # unit direction vector (b, -a)


def fit_line(points: np.ndarray) -> Optional[LineFit]:
    """Least-squares line ax+by+c=0 with a^2+b^2=1 via covariance eigenvector.

    points: (N, 2) array of (x, y). Returns None if degenerate.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 2:
        return None
    mean = pts.mean(axis=0)
    centered = pts - mean
    cov = centered.T @ centered
    try:
        eigvals, eigvecs = np.linalg.eigh(cov)
    except np.linalg.LinAlgError:
        return None
    # smallest eigenvalue -> normal vector (a, b)
    normal = eigvecs[:, 0]
    a, b = float(normal[0]), float(normal[1])
    norm = float(np.hypot(a, b))
    if norm < 1e-12:
        return None
    a, b = a / norm, b / norm
    c = -(a * float(mean[0]) + b * float(mean[1]))
    # residual: RMS perpendicular distance
    dists = a * pts[:, 0] + b * pts[:, 1] + c
    residual = float(np.sqrt(np.mean(dists ** 2))) if dists.size else 0.0
    direction = (b, -a)
    return LineFit(a=a, b=b, c=c, residual=residual, direction=direction)


def point_line_distance(p: np.ndarray, line: LineFit) -> np.ndarray:
    """Perpendicular distance from point(s) to a line."""
    p = np.asarray(p, dtype=np.float64)
    return np.abs(line.a * p[..., 0] + line.b * p[..., 1] + line.c)


def line_direction_angle_deg(v1: tuple[float, float], v2: tuple[float, float]) -> float:
    """Acute angle (deg) between two direction vectors, in [0, 90]."""
    a = np.asarray(v1, dtype=np.float64)
    b = np.asarray(v2, dtype=np.float64)
    na, nb = np.hypot(*a), np.hypot(*b)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    cos = float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))
    ang = float(np.degrees(np.arccos(np.abs(cos))))
    return min(ang, 180.0 - ang)


# ---------- circle fitting ----------

@dataclass
class CircleFit:
    cx: float
    cy: float
    r: float
    residual: float


def fit_circle_kasa(points: np.ndarray) -> Optional[CircleFit]:
    """Algebraic (Kasa) circle fit. points: (N, 2). Returns None if degenerate."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 3:
        return None
    x = pts[:, 0]
    y = pts[:, 1]
    x2 = x * x
    y2 = y * y
    M = np.array(
        [
            [x2.sum(), (x * y).sum(), x.sum()],
            [(x * y).sum(), y2.sum(), y.sum()],
            [x.sum(), y.sum(), float(pts.shape[0])],
        ]
    )
    rhs = -np.array([(x * (x2 + y2)).sum(), (y * (x2 + y2)).sum(), (x2 + y2).sum()])
    try:
        D, E, F = np.linalg.solve(M, rhs)
    except np.linalg.LinAlgError:
        return None
    cx, cy = -D / 2.0, -E / 2.0
    radicand = (D * D + E * E) / 4.0 - F
    if radicand <= 0:
        return None
    r = float(np.sqrt(radicand))
    residual = _circle_residual(pts, cx, cy, r)
    return CircleFit(cx=float(cx), cy=float(cy), r=r, residual=residual)


def _circle_residual(pts: np.ndarray, cx: float, cy: float, r: float) -> float:
    dists = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)
    return float(np.sqrt(np.mean((dists - r) ** 2)))


def fit_circle_lm(points: np.ndarray, init: CircleFit) -> CircleFit:
    """Levenberg-Marquardt geometric refinement of a circle fit."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 3:
        return init

    def residuals(params):
        cx, cy, r = params
        if r <= 0:
            return np.full(pts.shape[0], 1e6)
        return np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r

    try:
        res = least_squares(
            residuals,
            x0=[init.cx, init.cy, max(init.r, 1e-3)],
            method="lm",
            max_nfev=200,
        )
        cx, cy, r = res.x
        if r <= 0 or not np.isfinite(r):
            return init
        return CircleFit(
            cx=float(cx), cy=float(cy), r=float(r),
            residual=_circle_residual(pts, float(cx), float(cy), float(r)),
        )
    except Exception:
        return init


def circle_coverage(points: np.ndarray, cx: float, cy: float) -> tuple[float, Optional[list[float]]]:
    """Coverage ratio in [0, 1] and optional [start, end] angle (rad) for arcs.

    Coverage = (max contiguous angular span) / (2*pi).
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 3:
        return 1.0, None
    angles = np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)
    angles = np.sort(angles)
    gaps = np.diff(angles)
    # wrap-around gap
    gaps = np.append(gaps, (angles[0] + 2 * np.pi) - angles[-1])
    max_gap = float(np.max(gaps))
    span = 2 * np.pi - max_gap
    coverage = float(span / (2 * np.pi))
    if coverage >= 0.92:
        return 1.0, None
    # find arc start/end: the arc is everything except the max gap
    idx = int(np.argmax(gaps))
    if idx == len(angles) - 1:
        start, end = float(angles[0]), float(angles[-1])
    else:
        start, end = float(angles[idx + 1]), float(angles[idx])
    return coverage, [start, end]


# ---------- ellipse fitting ----------

@dataclass
class EllipseFit:
    cx: float
    cy: float
    semi_major: float
    semi_minor: float
    rotation: float       # radians
    residual: float


def _ellipse_from_cv(center, axes, angle_deg) -> EllipseFit:
    cx, cy = float(center[0]), float(center[1])
    a, b = float(axes[0]) / 2.0, float(axes[1]) / 2.0  # cv2 returns full axes
    semi_major = max(a, b)
    semi_minor = min(a, b)
    # angle_deg is the angle of the major axis (full axes[0] direction) vs x-axis,
    # but if axes[1] > axes[0] OpenCV reports the rotated rect's "width" angle.
    # Normalize so that rotation always corresponds to the semi_major axis.
    rotation = float(np.radians(angle_deg))
    if b > a:
        rotation += np.pi / 2.0
    return EllipseFit(
        cx=cx, cy=cy,
        semi_major=semi_major, semi_minor=semi_minor,
        rotation=rotation, residual=0.0,
    )


def fit_ellipse_fitzgibbon(points: np.ndarray) -> Optional[EllipseFit]:
    """cv2.fitEllipse wrapper (Fitzgibbon direct least squares)."""
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
    if pts.shape[0] < 5:
        return None
    try:
        center, axes, angle = cv2.fitEllipse(pts)
    except Exception:
        return None
    if axes[0] <= 0 or axes[1] <= 0:
        return None
    fit = _ellipse_from_cv(center, axes, angle)
    fit.residual = ellipse_residual(points, fit)
    return fit


def ellipse_residual(points: np.ndarray, fit: EllipseFit) -> float:
    """RMS radial residual of points vs ellipse (Taubin-style approximation)."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] == 0:
        return 0.0
    dx = pts[:, 0] - fit.cx
    dy = pts[:, 1] - fit.cy
    ct, st = np.cos(fit.rotation), np.sin(fit.rotation)
    u = dx * ct + dy * st
    v = -dx * st + dy * ct
    a, b = fit.semi_major, fit.semi_minor
    if a < 1e-9 or b < 1e-9:
        return float("inf")
    # approximate radial error: r_ellipse(u,v) - measured r
    # use normalized form (u/a)^2 + (v/b)^2 = 1 -> r = 1/sqrt(...)
    norm = np.sqrt((u / a) ** 2 + (v / b) ** 2)
    norm = np.where(norm < 1e-9, 1e-9, norm)
    r_local = 1.0 / norm
    # scale back to pixel-space: factor ~ avg(a,b)
    r_pix = r_local * ((a + b) / 2.0)
    r_meas = np.hypot(dx, dy)
    return float(np.sqrt(np.mean((r_meas - r_pix) ** 2)))


def fit_ellipse_ransac(
    points: np.ndarray,
    threshold_px: float = 2.5,
    max_iters: int = 80,
    rng: Optional[np.random.Generator] = None,
) -> Optional[EllipseFit]:
    """RANSAC ellipse fit. Returns best fit over consensus sets, or None."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 5:
        return None
    rng = rng or np.random.default_rng(0)
    n = pts.shape[0]
    best_fit: Optional[EllipseFit] = None
    best_inliers = 0
    for _ in range(max_iters):
        idx = rng.choice(n, size=min(5, n), replace=False)
        sample = pts[idx].astype(np.float32).reshape(-1, 1, 2)
        try:
            center, axes, angle = cv2.fitEllipse(sample)
        except Exception:
            continue
        if axes[0] <= 0 or axes[1] <= 0:
            continue
        cand = _ellipse_from_cv(center, axes, angle)
        # compute per-point residual via approximate distance
        dx = pts[:, 0] - cand.cx
        dy = pts[:, 1] - cand.cy
        ct, st = np.cos(cand.rotation), np.sin(cand.rotation)
        u = dx * ct + dy * st
        v = -dx * st + dy * ct
        a, b = cand.semi_major, cand.semi_minor
        if a < 1e-9 or b < 1e-9:
            continue
        err = np.abs((u / a) ** 2 + (v / b) ** 2 - 1.0) * min(a, b)
        inliers = int(np.sum(err < threshold_px))
        if inliers > best_inliers:
            best_inliers = inliers
            best_fit = cand
    if best_fit is None or best_inliers < 5:
        return None
    # refine on inliers
    dx = pts[:, 0] - best_fit.cx
    dy = pts[:, 1] - best_fit.cy
    ct, st = np.cos(best_fit.rotation), np.sin(best_fit.rotation)
    u = dx * ct + dy * st
    v = -dx * st + dy * ct
    a, b = best_fit.semi_major, best_fit.semi_minor
    err = np.abs((u / a) ** 2 + (v / b) ** 2 - 1.0) * min(a, b)
    inlier_pts = pts[err < threshold_px]
    if inlier_pts.shape[0] >= 5:
        refined = fit_ellipse_fitzgibbon(inlier_pts)
        if refined is not None:
            return refined
    best_fit.residual = ellipse_residual(pts, best_fit)
    return best_fit


def ellipse_foci(fit: EllipseFit) -> tuple[list[tuple[float, float]], float]:
    """Return (foci, eccentricity). For a circle (a≈b) foci = [center, center]."""
    a, b = fit.semi_major, fit.semi_minor
    if a < 1e-9:
        return [(fit.cx, fit.cy), (fit.cx, fit.cy)], 0.0
    ecc = float(np.sqrt(max(0.0, 1.0 - (b / a) ** 2)))
    if b >= a - 1e-6:
        return [(fit.cx, fit.cy), (fit.cx, fit.cy)], 0.0
    c = float(np.sqrt(a * a - b * b))
    ct, st = np.cos(fit.rotation), np.sin(fit.rotation)
    f1 = (fit.cx + c * ct, fit.cy + c * st)
    f2 = (fit.cx - c * ct, fit.cy - c * st)
    return [f1, f2], ecc


# ---------- subpixel point refinement ----------

def refine_corners_subpixel(
    gray: np.ndarray, corners: np.ndarray, win: tuple[int, int] = (5, 5)
) -> np.ndarray:
    """cv2.cornerSubPix refinement. corners: (N,1,2) float32. Returns (N,2)."""
    if corners is None or len(corners) == 0:
        return np.zeros((0, 2), dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)
    try:
        refined = cv2.cornerSubPix(gray, corners.astype(np.float32), win, (-1, -1), criteria)
    except Exception:
        refined = corners
    return refined.reshape(-1, 2)


# ---------- confidence helpers ----------

def confidence_from_residual(residual: float, tol: float) -> float:
    """confidence = max(0, 1 - residual/tol)."""
    if tol <= 0:
        return 0.0
    return float(max(0.0, 1.0 - residual / tol))
