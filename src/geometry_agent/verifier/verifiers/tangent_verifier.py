"""TangentVerifier: line-circle and circle-circle tangency (design/05 §2, §4)."""

from __future__ import annotations

import math

from ...config import VerifierConfig
from ...types import Node, NodeType, VerifyResult, VerifyState
from ..tolerance import classify, tolerance
from . import line_coeffs


class TangentVerifier:
    rel = "Tangent"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        try:
            if src.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY) and \
                    dst.type in (NodeType.CIRCLE, NodeType.ARC):
                return self._line_circle(src, dst, attrs)
            if src.type in (NodeType.CIRCLE, NodeType.ARC) and \
                    dst.type in (NodeType.CIRCLE, NodeType.ARC):
                return self._circle_circle(src, dst)
            return VerifyResult(
                verified=VerifyState.FALSE,
                evidence=f"Tangent: unsupported pair {src.type} -> {dst.type}",
            )
        except Exception as ex:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"TangentVerifier error: {ex}")

    # ------------------------------------------------------------------
    def _line_circle(self, line: Node, circle: Node, attrs: dict) -> VerifyResult:
        coeffs = line_coeffs(line)
        c = circle.attrs.get("center")
        r = circle.attrs.get("radius")
        if coeffs is None or c is None or r is None:
            return VerifyResult(verified=VerifyState.FALSE, evidence="Tangent: missing line/circle data")
        a, b, cc = coeffs
        r = float(r)
        signed = a * c[0] + b * c[1] + cc
        d = abs(signed)
        foot = (c[0] - a * signed, c[1] - b * signed)
        e = abs(d - r)
        tol = tolerance(self.config.tangent_abs_tol, self.config.tangent_rel_tol, r)
        st = classify(e, tol, self.config.uncertain_band_mult)
        tp = attrs.get("tangent_point")
        return VerifyResult(
            verified=st,
            measured={"dist": d, "radius": r, "error": e, "tol": tol},
            evidence=f"d(O,line)={d:.3f}, r={r:.3f}, |d-r|={e:.3f}, tol={tol:.3f} -> {st.value}",
            attrs={
                "tangent_point": tp,
                "tangent_coords": [foot[0], foot[1]],
                "dist": d,
                "radius": r,
            },
        )

    # ------------------------------------------------------------------
    def _circle_circle(self, c1: Node, c2: Node) -> VerifyResult:
        o1 = c1.attrs.get("center")
        o2 = c2.attrs.get("center")
        r1 = c1.attrs.get("radius")
        r2 = c2.attrs.get("radius")
        if None in (o1, o2, r1, r2):
            return VerifyResult(verified=VerifyState.FALSE, evidence="Tangent: missing circle data")
        r1, r2 = float(r1), float(r2)
        d = math.hypot(o1[0] - o2[0], o1[1] - o2[1])
        scale = r1 + r2
        tol = tolerance(self.config.tangent_abs_tol, self.config.tangent_rel_tol, scale)
        e_ext = abs(d - (r1 + r2))
        e_int = abs(d - abs(r1 - r2))
        if e_ext <= e_int:
            e, mode, target = e_ext, "external", r1 + r2
        else:
            e, mode, target = e_int, "internal", abs(r1 - r2)
        st = classify(e, tol, self.config.uncertain_band_mult)
        return VerifyResult(
            verified=st,
            measured={"center_dist": d, "r1": r1, "r2": r2, "error": e, "tol": tol, "mode": mode},
            evidence=f"d={d:.3f}, target={target:.3f} ({mode}), |delta|={e:.3f}, tol={tol:.3f} -> {st.value}",
            attrs={"mode": mode, "center_dist": d},
        )
