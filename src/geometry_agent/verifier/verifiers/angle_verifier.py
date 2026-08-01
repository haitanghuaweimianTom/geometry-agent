"""AngleVerifier: Perpendicular & Parallel (design/05 §2)."""

from __future__ import annotations

from ...config import VerifierConfig
from ...types import Node, VerifyResult, VerifyState
from ..tolerance import classify
from . import angle_between_dirs, line_direction


def _verify_angle(src: Node, dst: Node, attrs: dict, rel: str, config: VerifierConfig) -> VerifyResult:
    try:
        u = line_direction(src)
        v = line_direction(dst)
        if u is None or v is None:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"{rel}: missing line direction")
        ang = angle_between_dirs(u, v)
        if ang is None:
            return VerifyResult(verified=VerifyState.FALSE, evidence=f"{rel}: degenerate direction")
        if rel == "Perpendicular":
            target = 90.0
            e = abs(ang - 90.0)
            tol = float(config.perp_angle_tol_deg)
        else:  # Parallel
            target = 0.0
            e = ang
            tol = float(config.parallel_angle_tol_deg)
        st = classify(e, tol, config.uncertain_band_mult)
        return VerifyResult(
            verified=st,
            measured={"angle_deg": ang, "target": target, "error": e, "tol": tol},
            evidence=f"theta={ang:.3f}deg, target={target}deg, |delta|={e:.3f}deg, tol={tol}deg -> {st.value}",
            attrs={"angle": ang},
        )
    except Exception as ex:
        return VerifyResult(verified=VerifyState.FALSE, evidence=f"AngleVerifier error: {ex}")


class PerpendicularVerifier:
    rel = "Perpendicular"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        return _verify_angle(src, dst, attrs, "Perpendicular", self.config)


class ParallelVerifier:
    rel = "Parallel"

    def __init__(self, config: VerifierConfig):
        self.config = config

    def verify(self, src: Node, dst: Node, attrs: dict) -> VerifyResult:
        return _verify_angle(src, dst, attrs, "Parallel", self.config)
