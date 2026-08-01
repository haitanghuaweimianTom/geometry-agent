"""Unit tests for the LLM Reasoning Agent (design/07).

All LLM calls are mocked; no network access.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from geometry_agent.config import LLMConfig
from geometry_agent.reasoning.agent import LLMReasoningAgent
from geometry_agent.reasoning.cot import cot_reason, parse_plan
from geometry_agent.reasoning.llm_client import LLMClient
from geometry_agent.reasoning.reflection import reflect
from geometry_agent.reasoning.tools import TOOL_SCHEMAS, dispatch
from geometry_agent.types import ProofPlan, ProofStep


# --------------------------------------------------------------------------- #
# 1. Offline mode (no api_key): reason() must not crash and returns a ProofPlan.
# --------------------------------------------------------------------------- #
def test_offline_reason_returns_plan():
    agent = LLMReasoningAgent(LLMConfig(), {})
    plan = agent.reason("Objects:\n  - Point(A): [0,0]", "test problem", {})
    assert isinstance(plan, ProofPlan)
    # plan may be empty in offline mode
    assert plan.plan == []


def test_offline_agent_with_voting_does_not_crash():
    cfg = LLMConfig(api_key="", voting_n=3)
    agent = LLMReasoningAgent(cfg, {})
    plan = agent.reason("dsl", "求 x 的值", {})
    assert isinstance(plan, ProofPlan)


# --------------------------------------------------------------------------- #
# 2. tools.dispatch: calling verify with a lambda mock returns the result.
# --------------------------------------------------------------------------- #
def test_dispatch_verify_returns_result():
    tools_dict = {
        "verify": lambda rel, src, dst, attrs=None: {
            "verified": "true",
            "evidence": "mock ok",
            "measured": {},
        }
    }
    res = dispatch("verify", {"rel": "On", "src": "A", "dst": "B"}, tools_dict)
    assert res["verified"] == "true"
    assert res["evidence"] == "mock ok"


def test_dispatch_serializes_pydantic_result():
    from geometry_agent.types import VerifyResult, VerifyState

    tools_dict = {
        "verify": lambda rel, src, dst, attrs=None: VerifyResult(
            verified=VerifyState.TRUE, evidence="pydantic ok"
        )
    }
    res = dispatch("verify", {"rel": "On", "src": "A", "dst": "B"}, tools_dict)
    assert res["verified"] == "true"
    assert res["evidence"] == "pydantic ok"


def test_dispatch_unknown_tool_returns_error():
    res = dispatch("bogus", {}, {"verify": lambda **kw: {}})
    assert "error" in res


def test_dispatch_handles_exception():
    def boom(**kw):
        raise ValueError("boom")

    res = dispatch("verify", {"rel": "On", "src": "A", "dst": "B"}, {"verify": boom})
    assert "error" in res
    assert "ValueError" in res["error"]


def test_dispatch_reflect_not_in_tools_returns_noop():
    res = dispatch("reflect", {"failure": "x"}, {"verify": lambda **kw: {}})
    assert res["status"] == "noop"


def test_tool_schemas_well_formed():
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert {"verify", "solve", "search", "graph_query", "reflect"} <= names


# --------------------------------------------------------------------------- #
# 3. reflect(): with a mock client, returns a new parsed plan on failure.
# --------------------------------------------------------------------------- #
class _MockClient:
    """Minimal client mock returning a canned JSON plan."""

    is_offline = False
    config = LLMConfig()

    def __init__(self, content: str, tool_calls: Any = None):
        self._content = content
        self._tool_calls = tool_calls
        self.calls = 0

    def chat(self, messages, tools=None, temperature=0.3):
        self.calls += 1
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": self._content,
                        "tool_calls": self._tool_calls,
                    },
                    "finish_reason": "stop",
                }
            ]
        }


def test_reflect_returns_revised_plan():
    revised_json = json.dumps(
        {
            "plan": [
                {"step": 1, "statement": "revised claim", "reason": "reflected", "verified": True}
            ],
            "goal": {"kind": "Prove", "statement": "G"},
        }
    )
    client = _MockClient(revised_json)
    failing = ProofPlan(
        plan=[ProofStep(step=1, statement="bad", reason="r", verified=False)],
    )
    new_plan = reflect(client, "step 1: bad", failing, [])
    assert isinstance(new_plan, ProofPlan)
    assert len(new_plan.plan) == 1
    assert new_plan.plan[0].statement == "revised claim"
    assert new_plan.plan[0].verified is True
    assert client.calls == 1


def test_reflect_offline_returns_original_plan():
    class OfflineClient:
        is_offline = True

        def chat(self, *a, **kw):
            raise AssertionError("should not call chat when offline")

    original = ProofPlan(plan=[ProofStep(step=1, statement="keep", verified=False)])
    out = reflect(OfflineClient(), "fail", original, [])
    assert out is original


def test_reflect_keeps_plan_when_response_empty():
    client = _MockClient("no json here at all")
    failing = ProofPlan(
        plan=[ProofStep(step=1, statement="bad", verified=False)],
    )
    out = reflect(client, "fail", failing, [])
    assert out is failing


# --------------------------------------------------------------------------- #
# 4. LLMClient.chat with no key must not raise.
# --------------------------------------------------------------------------- #
def test_llm_client_chat_no_key_does_not_raise():
    client = LLMClient(LLMConfig())  # api_key == ""
    assert client.is_offline is True
    resp = client.chat([{"role": "user", "content": "hi"}])
    assert isinstance(resp, dict)
    assert resp.get("offline") is True
    assert resp["choices"][0]["message"]["role"] == "assistant"


def test_llm_client_chat_with_key_but_network_error_degrades(monkeypatch):
    cfg = LLMConfig(api_key="sk-test", base_url="http://localhost:1/v1")

    client = LLMClient(cfg)
    assert client.is_offline is False

    # Force httpx.Client.post to raise so we exercise the exception path.
    import httpx

    class _BoomClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            raise httpx.ConnectError("boom", request=None)

    monkeypatch.setattr(httpx, "Client", _BoomClient)
    resp = client.chat([{"role": "user", "content": "hi"}])
    assert isinstance(resp, dict)
    assert resp.get("offline") is True


# --------------------------------------------------------------------------- #
# Extra: end-to-end CoT with a mock client that returns a final JSON plan
# (no tool calls) -> parse_plan produces a verified ProofPlan.
# --------------------------------------------------------------------------- #
def test_cot_reason_parses_final_plan_from_mock_client():
    plan_json = json.dumps(
        {
            "plan": [
                {
                    "step": 1,
                    "statement": "△ADE ∽ △ABC",
                    "reason": "AA",
                    "verified": True,
                    "tool_call": {"name": "verify", "args": {"rel": "Similar", "src": "T1", "dst": "T2"}},
                }
            ],
            "goal": {"kind": "Prove", "statement": "△ADE ∽ △ABC"},
        }
    )
    client = _MockClient(plan_json)
    plan = cot_reason(client, "dsl", "problem", "goal statement", {}, fewshot="")
    assert isinstance(plan, ProofPlan)
    assert len(plan.plan) == 1
    assert plan.plan[0].verified is True
    assert plan.plan[0].tool_call.name == "verify"


def test_cot_reason_runs_tool_call_loop():
    """First response: a verify tool call. Second response: final JSON plan."""
    tool_call_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "let me verify",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "verify",
                                "arguments": json.dumps(
                                    {"rel": "On", "src": "A", "dst": "B"}
                                ),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    final_json = json.dumps(
        {
            "plan": [{"step": 1, "statement": "A on B", "reason": "verified", "verified": True}],
            "goal": {"kind": "Prove", "statement": "G"},
        }
    )
    final_response = {
        "choices": [
            {"message": {"role": "assistant", "content": final_json, "tool_calls": None},
             "finish_reason": "stop"}
        ]
    }

    class LoopClient:
        is_offline = False
        config = LLMConfig()

        def __init__(self):
            self.responses = [tool_call_response, final_response]
            self.idx = 0

        def chat(self, messages, tools=None, temperature=0.3):
            r = self.responses[self.idx]
            self.idx += 1
            return r

    tools_dict = {
        "verify": lambda rel, src, dst, attrs=None: {"verified": "true", "evidence": "ok"}
    }
    client = LoopClient()
    plan = cot_reason(client, "dsl", "problem", "G", tools_dict, fewshot="")
    assert len(plan.plan) == 1
    assert plan.plan[0].verified is True
    assert len(plan.tool_calls) == 1
    assert plan.tool_calls[0].name == "verify"
    assert plan.tool_calls[0].result["verified"] == "true"


def test_parse_plan_fallback_on_no_json():
    plan = parse_plan("just plain text, no json", "goal")
    assert len(plan.plan) == 1
    assert plan.plan[0].verified is False
    assert plan.plan[0].reason == "raw LLM output"


def test_agent_reflection_loop_invoked_on_failure():
    """Agent.reason with a mock that returns an unverified plan then a fixed one."""
    # First cot call returns an unverified step; reflect returns a verified plan.
    bad_json = json.dumps(
        {
            "plan": [{"step": 1, "statement": "bad", "reason": "r", "verified": False}],
            "goal": {"kind": "Prove", "statement": "G"},
        }
    )
    good_json = json.dumps(
        {
            "plan": [{"step": 1, "statement": "fixed", "reason": "reflected", "verified": True}],
            "goal": {"kind": "Prove", "statement": "G"},
        }
    )

    class AgentMockClient:
        is_offline = False
        config = LLMConfig()

        def __init__(self):
            self.seq = [bad_json, good_json]
            self.idx = 0

        def chat(self, messages, tools=None, temperature=0.3):
            content = self.seq[min(self.idx, len(self.seq) - 1)]
            self.idx += 1
            return {
                "choices": [
                    {"message": {"role": "assistant", "content": content, "tool_calls": None},
                     "finish_reason": "stop"}
                ]
            }

    agent = LLMReasoningAgent(LLMConfig(api_key="sk-test"), {})
    agent.client = AgentMockClient()
    plan = agent.reason("dsl", "problem", {})
    assert isinstance(plan, ProofPlan)
    # reflection should have replaced the failing plan with the verified one
    assert plan.plan[0].statement == "fixed"
    assert plan.plan[0].verified is True
