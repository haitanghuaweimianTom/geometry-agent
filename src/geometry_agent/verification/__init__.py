from __future__ import annotations

from typing import Protocol, runtime_checkable

from geometry_agent.types import GradeLevel
from geometry_agent.verification._models import Step, Verdict
from geometry_agent.verification.lean_client import LeanStepVerifier
from geometry_agent.verification.symbolic import SymbolicStepVerifier


@runtime_checkable
class StepVerifier(Protocol):
    def verify(self, step: Step, premises: list[Step]) -> Verdict: ...


def build_verifier(
    grade: GradeLevel,
    *,
    client=None,
    lean_endpoint: str | None = None,
    symbolic_timeout_ms: int = 200,
) -> StepVerifier:
    if grade is GradeLevel.COMPETITION and lean_endpoint:
        return LeanStepVerifier(endpoint=lean_endpoint, timeout_s=10)
    return SymbolicStepVerifier(timeout_ms=symbolic_timeout_ms)


__all__ = [
    "Verdict",
    "Step",
    "StepVerifier",
    "build_verifier",
]
