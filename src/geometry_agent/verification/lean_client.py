"""Lean (competition-grade) step-verifier backend stub."""

from __future__ import annotations

from geometry_agent.types import VerifyState
from geometry_agent.verification._models import Step, Verdict


class LeanStepVerifier:
    def __init__(self, endpoint: str, timeout_s: int = 10) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s

    def verify(self, step: Step, premises: list[Step]) -> Verdict:
        return Verdict(verified=VerifyState.UNCERTAIN, reason="not implemented")
