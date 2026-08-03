from __future__ import annotations

import pytest
from pydantic import ValidationError

from geometry_agent.types import GradeLevel
from geometry_agent.verification import Step, StepVerifier, Verdict, build_verifier
from geometry_agent.verification.lean_client import LeanStepVerifier
from geometry_agent.verification.symbolic import SymbolicStepVerifier


def test_verdict_requires_verified_field() -> None:
    v = Verdict(verified="true", evidence="x=2", reason="algebra")
    assert v.verified == "true"
    assert v.evidence == "x=2"
    assert v.reason == "algebra"
    assert v.lean_source is None


def test_verdict_rejects_invalid_verified_value() -> None:
    with pytest.raises(ValidationError):
        Verdict(verified="yes", evidence="x", reason="")


def test_step_captures_statement_and_premise_ids() -> None:
    s = Step(
        id="s1",
        statement="AB = CD",
        premise_ids=["s0"],
        justification="given",
    )
    assert s.id == "s1"
    assert s.statement == "AB = CD"
    assert s.premise_ids == ["s0"]
    assert s.justification == "given"


def test_build_verifier_junior_returns_symbolic() -> None:
    v = build_verifier(GradeLevel.JUNIOR)
    assert isinstance(v, SymbolicStepVerifier)
    assert isinstance(v, StepVerifier)


def test_build_verifier_senior_returns_symbolic() -> None:
    v = build_verifier(GradeLevel.SENIOR)
    assert isinstance(v, SymbolicStepVerifier)


def test_build_verifier_competition_with_endpoint_returns_lean() -> None:
    v = build_verifier(GradeLevel.COMPETITION, lean_endpoint="http://localhost:8080")
    assert isinstance(v, LeanStepVerifier)


def test_build_verifier_competition_without_endpoint_falls_back_to_symbolic() -> None:
    v = build_verifier(GradeLevel.COMPETITION, lean_endpoint=None)
    assert isinstance(v, SymbolicStepVerifier)
