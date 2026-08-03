"""Symbolic (algebraic) step-verifier backend stub."""

from __future__ import annotations

from geometry_agent.types import VerifyState
from geometry_agent.verification._models import Step, Verdict


class SymbolicStepVerifier:
    def __init__(self, timeout_ms: int = 200) -> None:
        self.timeout_ms = timeout_ms

    def verify(self, step: Step, premises: list[Step]) -> Verdict:
        return Verdict(verified=VerifyState.UNCERTAIN, reason="not implemented")
