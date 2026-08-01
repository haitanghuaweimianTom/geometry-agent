"""EllipseVerifier: PF1+PF2 = 2a (design/05 §2, §4.3)."""

from __future__ import annotations

import math

from ...config import VerifierConfig
from ...types import Node, NodeType, VerifyResult, VerifyState
from ..tolerance import classify
from . import point_coords


class EllipseVerifier:
    rel = "On"  # invoked via On(P, Ellipse) dispatch

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        try:
            if dst.type != NodeType.ELLIPSE:
                return VerifyResult(verified=VerifyState.FALSE, evidence=f"Ellipse: dst not Ellipse ({dst.type})")
            p = point_coords(src)
            if p is None:
                return VerifyResult(verified=VerifyState.FALSE, evidence="Ellipse: missing point coords")
            px, py = p
            a = float(dst.attrs.get("semi_major", 0.0))
            b = float(dst.attrs.get("semi_minor", 0.0))
            foci = dst.attrs.get("foci") or []
            if len(foci) >= 2:
                f1 = (float(foci[0][0]), float(foci[0][1]))
                f2 = (float(foci[1][0]), float(foci[1][1]))
            else:
                cx, cy = dst.attrs.get("center", (0.0, 0.0))
                rot = float(dst.attrs.get("rotation", 0.0))
                c = math.sqrt(max(0.0, a * a - b * b))
                f1 = (float(cx) + c * math.cos(rot), float(cy) + c * math.sin(rot))
                f2 = (float(cx) - c * math.cos(rot), float(cy) - c * math.sin(rot))
            d1 = math.hypot(px - f1[0], py - f1[1])
            d2 = math.hypot(px - f2[0], py - f2[1])
            s = d1 + d2
            target = 2.0 * a
            e = abs(s - target)
            tol = self.config.ellipse_sum_rel_tol * target
            st = classify(e, tol, self.config.uncertain_band_mult)
            return VerifyResult(
                verified=st,
                measured={"PF1": d1, "PF2": d2, "sum": s, "2a": target, "error": e, "tol": tol},
                evidence=f"|PF1|+|PF2|={s:.3f}, 2a={target:.3f}, e={e:.3f}, tol={tol:.3f} -> {st.value}",
                attrs={"sum": s, "2a": target},
            )
        except Exception as ex:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"EllipseVerifier error: {ex}")
