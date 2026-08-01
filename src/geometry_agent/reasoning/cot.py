"""Chain-of-Thought reasoning (design/07 §3.1).

Single linear path: the LLM proposes a claim, calls verify/solve to confirm it,
the tool result is fed back, and the loop continues until the LLM emits a final
JSON plan or ``max_tool_calls`` is reached.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..types import GoalSpec, ProofPlan, ProofStep, ToolCall
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, dispatch


def cot_reason(
    client: Any,
    dsl: str,
    problem: str,
    goal: str,
    tools: dict[str, Any],
    fewshot: str = "",
) -> ProofPlan:
    """Run a single-chain CoT and return a :class:`ProofPlan`."""
    if getattr(client, "is_offline", False):
        return ProofPlan(goal=goal_spec(goal))

    messages = _build_messages(dsl, problem, goal, fewshot)
    tool_log: list[ToolCall] = []
    cfg = getattr(client, "config", None)
    max_calls = getattr(cfg, "max_tool_calls", 30) or 30
    temp = getattr(cfg, "temperature", 0.3)

    non_json_rounds = 0
    for _ in range(max(1, int(max_calls))):
        try:
            resp = client.chat(messages, tools=TOOL_SCHEMAS, temperature=temp)
        except Exception:
            return _plan_from_tool_log(tool_log, goal)

        if resp is None or resp.get("offline"):
            return _plan_from_tool_log(tool_log, goal)

        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}

        assistant_msg: dict[str, Any] = {
            "role": msg.get("role", "assistant"),
            "content": msg.get("content") or "",
        }
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        messages.append(assistant_msg)

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            non_json_rounds = 0
            for tc in tool_calls:
                fn = tc.get("function", {}) or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except Exception:
                    args = {}
                result = dispatch(name, args, tools)
                tool_log.append(ToolCall(name=name, args=args, result=result))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
            # Nudge to converge past halfway.
            if len(tool_log) >= max(3, int(max_calls) // 2):
                messages.append({
                    "role": "user",
                    "content": (
                        "已收集足够证据。请停止调用工具，直接输出最终证明的单一 JSON 对象，"
                        '格式: {"plan":[{"step":1,"statement":"...","reason":"...",'
                        '"verified":true}],"goal":{"kind":"Prove","statement":"..."}}。'
                        "只输出 JSON，不要其他内容。"
                    ),
                })
            continue

        content = msg.get("content") or ""
        plan = parse_plan(content, goal)
        # parse_plan falls back to a raw-text single step when no JSON found.
        # If the raw output is long prose (not a clean JSON plan), push the LLM
        # to format it as JSON once before giving up.
        is_raw_fallback = (
            len(plan.plan) == 1
            and not plan.plan[0].verified
            and plan.plan[0].reason == "raw LLM output"
        )
        if is_raw_fallback and non_json_rounds < 1 and len(content) > 40:
            non_json_rounds += 1
            messages.append({
                "role": "user",
                "content": (
                    "上面的回答不是 JSON 格式。请把你刚才的解答整理成一个 JSON 对象输出，"
                    '格式: {"plan":[{"step":1,"statement":"结论(中文)","reason":"依据",'
                    '"verified":true}],"goal":{"kind":"Prove","statement":"..."}}。'
                    "只输出 JSON。"
                ),
            })
            continue
        plan.tool_calls = tool_log
        return plan

    # Loop exhausted: synthesise a plan from successful tool calls.
    return _plan_from_tool_log(tool_log, goal)


def _build_messages(dsl: str, problem: str, goal: str, fewshot: str) -> list[dict[str, Any]]:
    sys = SYSTEM_PROMPT or ""
    if fewshot:
        sys = f"{sys}\n\n{fewshot}"
    user = (
        "[Context]\n"
        f"# Geometry DSL\n{dsl}\n\n"
        f"# Problem\n{problem}\n\n"
        "[Task]\n"
        f"Goal: {goal}\n\n"
        "[Instructions]\n"
        "1. List the known verified facts and the goal.\n"
        "2. For each intermediate claim, call `verify` or `solve` to confirm it.\n"
        "3. If `verify` returns false, call `reflect` to revise the plan.\n"
        "4. When the goal is reached, output the final proof as a SINGLE JSON object:\n"
        '   {"plan":[{"step":1,"statement":"...","reason":"...","verified":true,'
        '"tool_call":{"name":"verify","args":{...}}}],'
        '"goal":{"kind":"Prove","statement":"..."}}\n'
    )
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ]


# --------------------------------------------------------------------------- #
# Shared helpers (reused by reflection.py and tot.py)
# --------------------------------------------------------------------------- #
def goal_spec(goal: Any) -> GoalSpec:
    if isinstance(goal, GoalSpec):
        return goal
    if isinstance(goal, dict):
        try:
            return GoalSpec(**goal)
        except Exception:
            return GoalSpec()
    if isinstance(goal, str) and goal.strip():
        return GoalSpec(kind="Prove", statement=goal)
    return GoalSpec()


def infer_goal(problem: str) -> GoalSpec:
    text = problem or ""
    kind = "Prove"
    if any(k in text for k in ("求", "计算", "值", "长度", "角度", "面积")):
        kind = "Solve"
    elif "找" in text or "find" in text.lower():
        kind = "Find"
    return GoalSpec(kind=kind, statement=text)


def _extract_json(content: str) -> str | None:
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
    if m:
        return m.group(1)
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        return m.group(0)
    return None


def parse_plan(content: str, goal: Any = None) -> ProofPlan:
    """Parse an LLM text response into a :class:`ProofPlan`.

    Falls back to a single unverified step holding the raw text when no valid
    JSON object can be found.
    """
    raw = _extract_json(content or "")
    data: Any = None
    if raw:
        try:
            data = json.loads(raw)
        except Exception:
            data = None

    if not isinstance(data, dict):
        gs = goal_spec(goal)
        return ProofPlan(
            goal=gs,
            plan=[
                ProofStep(
                    step=1,
                    statement=(content or "")[:500],
                    reason="raw LLM output",
                    verified=False,
                )
            ],
        )

    steps: list[ProofStep] = []
    for i, s in enumerate(data.get("plan", []) or [], 1):
        if not isinstance(s, dict):
            continue
        s = dict(s)
        s.setdefault("step", i)
        try:
            steps.append(ProofStep(**s))
        except Exception:
            steps.append(
                ProofStep(
                    step=s.get("step", i),
                    statement=str(s.get("statement", "")),
                    reason=str(s.get("reason", "")),
                    verified=bool(s.get("verified", False)),
                )
            )

    g = data.get("goal")
    gs = goal_spec(g) if g is not None else goal_spec(goal)
    # LLM-decided reasoning summary (Chinese). Accept several key names.
    summary = ""
    for key in ("summary", "解题思路", "insight", "reasoning_summary"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            summary = v.strip()
            break
    # LLM-decided key equations (the core formulas of the proof, chosen by
    # the model itself — NOT scraped from tool output).
    key_equations: list[str] = []
    for key in ("key_equations", "关键算式", "key_formulas"):
        v = data.get(key)
        if isinstance(v, list):
            key_equations = [str(x).strip() for x in v if str(x).strip()]
            break
        if isinstance(v, str) and v.strip():
            key_equations = [s.strip() for s in v.split("\n") if s.strip()]
            break
    return ProofPlan(plan=steps, goal=gs, summary=summary, key_equations=key_equations)


def _plan_from_tool_log(tool_log: list[ToolCall], goal: Any) -> ProofPlan:
    """Build a fallback ProofPlan from successful verify/solve tool calls.

    Used when the LLM exhausts ``max_tool_calls`` without emitting a final JSON
    plan. Each successful ``verify`` becomes a verified step; ``solve`` /
    ``execute_code`` results are summarised, and a best-effort final answer is
    extracted from the last successful computation.
    """
    steps: list[ProofStep] = []
    i = 0
    last_numeric_answer = ""
    for tc in tool_log:
        res = tc.result
        ok = False
        if isinstance(res, dict):
            v = res.get("verified")
            if v is True or v == "true" or getattr(v, "value", "") == "true":
                ok = True
        if not ok:
            continue
        i += 1
        if tc.name == "verify":
            args = tc.args or {}
            stmt = f"{args.get('rel','')}({args.get('src','')}, {args.get('dst','')})"
            reason = "verify 工具确认"
        elif tc.name == "solve":
            sol = res.get("solution", {}) if isinstance(res, dict) else {}
            stmt = f"方程求解: {sol}" if sol else "方程求解"
            reason = "solve 工具确认"
        elif tc.name == "execute_code":
            out = (res.get("output", "") if isinstance(res, dict) else "")
            stmt = f"代码计算: {out.strip()[:80]}" if out.strip() else "代码计算"
            reason = "execute_code 工具确认"
            # try to capture a numeric answer from the last output line
            if out.strip():
                last_line = [l for l in out.strip().splitlines() if l.strip()][-1]
                last_numeric_answer = last_line[:60]
        else:
            stmt = f"{tc.name} 确认"
            reason = f"{tc.name} 工具确认"
        steps.append(ProofStep(
            step=i, statement=stmt, reason=reason, verified=True,
            tool_call=tc,
        ))
    gs = goal_spec(goal)
    # If we found a numeric answer in code output, add a concluding step.
    if last_numeric_answer and steps:
        i += 1
        steps.append(ProofStep(
            step=i, statement=f"计算结果: {last_numeric_answer}",
            reason="由 execute_code 输出", verified=True,
        ))
    if not steps and gs.statement:
        steps.append(ProofStep(step=1, statement=gs.statement, reason="未解出", verified=False))
    return ProofPlan(plan=steps, goal=gs, tool_calls=tool_log)


__all__ = ["cot_reason", "parse_plan", "goal_spec", "infer_goal"]
