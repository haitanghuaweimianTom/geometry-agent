"""Self-reflection on failure (design/07 §3.3, §6).

When a verification step fails, the LLM is asked to analyse the failure and
emit a revised plan. Capped at ``max_reflections`` rounds by the caller.
"""

from __future__ import annotations

import json
from typing import Any

from ..types import ProofPlan
from .cot import _extract_json, parse_plan
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS


def reflect(client: Any, failure: Any, plan: Any, history: Any) -> ProofPlan:
    """Produce a revised :class:`ProofPlan` after a failure.

    ``plan`` may be a :class:`ProofPlan`, a dict, or None. On offline/error the
    original plan is returned unchanged.
    """
    if isinstance(plan, dict):
        try:
            plan = ProofPlan(**plan)
        except Exception:
            plan = ProofPlan()
    if not isinstance(plan, ProofPlan):
        plan = ProofPlan()

    if getattr(client, "is_offline", False):
        return plan

    plan_text = plan.model_dump_json(indent=2) if plan.plan else "(empty plan)"
    history_text = _fmt_history(history)

    prompt = (
        "[Reflection]\n"
        f"Previous failure: {failure or 'unknown'}\n\n"
        f"Current plan:\n{plan_text}\n\n"
        f"History:\n{history_text}\n\n"
        "Analyse the failure (wrong theorem / unverified relation / planning error) "
        "and produce a REVISED proof plan. Output ONLY a JSON object:\n"
        '{"plan":[{"step":1,"statement":"...","reason":"...","verified":true}],'
        '"goal":{"kind":"Prove","statement":"..."}}\n'
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT or "You are a geometry proof expert."},
        {"role": "user", "content": prompt},
    ]

    try:
        resp = client.chat(messages, tools=TOOL_SCHEMAS, temperature=0.5)
    except Exception:
        return plan

    if resp is None or resp.get("offline"):
        return plan

    choice = (resp.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""

    raw = _extract_json(content)
    if not raw:
        return plan
    try:
        json.loads(raw)
    except Exception:
        return plan

    new_plan = parse_plan(content, plan.goal)
    if not new_plan.plan:
        return plan
    return new_plan


def _fmt_history(history: Any) -> str:
    if not history:
        return "(none)"
    try:
        return json.dumps(history, ensure_ascii=False, default=str)[:2000]
    except Exception:
        return str(history)[:2000]


__all__ = ["reflect"]
