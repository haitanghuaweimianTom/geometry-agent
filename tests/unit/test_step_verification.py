"""Unit tests for the per-step verification factory and models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from geometry_agent.types import GradeLevel, VerifyState
from geometry_agent.verification import Step, StepVerifier, Verdict, build_verifier
from geometry_agent.verification.lean_client import LeanStepVerifier
from geometry_agent.verification.symbolic import SymbolicStepVerifier


def test_verdict_requires_verified_field() -> None:
    v = Verdict(verified=VerifyState.TRUE, evidence="x=2", reason="algebra")
    assert v.verified == VerifyState.TRUE
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
    assert v.timeout_s == 10


def test_build_verifier_competition_without_endpoint_falls_back_to_symbolic() -> None:
    v = build_verifier(GradeLevel.COMPETITION, lean_endpoint=None)
    assert isinstance(v, SymbolicStepVerifier)


def test_build_verifier_accepts_lean_timeout_s() -> None:
    v = build_verifier(
        GradeLevel.COMPETITION,
        lean_endpoint="http://localhost:8080",
        lean_timeout_s=42,
    )
    assert isinstance(v, LeanStepVerifier)
    assert v.timeout_s == 42


def test_symbolic_verifier_unparseable_returns_uncertain() -> None:
    v = SymbolicStepVerifier()
    s = Step(id="s1", statement="三角形ABC相似于三角形DEF")
    out = v.verify(s, [])
    assert out.verified == VerifyState.UNCERTAIN


def test_lean_verifier_returns_uncertain_stub() -> None:
    v = LeanStepVerifier(endpoint="http://x", timeout_s=5)
    s = Step(id="s1", statement="AB=CD")
    out = v.verify(s, [])
    assert out.verified == VerifyState.UNCERTAIN
    assert v.timeout_s == 5


def test_parse_claim_returns_none_for_plain_text() -> None:
    from geometry_agent.verification.step_parser import parse_claim

    assert parse_claim("just some text") is None


def test_claim_step_tool_schema_exists():
    from geometry_agent.reasoning.tools import TOOL_SCHEMAS
    names = [s["function"]["name"] for s in TOOL_SCHEMAS]
    assert "claim_step" in names
    schema = next(s["function"] for s in TOOL_SCHEMAS if s["function"]["name"] == "claim_step")
    props = schema["parameters"]["properties"]
    assert "statement" in props
    assert "step_id" in props
    assert "premise_ids" in props
    assert "justification" in props
    assert set(schema["parameters"]["required"]) == {"step_id", "statement", "justification"}
