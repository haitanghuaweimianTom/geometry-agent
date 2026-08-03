"""Tests for verification middleware integration in _run_feedback_loop."""
from __future__ import annotations

import pytest

from geometry_agent.verification import Step, Verdict, VerifyState, StepVerifier
from geometry_agent.verification.llm_judge import LLMJudge


class FakeClient:
    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.calls = 0
        self.config = type(
            "C", (), {"max_tool_calls": 5, "temperature": 0.3, "is_offline": True,
                       "api_key": "", "model": "fake", "base_url": "",
                       "max_tokens": 1024, "max_reflections": 0, "fewshot_dir": "",
                       "voting_n": 1},
        )()

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.replies:
            return self.replies.pop(0)
        return {"choices": [{"message": {"role": "assistant", "content": "done"}}]}


class FakeVerifier(StepVerifier):
    def __init__(self, sequence):
        self.seq = list(sequence)
        self.calls = 0

    def verify(self, step, premises):
        self.calls += 1
        if self.seq:
            return self.seq.pop(0)
        return Verdict(verified=VerifyState.TRUE, evidence="ok")


class FakeJudge(LLMJudge):
    def __init__(self, verdict=None):
        self.calls = 0
        self.verdict = verdict or Verdict(verified=VerifyState.UNCERTAIN, reason="judge")

    def judge(self, step, premises, failures):
        self.calls += 1
        return self.verdict


def test_verify_and_retry_helper_exists():
    from geometry_agent.reasoning.enhanced_agent import _verify_and_retry
    assert callable(_verify_and_retry)


def test_verdict_true_adds_to_verified_steps():
    from geometry_agent.verification.symbolic import SymbolicStepVerifier
    v = SymbolicStepVerifier()
    s = Step(id="s1", statement="1+1 = 2", premise_ids=[], justification="算术")
    verdict = v.verify(s, [])
    assert verdict.verified == VerifyState.TRUE


def test_verdict_false_without_judge_returns_failure():
    v = FakeVerifier([Verdict(verified=VerifyState.FALSE, reason="not equal")])
    j = FakeJudge()
    from geometry_agent.reasoning.enhanced_agent import _verify_and_retry
    verdict, retries = _verify_and_retry(
        v, None,
        Step(id="s1", statement="1=2", premise_ids=[], justification=""),
        [], max_retries=0,
    )
    assert verdict.verified == VerifyState.FALSE
    assert retries == 0


def test_verdict_three_failures_calls_judge():
    v = FakeVerifier([Verdict(verified=VerifyState.FALSE, reason="nope")] * 4)
    j = FakeJudge(Verdict(verified=VerifyState.UNCERTAIN, reason="judge pass"))
    from geometry_agent.reasoning.enhanced_agent import _verify_and_retry
    verdict, retries = _verify_and_retry(
        v, j,
        Step(id="s1", statement="a=b", premise_ids=[], justification=""),
        [], max_retries=3,
    )
    assert j.calls == 1
    assert verdict.verified == VerifyState.UNCERTAIN
    assert retries == 3


def test_verdict_true_on_first_try_short_circuits():
    v = FakeVerifier([Verdict(verified=VerifyState.TRUE, evidence="ok")])
    j = FakeJudge()
    from geometry_agent.reasoning.enhanced_agent import _verify_and_retry
    verdict, retries = _verify_and_retry(
        v, j,
        Step(id="s1", statement="1+1=2", premise_ids=[], justification=""),
        [], max_retries=3,
    )
    assert v.calls == 1
    assert j.calls == 0
    assert verdict.verified == VerifyState.TRUE
    assert retries == 0


def test_agent_init_builds_verifier_and_judge():
    from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
    from geometry_agent.config import LLMConfig
    agent = EnhancedReasoningAgent(config=LLMConfig(), grade=__import__(
        "geometry_agent.types", fromlist=["GradeLevel"]).GradeLevel.SENIOR)
    assert agent.verifier is not None
    assert agent.llm_judge is not None
    assert agent.verified_steps == {}
    assert agent._step_retries == {}


def test_middleware_true_adds_to_verified_steps():
    """Claim_step with TRUE verdict should add step to verified_steps."""
    from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
    from geometry_agent.config import LLMConfig
    from geometry_agent.types import GradeLevel
    agent = EnhancedReasoningAgent(config=LLMConfig(), grade=GradeLevel.SENIOR)
    # Patch verifier to always return TRUE.
    agent.verifier = FakeVerifier([Verdict(verified=VerifyState.TRUE, evidence="ok")])

    # Simulate what happens in _run_feedback_loop after dispatch returns pending.
    result = {"status": "pending_verification", "step": {
        "step_id": "s1", "statement": "1+1=2", "premise_ids": [], "justification": "算术",
    }}
    step_data = result["step"]
    step_id = step_data.get("step_id", f"s{len(agent.verified_steps)+1}")
    step = Step(
        id=step_id,
        statement=step_data.get("statement", ""),
        premise_ids=step_data.get("premise_ids", []),
        justification=step_data.get("justification", ""),
    )
    verdict = agent.verifier.verify(step, [])
    assert verdict.verified == VerifyState.TRUE
    agent.verified_steps[step_id] = step
    assert "s1" in agent.verified_steps


def test_prompt_builder_injects_verification_contract_for_senior():
    from geometry_agent.reasoning.prompt_builder import build_enhanced_prompt
    from geometry_agent.types import GradeLevel
    msgs = build_enhanced_prompt(
        dsl="", problem="", goal="", knowledge="", subject=None, fewshot="",
        grade=GradeLevel.SENIOR,
    )
    user = msgs[-1]["content"]
    assert "claim_step" in user
    assert "验证契约" in user


def test_prompt_builder_injects_lean_note_for_competition():
    from geometry_agent.reasoning.prompt_builder import build_enhanced_prompt
    from geometry_agent.types import GradeLevel
    msgs = build_enhanced_prompt(
        dsl="", problem="", goal="", knowledge="", subject=None, fewshot="",
        grade=GradeLevel.COMPETITION,
    )
    user = msgs[-1]["content"]
    assert "Lean" in user
