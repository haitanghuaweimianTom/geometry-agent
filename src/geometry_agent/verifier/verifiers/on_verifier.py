"""OnVerifier: Point on Line/Segment/Ray/Circle/Arc/Ellipse (design/05 §2)."""

from __future__ import annotations

import math

from ...config import VerifierConfig
from ...types import Node, NodeType, VerifyResult, VerifyState
from ..tolerance import classify, tolerance
from . import line_coeffs, line_length, point_coords, proj_param


class OnVerifier:
    rel = "On"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        try:
            p = point_coords(src)
            if p is None:
                return VerifyResult(verified=VerifyState.FALSE, evidence="On: missing src coords")
            px, py = p
            t = dst.type
            if t in (NodeType.CIRCLE, NodeType.ARC):
                return self._on_circle(px, py, dst)
            if t in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY):
                return self._on_line(px, py, dst, t)
            if t == NodeType.ELLIPSE:
                from .ellipse_verifier import EllipseVerifier
                return EllipseVerifier(self.config).verify(src, dst, attrs)
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"On: unsupported dst type {t}")
        except Exception as ex:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"OnVerifier error: {ex}")

    # ------------------------------------------------------------------
    def _on_circle(self, px: float, py: float, dst: Node) -> VerifyResult:
        c = dst.attrs.get("center")
        r = dst.attrs.get("radius")
        if c is None or r is None:
            return VerifyResult(verified=VerifyState.FALSE, evidence="On: circle missing center/radius")
        r = float(r)
        d = math.hypot(px - c[0], py - c[1])
        e = abs(d - r)
        tol = tolerance(self.config.on_circle_abs_tol, self.config.on_circle_rel_tol, r)
        st = classify(e, tol, self.config.uncertain_band_mult)
        return VerifyResult(
            verified=st,
            measured={"dist": d, "radius": r, "error": e, "tol": tol},
            evidence=f"|OP-r|={e:.3f} (d={d:.3f}, r={r:.3f}), tol={tol:.3f} -> {st.value}",
            attrs={"dist": d, "radius": r},
        )

    # ------------------------------------------------------------------
    def _on_line(self, px: float, py: float, dst: Node, ntype: NodeType) -> VerifyResult:
        coeffs = line_coeffs(dst)
        if coeffs is None:
            return VerifyResult(verified=VerifyState.FALSE, evidence="On: line has no equation/endpoints")
        a, b, c = coeffs
        d = abs(a * px + b * py + c)
        scale = line_length(dst)
        if scale <= 0:
            ep = dst.attrs.get("endpoints")
            if ep and len(ep) >= 2:
                scale = math.hypot(ep[1][0] - ep[0][0], ep[1][1] - ep[0][1])
        if scale <= 0:
            scale = 1.0
        tol = tolerance(self.config.on_line_abs_tol, self.config.on_line_rel_tol, scale)
        # segment / ray range check
        in_range = True
        ep = dst.attrs.get("endpoints")
        if ntype == NodeType.SEGMENT and ep and len(ep) >= 2:
            tpar = proj_param(px, py, ep[0], ep[1])
            slack = tol / scale
            in_range = -slack <= tpar <= 1.0 + slack
        elif ntype == NodeType.RAY and ep and len(ep) >= 2:
            tpar = proj_param(px, py, ep[0], ep[1])
            slack = tol / scale
            in_range = tpar >= -slack
        e = d
        st = classify(e, tol, self.config.uncertain_band_mult)
        if not in_range:
            st = VerifyState.FALSE
        return VerifyResult(
            verified=st,
            measured={"dist": d, "error": e, "tol": tol, "in_range": in_range},
            evidence=f"dist(P,line)={d:.3f}, tol={tol:.3f}, in_range={in_range} -> {st.value}",
            attrs={"dist": d},
        )
