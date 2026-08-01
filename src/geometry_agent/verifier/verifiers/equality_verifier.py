"""EqualityVerifier: segment-length & angle equality (design/05 §2)."""

from __future__ import annotations


from ...config import VerifierConfig
from ...types import Node, NodeType, VerifyResult, VerifyState
from ..tolerance import classify
from . import line_length


class EqualityVerifier:
    rel = "Equal"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        try:
            if src.type == NodeType.SEGMENT and dst.type == NodeType.SEGMENT:
                return self._length_equal(src, dst)
            ang1 = attrs.get("angle1") if attrs else None
            ang2 = attrs.get("angle2") if attrs else None
            if ang1 is not None and ang2 is not None:
                return self._angle_equal(float(ang1), float(ang2))
            return VerifyResult(
                verified=VerifyState.FALSE,
                evidence="Equal: no comparable segments or angles",
            )
        except Exception as ex:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"EqualityVerifier error: {ex}")

    # ------------------------------------------------------------------
    def _length_equal(self, s1: Node, s2: Node) -> VerifyResult:
        L1 = line_length(s1)
        L2 = line_length(s2)
        avg = 0.5 * (L1 + L2)
        if avg < 1e-9:
            return VerifyResult(verified=VerifyState.FALSE, evidence="Equal: degenerate segments")
        e = abs(L1 - L2) / avg
        tol = float(self.config.equal_rel_tol)
        st = classify(e, tol, self.config.uncertain_band_mult)
        return VerifyResult(
            verified=st,
            measured={"L1": L1, "L2": L2, "rel_err": e, "tol": tol},
            evidence=f"|L1-L2|/avg={e:.4f}, tol={tol} -> {st.value}",
            attrs={"L1": L1, "L2": L2},
        )

    def _angle_equal(self, a1: float, a2: float) -> VerifyResult:
        e = abs(a1 - a2)
        tol = float(self.config.equal_angle_tol_deg)
        st = classify(e, tol, self.config.uncertain_band_mult)
        return VerifyResult(
            verified=st,
            measured={"angle1": a1, "angle2": a2, "err": e, "tol": tol},
            evidence=f"|delta_angle|={e:.3f}deg, tol={tol}deg -> {st.value}",
        )
