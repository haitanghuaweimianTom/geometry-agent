"""LLM Reasoning Agent (design/07).

Orchestrates CoT / self-consistency voting / reflection to turn a DSL + problem
text into a :class:`ProofPlan`. This is the entry point used by
``GeometryPipeline.llm_agent``.
"""

from __future__ import annotations

from typing import Any

from ..config import LLMConfig
from ..types import ProofPlan
from .cot import cot_reason
from .llm_client import LLMClient
from .prompts import fewshot_for
from .reflection import reflect
from .voting import self_consistency


class LLMReasoningAgent:
    """Top-level reasoning agent wired into the pipeline."""

    def __init__(self, config: LLMConfig | None = None, tools: dict | None = None):
        self.config = config or LLMConfig()
        self.tools = tools or {}
        self.client = LLMClient(self.config)

    def reason(self, dsl: str, problem: str, tools: dict) -> ProofPlan:
        """Produce a :class:`ProofPlan` for the given DSL + problem text.

        - ``voting_n == 1``  -> single-chain CoT (default).
        - ``voting_n  > 1``  -> self-consistency voting over ``voting_n`` samples.
        - Any failure triggers up to ``max_reflections`` reflection rounds.
        - No api_key -> offline: returns an empty unverified ProofPlan.
        """
        effective = dict(tools) if tools else dict(self.tools)
        if "reflect" not in effective:
            effective["reflect"] = self._make_reflect_tool()

        if self.client.is_offline:
            return ProofPlan()

        fewshot = fewshot_for("triangle")
        goal = problem or ""

        if self.config.voting_n > 1:
            plan = self_consistency(
                problem,
                self._make_run_fn(dsl, problem, goal, effective, fewshot),
                n=self.config.voting_n,
            )
        else:
            plan = cot_reason(self.client, dsl, problem, goal, effective, fewshot)

        if not self.client.is_offline and _has_failure(plan):
            history: list[dict[str, Any]] = []
            for _ in range(max(0, self.config.max_reflections)):
                failure = _failure_desc(plan)
                revised = reflect(self.client, failure, plan, history)
                history.append({"failure": failure, "plan": plan.model_dump()})
                plan = revised
                if not _has_failure(plan):
                    break

        return plan

    def _make_run_fn(self, dsl, problem, goal, effective, fewshot):
        client = self.client

        def run_fn(temperature: float) -> ProofPlan:
            orig = client.config.temperature
            client.config.temperature = temperature
            try:
                return cot_reason(client, dsl, problem, goal, effective, fewshot)
            finally:
                client.config.temperature = orig

        return run_fn

    def _make_reflect_tool(self):
        client = self.client

        def _reflect_tool(failure: str = "", plan: Any = None, history: Any = None):
            revised = reflect(client, failure or "", plan, history or [])
            return revised.model_dump()

        return _reflect_tool


def _has_failure(plan: ProofPlan) -> bool:
    if not isinstance(plan, ProofPlan):
        return True
    if not plan.plan:
        return True
    return any(not s.verified for s in plan.plan)


def _failure_desc(plan: ProofPlan) -> str:
    if not isinstance(plan, ProofPlan) or not plan.plan:
        return "empty plan"
    bad = [s for s in plan.plan if not s.verified]
    if not bad:
        return ""
    return "; ".join(f"step {s.step}: {s.statement}" for s in bad)


__all__ = ["LLMReasoningAgent"]
