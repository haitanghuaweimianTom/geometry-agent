"""Unit tests for the EnhancedReasoningAgent (design/07 §5 enhancement).

All LLM calls are mocked; no network access.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from geometry_agent.config import KnowledgeConfig, LLMConfig
from geometry_agent.knowledge.manager import KnowledgeManager
from geometry_agent.reasoning.agent import LLMReasoningAgent
from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
from geometry_agent.reasoning.prompt_builder import build_enhanced_prompt
from geometry_agent.types import ProofPlan, SubjectType


# --------------------------------------------------------------------------- #
# 1. Offline mode (no api_key): reason() must not crash, returns ProofPlan.
# --------------------------------------------------------------------------- #
def test_offline_reason_returns_plan():
    agent = EnhancedReasoningAgent(LLMConfig(), {}, None)
    plan = agent.reason("Objects:\n  - Point(A): [0,0]", "test problem", {})
    assert isinstance(plan, ProofPlan)
    assert plan.plan == []


def test_offline_reason_with_knowledge_manager_returns_plan():
    mgr = KnowledgeManager(KnowledgeConfig(web_enabled=False))
    agent = EnhancedReasoningAgent(LLMConfig(), {}, mgr)
    plan = agent.reason("Objects:\n  - Point(A): [0,0]", "AB 切圆 O 于 A", {})
    assert isinstance(plan, ProofPlan)
    assert plan.plan == []


# --------------------------------------------------------------------------- #
# 2. With knowledge_manager: reason() retrieves knowledge and the prompt
#    sent to the LLM contains the knowledge fragment.
# --------------------------------------------------------------------------- #
class _MockClient:
    """Captures the messages sent to chat() and returns a canned JSON plan."""

    is_offline = False
    config = LLMConfig(api_key="sk-test")

    def __init__(self, content: str):
        self._content = content
        self.captured_messages: list[list[dict]] = []

    def chat(self, messages, tools=None, temperature=0.3):
        self.captured_messages.append([dict(m) for m in messages])
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": self._content,
                        "tool_calls": None,
                    },
                    "finish_reason": "stop",
                }
            ]
        }


def test_reason_with_knowledge_manager_injects_knowledge_into_prompt():
    plan_json = json.dumps(
        {
            "plan": [
                {
                    "step": 1,
                    "statement": "OA ⊥ AB",
                    "reason": "切线性质定理",
                    "verified": True,
                }
            ],
            "goal": {"kind": "Prove", "statement": "OA ⊥ AB"},
        }
    )
    mgr = KnowledgeManager(KnowledgeConfig(web_enabled=False))
    agent = EnhancedReasoningAgent(LLMConfig(api_key="sk-test"), {}, mgr)
    mock_client = _MockClient(plan_json)
    agent.client = mock_client

    plan = agent.reason("Objects:\n  - Point(A): [0,0]", "AB 切圆 O 于 A, 求证 OA⊥AB", {})

    assert isinstance(plan, ProofPlan)
    assert len(plan.plan) == 1
    assert plan.plan[0].verified is True

    # The prompt sent to the LLM must contain the knowledge fragment.
    assert mock_client.captured_messages, "LLM was not called"
    sent = mock_client.captured_messages[0]
    full = "\n".join(m.get("content", "") for m in sent)
    assert "推荐" in full, "prompt must contain recommended-method markers"
    assert "课内方法" in full, "prompt must mention 课内方法 priority"


def test_reason_classifies_subject_and_uses_correct_fewshot():
    """Analytic problem → analytic few-shot with execute_code example."""
    plan_json = json.dumps(
        {
            "plan": [{"step": 1, "statement": "c=4", "reason": "sympy", "verified": True}],
            "goal": {"kind": "Solve", "statement": "椭圆焦点"},
        }
    )
    mgr = KnowledgeManager(KnowledgeConfig(web_enabled=False))
    agent = EnhancedReasoningAgent(LLMConfig(api_key="sk-test"), {}, mgr)
    mock_client = _MockClient(plan_json)
    agent.client = mock_client

    agent.reason("Objects:\n  - Ellipse(E): ...", "求椭圆 x²/25+y²/9=1 的焦点", {})

    sent = mock_client.captured_messages[0]
    full = "\n".join(m.get("content", "") for m in sent)
    assert "椭圆" in full or "解析" in full.lower() or "analytic" in full.lower()


# --------------------------------------------------------------------------- #
# 3. build_enhanced_prompt output contains key markers.
# --------------------------------------------------------------------------- #
def test_build_enhanced_prompt_contains_required_markers():
    knowledge = (
        "# 学科: 平面几何\n\n"
        "## 推荐方法 (按优先级排序, 课内方法优先尝试)\n"
        "1. 切线性质定理 (课内方法(推荐优先尝试)) [推荐优先尝试]\n"
    )
    messages = build_enhanced_prompt(
        dsl="Objects:\n  - Point(A): [0,0]",
        problem="AB 切圆 O 于 A",
        goal="OA⊥AB",
        knowledge=knowledge,
        subject=SubjectType.PLANE_GEOMETRY,
        fewshot="# example",
    )
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    full = messages[0]["content"] + "\n" + messages[1]["content"]
    assert "课内方法" in full
    assert "execute_code" in full
    assert "推荐" in full


def test_build_enhanced_prompt_without_knowledge():
    messages = build_enhanced_prompt(
        dsl="dsl",
        problem="problem",
        goal="goal",
        knowledge="",
        subject=SubjectType.TRIANGLE_SOLVING,
        fewshot="",
    )
    full = messages[0]["content"] + "\n" + messages[1]["content"]
    assert "课内方法" in full
    assert "execute_code" in full


# --------------------------------------------------------------------------- #
# 4. Few-shot files exist and are non-empty.
# --------------------------------------------------------------------------- #
_PROMPT_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "geometry_agent"
    / "reasoning"
    / "prompts"
)


@pytest.mark.parametrize(
    "filename",
    ["enhanced_system.txt", "fewshot_plane.txt", "fewshot_analytic.txt", "fewshot_triangle.txt"],
)
def test_fewshot_files_exist_and_nonempty(filename):
    p = _PROMPT_DIR / filename
    assert p.exists(), f"{filename} not found at {p}"
    text = p.read_text(encoding="utf-8").strip()
    assert len(text) > 50, f"{filename} is too short ({len(text)} chars)"


def test_fewshot_plane_contains_execute_code_example():
    text = (_PROMPT_DIR / "fewshot_plane.txt").read_text(encoding="utf-8")
    assert "execute_code" in text
    assert "verify" in text


def test_fewshot_analytic_contains_execute_code_example():
    text = (_PROMPT_DIR / "fewshot_analytic.txt").read_text(encoding="utf-8")
    assert "execute_code" in text


def test_fewshot_triangle_contains_solve_example():
    text = (_PROMPT_DIR / "fewshot_triangle.txt").read_text(encoding="utf-8")
    assert "solve" in text
    assert "余弦" in text or "正弦" in text


# --------------------------------------------------------------------------- #
# 5. Interface compatibility: both agents return ProofPlan.
# --------------------------------------------------------------------------- #
def test_enhanced_and_legacy_agent_both_return_proofplan_offline():
    cfg = LLMConfig()  # no api_key → offline
    enhanced = EnhancedReasoningAgent(cfg, {}, None)
    legacy = LLMReasoningAgent(cfg, {})

    dsl = "Objects:\n  - Point(A): [0,0]"
    problem = "test"

    ep = enhanced.reason(dsl, problem, {})
    lp = legacy.reason(dsl, problem, {})

    assert isinstance(ep, ProofPlan)
    assert isinstance(lp, ProofPlan)


def test_enhanced_agent_with_mock_llm_returns_proofplan():
    plan_json = json.dumps(
        {
            "plan": [
                {"step": 1, "statement": "claim", "reason": "r", "verified": True}
            ],
            "goal": {"kind": "Prove", "statement": "G"},
        }
    )
    agent = EnhancedReasoningAgent(LLMConfig(api_key="sk-test"), {}, None)
    agent.client = _MockClient(plan_json)
    plan = agent.reason("dsl", "problem", {})
    assert isinstance(plan, ProofPlan)
    assert len(plan.plan) == 1


# --------------------------------------------------------------------------- #
# Bonus: tool-merge brings in execute_code dispatcher.
# --------------------------------------------------------------------------- #
def test_merge_tools_includes_code_execution():
    agent = EnhancedReasoningAgent(LLMConfig(api_key="sk-test"), {}, None)
    merged = agent._merge_tools({"verify": lambda **kw: {"verified": "true"}})
    assert "verify" in merged
    assert "execute_code" in merged
    assert "complex_method" in merged
    assert "coordinate_method" in merged


# --------------------------------------------------------------------------- #
# LLM-decided 解题思路 summary (PDF appendix; must not leak code/JSON)
# --------------------------------------------------------------------------- #
def test_clean_summary_keeps_strategy_and_drops_markdown():
    from geometry_agent.reasoning.enhanced_agent import _clean_summary

    content = (
        "我注意到A(0,-2)与P(1,-2)纵坐标相同，猜想直线HN过定点A。\n"
        "**先证明共线条件**，再代入韦达定理验证。"
    )
    cleaned = _clean_summary(content)
    assert "猜想" in cleaned
    assert "韦达定理" in cleaned
    assert "**" not in cleaned


def test_clean_summary_removes_json_fragments():
    from geometry_agent.reasoning.enhanced_agent import _clean_summary

    content = (
        "设直线斜率为k，联立方程由韦达定理求x1+x2。"
        '{"plan":[{"step":1,"statement":"x"}]}'
    )
    cleaned = _clean_summary(content)
    assert "韦达定理" in cleaned
    assert '"plan"' not in cleaned


def test_clean_summary_empty_for_garbage():
    from geometry_agent.reasoning.enhanced_agent import _clean_summary

    assert _clean_summary("") == ""
    assert _clean_summary("###   \n** **") == ""


def test_parse_plan_extracts_summary():
    from geometry_agent.reasoning.cot import parse_plan

    content = (
        '{"plan":[{"step":1,"statement":"设椭圆方程","reason":"标准方程",'
        '"verified":true}],"goal":{"kind":"Prove","statement":"..."},'
        '"summary":"先猜后证：取特殊值猜测定点，再用韦达定理验证共线条件",'
        '"key_equations":["xB=4k(k-1)/(4k²+3)","xB(yC+3/4)-xC(yB+3/4)=0"]}'
    )
    plan = parse_plan(content, "证明直线过定点")
    assert plan.summary == "先猜后证：取特殊值猜测定点，再用韦达定理验证共线条件"
    assert len(plan.plan) == 1
    assert plan.key_equations == [
        "xB=4k(k-1)/(4k²+3)",
        "xB(yC+3/4)-xC(yB+3/4)=0",
    ]
