"""Tree-of-Thoughts search (design/07 §3.2).

Propose multiple candidate sub-goals, verify each branch independently, prune
failures and recurse on the first fully-verified branch. Falls back to the
linear CoT plan when no branch succeeds.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..types import ProofPlan, ProofStep, ToolCall
from .cot import cot_reason, goal_spec
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, dispatch


def tot_search(
    client: Any,
    dsl: str,
    problem: str,
    goal: str,
    tools: dict[str, Any],
    max_depth: int = 8,
) -> ProofPlan:
    """ToT search with per-branch verification and pruning."""
    if getattr(client, "is_offline", False):
        return ProofPlan(goal=goal_spec(goal))

    base = cot_reason(client, dsl, problem, goal, tools)
    if _all_verified(base):
        return base

    tool_log: list[ToolCall] = []
    found = _tot_dfs(client, dsl, problem, goal, tools, [], max_depth, tool_log)
    if found is not None and _all_verified(found):
        return found

    return base or ProofPlan(goal=goal_spec(goal))


def _tot_dfs(client, dsl, problem, goal, tools, path, max_depth, tool_log):
    if len(path) > max_depth:
        return None

    branches = _propose_branches(client, dsl, problem, goal, path)
    for br in branches:
        verify_args = br.get("verify_args") or {}
        if verify_args:
            res = dispatch("verify", verify_args, tools)
            tool_log.append(ToolCall(name="verify", args=verify_args, result=res))
            if not _verify_ok(res):
                continue

        sub_goal = br.get("next_goal") or goal
        sub = _tot_dfs(client, dsl, problem, sub_goal, tools, path + [br], max_depth, tool_log)
        if sub is not None and _all_verified(sub):
            step = ProofStep(
                step=len(path) + 1,
                statement=br.get("statement", sub_goal or ""),
                reason=br.get("reason", "tot branch verified"),
                verified=True,
                tool_call=ToolCall(name="verify", args=verify_args) if verify_args else None,
            )
            merged = [step] + list(sub.plan or [])
            return ProofPlan(goal=goal_spec(goal), plan=merged, tool_calls=list(tool_log))
    return None


def _propose_branches(client, dsl, problem, goal, path) -> list[dict[str, Any]]:
    prompt = (
        f"[Tree-of-Thoughts] Goal: {goal}\n"
        f"DSL:\n{dsl}\nProblem: {problem}\n"
        f"Path so far: {path}\n\n"
        "Propose up to 3 candidate sub-goals that, if verified, advance the proof. "
        "Return ONLY a JSON array:\n"
        '[{"statement":"...","reason":"...","verify_args":{"relation":"...","src":"...","dst":"..."},'
        '"next_goal":"..."}]'
    )
    try:
        resp = client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT or "You are a geometry proof expert."},
                {"role": "user", "content": prompt},
            ],
            tools=TOOL_SCHEMAS,
            temperature=0.4,
        )
    except Exception:
        return []
    if resp is None or resp.get("offline"):
        return []
    content = (resp.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    raw = _extract_array(content)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _extract_array(content: str) -> str | None:
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", content)
    if m:
        return m.group(1)
    m = re.search(r"\[[\s\S]*\]", content)
    if m:
        return m.group(0)
    return None


def _verify_ok(res: Any) -> bool:
    if res is None:
        return False
    if isinstance(res, dict):
        return res.get("verified") in (True, "true", "True")
    return str(getattr(res, "verified", "")).lower() == "true"


def _all_verified(plan: ProofPlan | None) -> bool:
    return bool(plan and plan.plan) and all(s.verified for s in plan.plan)


__all__ = ["tot_search"]
