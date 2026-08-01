"""Relation verifiers: Collinear / Concentric / Intersect / Inscribed
(design/05 §2)."""

from __future__ import annotations

import math

from ...config import VerifierConfig
from ...types import Node, NodeType, VerifyResult, VerifyState
from ..tolerance import classify, tolerance
from . import line_coeffs


class CollinearVerifier:
    rel = "Collinear"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        try:
            pts = []
            if attrs and attrs.get("points"):
                pts = [tuple(p) for p in attrs["points"]]
            else:
                sp = src.attrs.get("coords")
                dp = dst.attrs.get("coords")
                p3 = attrs.get("point3") if attrs else None
                if sp and dp and p3:
                    pts = [tuple(sp), tuple(dp), tuple(p3)]
            if len(pts) < 3:
                return VerifyResult(verified=VerifyState.FALSE, evidence="Collinear: need >=3 points")
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            n = len(pts)
            mx = sum(xs) / n
            my = sum(ys) / n
            sxx = sum((x - mx) ** 2 for x in xs)
            sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            syy = sum((y - my) ** 2 for y in ys)
            if sxx < 1e-12 and syy < 1e-12:
                return VerifyResult(
                    verified=VerifyState.TRUE,
                    measured={"max_dist": 0.0, "tol": 0.0},
                    evidence="Collinear: coincident points",
                )
            if sxx >= syy:
                a = sxy / sxx if sxx > 1e-12 else 0.0
                b = -1.0
                c = my - a * mx
            else:
                a = 1.0
                b = -sxy / syy if syy > 1e-12 else 0.0
                c = -(a * mx + b * my)
            denom = math.hypot(a, b)
            dists = [abs(a * x + b * y + c) / denom for x, y in pts]
            e = max(dists)
            scale = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
            tol = tolerance(self.config.collinear_abs_tol, self.config.collinear_rel_tol, scale)
            st = classify(e, tol, self.config.uncertain_band_mult)
            return VerifyResult(
                verified=st,
                measured={"max_dist": e, "tol": tol, "scale": scale},
                evidence=f"max dist={e:.3f}, tol={tol:.3f} -> {st.value}",
            )
        except Exception as ex:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"CollinearVerifier error: {ex}")


class ConcentricVerifier:
    rel = "Concentric"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        try:
            o1 = src.attrs.get("center")
            o2 = dst.attrs.get("center")
            r1 = float(src.attrs.get("radius", 0.0))
            r2 = float(dst.attrs.get("radius", 0.0))
            if o1 is None or o2 is None:
                return VerifyResult(verified=VerifyState.FALSE, evidence="Concentric: missing center")
            d = math.hypot(o1[0] - o2[0], o1[1] - o2[1])
            avg_r = 0.5 * (r1 + r2) or 1.0
            tol = tolerance(self.config.concentric_abs_tol, self.config.concentric_rel_tol, avg_r)
            st = classify(d, tol, self.config.uncertain_band_mult)
            return VerifyResult(
                verified=st,
                measured={"center_dist": d, "tol": tol},
                evidence=f"|O1O2|={d:.3f}, tol={tol:.3f} -> {st.value}",
            )
        except Exception as ex:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"ConcentricVerifier error: {ex}")


class IntersectVerifier:
    rel = "Intersect"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        try:
            pts = _intersect(src, dst)
            if pts:
                return VerifyResult(
                    verified=VerifyState.TRUE,
                    measured={"num_intersections": len(pts)},
                    evidence=f"intersection at {[tuple(round(c, 2) for c in p) for p in pts]}",
                    attrs={"intersection_points": [list(p) for p in pts]},
                )
            return VerifyResult(
                verified=VerifyState.FALSE,
                measured={"num_intersections": 0},
                evidence="no intersection found",
            )
        except Exception as ex:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"IntersectVerifier error: {ex}")


class InscribedVerifier:
    rel = "Inscribed"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        try:
            verts = src.attrs.get("vertices") or []
            if len(verts) < 3:
                return VerifyResult(verified=VerifyState.FALSE, evidence="Inscribed: missing vertices")
            c = dst.attrs.get("center")
            r = dst.attrs.get("radius")
            if c is None or r is None:
                return VerifyResult(verified=VerifyState.FALSE, evidence="Inscribed: missing circle data")
            r = float(r)
            max_e = 0.0
            for v in verts:
                d = math.hypot(v[0] - c[0], v[1] - c[1])
                max_e = max(max_e, abs(d - r))
            tol = tolerance(self.config.on_circle_abs_tol, self.config.on_circle_rel_tol, r)
            st = classify(max_e, tol, self.config.uncertain_band_mult)
            return VerifyResult(
                verified=st,
                measured={"max_err": max_e, "tol": tol},
                evidence=f"max|OP-r|={max_e:.3f}, tol={tol:.3f} -> {st.value}",
            )
        except Exception as ex:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"InscribedVerifier error: {ex}")


# ---------------------------------------------------------------------------
def _intersect(src: Node, dst: Node):
    s_line = src.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)
    d_line = dst.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)
    s_circ = src.type in (NodeType.CIRCLE, NodeType.ARC)
    d_circ = dst.type in (NodeType.CIRCLE, NodeType.ARC)
    if s_line and d_line:
        return _ll(src, dst)
    if s_line and d_circ:
        return _lc(src, dst)
    if s_circ and d_line:
        return _lc(dst, src)
    if s_circ and d_circ:
        return _cc(src, dst)
    return []


def _ll(s: Node, d: Node):
    c1 = line_coeffs(s)
    c2 = line_coeffs(d)
    if c1 is None or c2 is None:
        return []
    a1, b1, cc1 = c1
    a2, b2, cc2 = c2
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
        return []
    x = (b1 * cc2 - b2 * cc1) / det
    y = (a2 * cc1 - a1 * cc2) / det
    return [(x, y)]


def _lc(line: Node, circle: Node):
    coeffs = line_coeffs(line)
    if coeffs is None:
        return []
    a, b, c = coeffs
    ctr = circle.attrs.get("center")
    r = circle.attrs.get("radius")
    if ctr is None or r is None:
        return []
    r = float(r)
    sd = a * ctr[0] + b * ctr[1] + c
    h2 = r * r - sd * sd
    if h2 < -1e-9:
        return []
    h = math.sqrt(max(0.0, h2))
    fx = ctr[0] - a * sd
    fy = ctr[1] - b * sd
    if h < 1e-6:
        return [(fx, fy)]
    return [(fx - b * h, fy + a * h), (fx + b * h, fy - a * h)]


def _cc(c1: Node, c2: Node):
    o1 = c1.attrs.get("center")
    o2 = c2.attrs.get("center")
    r1 = c1.attrs.get("radius")
    r2 = c2.attrs.get("radius")
    if None in (o1, o2, r1, r2):
        return []
    r1, r2 = float(r1), float(r2)
    d = math.hypot(o1[0] - o2[0], o1[1] - o2[1])
    if d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9 or d < 1e-9:
        return []
    a = (d * d + r1 * r1 - r2 * r2) / (2 * d)
    h = math.sqrt(max(0.0, r1 * r1 - a * a))
    px = o1[0] + a * (o2[0] - o1[0]) / d
    py = o1[1] + a * (o2[1] - o1[1]) / d
    if h < 1e-6:
        return [(px, py)]
    return [
        (px + h * (o2[1] - o1[1]) / d, py - h * (o2[0] - o1[0]) / d),
        (px - h * (o2[1] - o1[1]) / d, py + h * (o2[0] - o1[0]) / d),
    ]
