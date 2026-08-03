"""Tests for threading verification status through ProofStep and LaTeX rendering."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_proofstep_has_verified_field():
    from geometry_agent.types import ProofStep

    st = ProofStep(step=1, statement="AB=CD")
    assert hasattr(st, "verification_status")
    assert st.verification_status == "unknown"
    assert hasattr(st, "verifier_reason")
    assert st.verifier_reason == ""
    # Legacy bool ``verified`` still defaults to False for back-compat.
    assert st.verified is False


def test_proofstep_verified_true_false_uncertain_roundtrip():
    from geometry_agent.types import ProofStep

    for v in ("true", "false", "uncertain", "unknown"):
        st = ProofStep(
            step=1,
            statement="S",
            verification_status=v,
            verifier_reason=f"reason-{v}",
        )
        assert st.verification_status == v
        assert st.verifier_reason == f"reason-{v}"
        # Legacy boolean field independent of verification_status.
        d = st.model_dump()
        assert d["verification_status"] == v
        assert d["verifier_reason"] == f"reason-{v}"


def test_latex_renders_checkmark_for_true():
    from geometry_agent.report import solution_to_latex
    from geometry_agent.types import ProofStep, Solution

    sol = Solution(
        answer="42",
        proof=[
            ProofStep(step=1, statement="AB = CD", reason="by SAS",
                      verified=True, verification_status="true"),
        ],
    )
    tex = solution_to_latex("题文", sol, graph=None, title="T")
    assert r"\checkmark" in tex
    assert "verificationgreen" in tex or "verifiedgreen" in tex


def test_latex_renders_warning_for_uncertain():
    from geometry_agent.report import solution_to_latex
    from geometry_agent.types import ProofStep, Solution

    sol = Solution(
        answer="",
        proof=[
            ProofStep(step=1, statement="∠A=∠B", reason="推测",
                      verified=False, verification_status="uncertain",
                      verifier_reason="judge pass"),
        ],
    )
    tex = solution_to_latex("题文", sol, graph=None)
    # Orange bold '!' badge for uncertain.
    assert "verifiedorange" in tex
    assert r"\textbf{!}" in tex


def test_latex_renders_x_for_false():
    from geometry_agent.report import solution_to_latex
    from geometry_agent.types import ProofStep, Solution

    sol = Solution(
        answer="",
        proof=[
            ProofStep(step=1, statement="错误结论", reason="错误应用",
                      verified=False, verification_status="false",
                      verifier_reason="counterexample"),
        ],
    )
    tex = solution_to_latex("题文", sol, graph=None)
    assert r"\ding{55}" in tex
    assert "verifiedred" in tex


def test_latex_summary_line():
    from geometry_agent.report import solution_to_latex
    from geometry_agent.types import ProofStep, Solution

    sol = Solution(
        answer="ans",
        proof=[
            ProofStep(step=1, statement="s1", verified=True, verification_status="true"),
            ProofStep(step=2, statement="s2", verified=True, verification_status="true"),
            ProofStep(step=3, statement="s3", verified=False, verification_status="uncertain"),
            ProofStep(step=4, statement="s4", verified=False, verification_status="false"),
            ProofStep(step=5, statement="s5", verified=False),
        ],
    )
    tex = solution_to_latex("题文", sol, graph=None)
    assert "验证统计" in tex
    assert "2 步已证" in tex
    assert "1 步存疑" in tex
    assert "1 步错误" in tex
    assert "1 步未验证" in tex


def test_backward_compat_missing_verification_status():
    """ProofStep without verification_status still renders (treated as unknown)."""
    from geometry_agent.types import ProofStep, Solution
    from geometry_agent.report import solution_to_latex

    st = ProofStep(step=1, statement="step")
    # Back-compat: when verification_status is missing default is "unknown".
    assert st.verification_status == "unknown"
    sol = Solution(answer="", proof=[st])
    tex = solution_to_latex("题", sol, graph=None)
    assert "验证统计" in tex
    assert "1 步未验证" in tex
