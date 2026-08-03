"""End-to-end graded-verification tests.

These tests exercise the ``EnhancedReasoningAgent`` feedback loop across all
three ``GradeLevel`` settings (junior / senior / competition) but stub out the
LLM client and the Lean HTTP client so nothing actually hits the network.

Each test feeds the agent a deterministic, scripted sequence of chat responses:
  1. First call → a ``claim_step`` tool call for an intermediate claim that the
     symbolic verifier (or mocked Lean verifier) will accept.
  2. Second call → a ``claim_step`` for the final answer.
  3. Third call → a final JSON answer (no tool calls) ending the loop.

The assertions verify that:
  - The agent returns a non-empty plan with ≥1 steps.
  - At least one step carries a populated ``verification_status``.
  - The LaTeX renderer emits a verification badge and the "验证统计" line.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from geometry_agent.config import LLMConfig, VerificationConfig
from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
from geometry_agent.report import solution_to_latex
from geometry_agent.types import GradeLevel, ProofStep, Solution


class _StubKnowledgeManager:
    """Minimal knowledge manager returning plane-geometry defaults."""

    class _RK:
        def __init__(self):
            self.topic = type("T", (), {"value": "plane_geometry"})()

    def get_knowledge(self, *_a, **_kw):
        return self._RK()

    def format_for_prompt(self, *_a, **_kw):
        return ""


def _make_agent(grade: GradeLevel) -> EnhancedReasoningAgent:
    cfg = LLMConfig(
        api_key="fake-key",
        max_tool_calls=8,
        verification=VerificationConfig(
            llm_judge_enabled=False,
            max_retries=0,
        ),
    )
    agent = EnhancedReasoningAgent(cfg, tools={}, grade=grade)
    agent.knowledge_manager = _StubKnowledgeManager()
    return agent


def _scripted_chat(step1: dict[str, str], step2: dict[str, str], answer: str, summary: str):
    """Return a fake chat() implementing the 3-step scripted protocol."""
    state = {"n": 0}

    def _chat(messages, tools=None, temperature=None):
        state["n"] += 1
        n = state["n"]
        if n == 1:
            tc = {
                "id": "c1",
                "type": "function",
                "function": {
                    "name": "claim_step",
                    "arguments": json.dumps({
                        "step_id": "s1",
                        "statement": step1["statement"],
                        "justification": step1["justification"],
                        "premise_ids": [],
                    }),
                },
            }
            return _msg(tc)
        if n == 2:
            tc = {
                "id": "c2",
                "type": "function",
                "function": {
                    "name": "claim_step",
                    "arguments": json.dumps({
                        "step_id": "s2",
                        "statement": step2["statement"],
                        "justification": step2["justification"],
                        "premise_ids": ["s1"],
                    }),
                },
            }
            return _msg(tc)
        plan_json = json.dumps({
            "plan": [
                {"step": 1, "statement": step1["statement"],
                 "reason": step1["justification"], "verified": True},
                {"step": 2, "statement": step2["statement"],
                 "reason": step2["justification"], "verified": True},
            ],
            "summary": summary,
            "key_equations": [step2["statement"]],
        })
        return _msg(None, content=plan_json)

    return _chat


def _msg(tool_call, content=""):
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_call is not None:
        msg["tool_calls"] = [tool_call]
    return {"choices": [{"message": msg}]}


def _assert_plan_ok(plan, problem_text: str) -> None:
    assert plan is not None, f"plan is None for {problem_text}"
    assert len(plan.plan) >= 1, f"plan has no steps for {problem_text}: {plan}"
    statuses = {getattr(st, "verification_status", "unknown") or "unknown"
                for st in plan.plan}
    assert statuses & {"true", "false", "uncertain", "unknown"}, \
        f"no verification status populated: {statuses}"
    # At least one step has been through verification middleware.
    assert any((getattr(st, "verification_status", "unknown") or "unknown")
               in {"true", "false", "uncertain"} for st in plan.plan), \
        f"expected at least one verified/uncertain/false step, got {statuses}"


def _assert_latex_ok(plan, answer: str, problem_text: str) -> None:
    sol = Solution(
        answer=answer,
        confidence=1.0,
        verified=True,
        proof=list(plan.plan),
        reasoning_summary=plan.summary or "",
        key_equations=plan.key_equations or [],
    )
    tex = solution_to_latex(problem_text, sol)
    assert r"\checkmark" in tex or "验证统计" in tex, \
        "LaTeX output missing verification badge or 验证统计 line"
    assert "验证统计" in tex, "LaTeX output missing 验证统计 line"


# ---------------------------------------------------------------------------
# Junior (3) — algebra / area, all verified by SymPy
# ---------------------------------------------------------------------------

def test_junior_x_plus_3_eq_7():
    agent = _make_agent(GradeLevel.JUNIOR)
    agent.client.chat = _scripted_chat(
        step1={"statement": "x = 7 - 3", "justification": "移项"},
        step2={"statement": "x = 4", "justification": "计算得 x=4"},
        answer="x=4",
        summary="移项解得 x=4",
    )
    plan = agent.reason("", "解方程 x + 3 = 7", {})
    _assert_plan_ok(plan, "jr-1 x+3=7")
    _assert_latex_ok(plan, "x=4", "解方程 x + 3 = 7")


def test_junior_2x_plus_1_eq_5():
    agent = _make_agent(GradeLevel.JUNIOR)
    agent.client.chat = _scripted_chat(
        step1={"statement": "2*x = 4", "justification": "移项 2x+1=5 => 2x=4"},
        step2={"statement": "x = 2", "justification": "两边除以 2"},
        answer="x=2",
        summary="移项两边除以 2 得 x=2",
    )
    plan = agent.reason("", "解方程 2x+1=5", {})
    _assert_plan_ok(plan, "jr-2 2x+1=5")
    _assert_latex_ok(plan, "x=2", "解方程 2x+1=5")


def test_junior_rectangle_area():
    agent = _make_agent(GradeLevel.JUNIOR)
    agent.client.chat = _scripted_chat(
        step1={"statement": "S = 5*3", "justification": "长方形面积=长×宽"},
        step2={"statement": "S = 15", "justification": "5*3=15"},
        answer="15",
        summary="长方形面积 5×3=15",
    )
    plan = agent.reason("", "长方形长5宽3,面积多少", {})
    _assert_plan_ok(plan, "jr-3 rectangle area")
    _assert_latex_ok(plan, "15", "长方形长5宽3,面积多少")


# ---------------------------------------------------------------------------
# Senior (3) — quadratic, trig identity, arithmetic sequence
# ---------------------------------------------------------------------------

def test_senior_quadratic():
    agent = _make_agent(GradeLevel.SENIOR)
    agent.client.chat = _scripted_chat(
        step1={"statement": "x**2 - 5*x + 6 = (x - 2)*(x - 3)",
               "justification": "因式分解"},
        step2={"statement": "(x - 2)*(x - 3) = 0",
               "justification": "代入方程"},
        answer="x=2 或 x=3",
        summary="因式分解得 (x-2)(x-3)=0, 根为 2 和 3",
    )
    plan = agent.reason("", "解方程 x^2 - 5x + 6 = 0", {})
    _assert_plan_ok(plan, "sr-1 quadratic")
    _assert_latex_ok(plan, "x=2 或 x=3", "解方程 x^2 - 5x + 6 = 0")


def test_senior_pythagorean_id():
    agent = _make_agent(GradeLevel.SENIOR)
    agent.client.chat = _scripted_chat(
        step1={"statement": "sin(x)**2 + cos(x)**2 = 1",
               "justification": "三角恒等式 sin^2+cos^2=1"},
        step2={"statement": "1",
               "justification": "恒等式成立"},
        answer="1",
        summary="由三角平方恒等式, sin^2 x + cos^2 x = 1",
    )
    plan = agent.reason("", "求 sin^2 x + cos^2 x", {})
    _assert_plan_ok(plan, "sr-2 pythagorean id")
    _assert_latex_ok(plan, "1", "求 sin^2 x + cos^2 x")


def test_senior_arithmetic_seq():
    agent = _make_agent(GradeLevel.SENIOR)
    agent.client.chat = _scripted_chat(
        step1={"statement": "a10 = 2 + (10 - 1)*3",
               "justification": "等差数列通项公式 an = a1 + (n-1)d"},
        step2={"statement": "a10 = 29",
               "justification": "2 + 9*3 = 29"},
        answer="29",
        summary="由等差数列通项公式 a10 = a1 + 9d = 2 + 27 = 29",
    )
    plan = agent.reason("", "等差数列a1=2,d=3,求a10", {})
    _assert_plan_ok(plan, "sr-3 arith seq")
    _assert_latex_ok(plan, "29", "等差数列a1=2,d=3,求a10")


# ---------------------------------------------------------------------------
# Competition (2) — Lean-backed. We monkeypatch requests.post in
# geometry_agent.verification.lean_client so the Lean HTTP client returns
# {"verified": true, "output": "ok"} without touching the network.
# ---------------------------------------------------------------------------

def _mock_lean_post(*_a, **_kw):
    resp = MagicMock()
    resp.json.return_value = {"verified": True, "output": "ok"}
    return resp


@patch("geometry_agent.verification.lean_client.requests.post", _mock_lean_post)
def test_competition_one_plus_one():
    agent = _make_agent(GradeLevel.COMPETITION)
    agent.client.chat = _scripted_chat(
        step1={"statement": "1 + 1 = 2", "justification": "Peano axioms / norm_num"},
        step2={"statement": "1 + 1 = 2", "justification": "证毕"},
        answer="1+1=2",
        summary="由自然数加法定义, 1+1=2",
    )
    plan = agent.reason("", "证明: 1+1=2", {})
    _assert_plan_ok(plan, "cp-1 1+1=2")
    _assert_latex_ok(plan, "1+1=2", "证明: 1+1=2")


@patch("geometry_agent.verification.lean_client.requests.post", _mock_lean_post)
def test_competition_sum_1_to_100():
    agent = _make_agent(GradeLevel.COMPETITION)
    agent.client.chat = _scripted_chat(
        step1={"statement": "1 + 2 + 3 + 100 = 5050",
               "justification": "高斯求和: n(n+1)/2 = 100*101/2 = 5050"},
        step2={"statement": "5050", "justification": "得解"},
        answer="5050",
        summary="高斯配对 (1+100)+(2+99)+...=50*101=5050",
    )
    plan = agent.reason("", "1+2+...+100 = 5050", {})
    _assert_plan_ok(plan, "cp-2 sum 1..100")
    _assert_latex_ok(plan, "5050", "1+2+...+100 = 5050")
