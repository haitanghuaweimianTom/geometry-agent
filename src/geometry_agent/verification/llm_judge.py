"""LLM judge step-verifier: asks the chat client whether a failing step is actually valid."""

from __future__ import annotations

import json
import re
from typing import Any

from geometry_agent.types import VerifyState
from geometry_agent.verification._models import Step, Verdict


_SYSTEM_PROMPT = (
    "You are a strict mathematical proof reviewer. Given premises and a proposed "
    "conclusion that failed automatic verification three times, judge whether the "
    "conclusion is valid. Reply with a single JSON object: "
    "{\"verdict\":\"true|false|uncertain\",\"reason\":\"<brief justification>\"}."
)

_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


class LLMJudge:
    def __init__(self, client: Any) -> None:
        self.client = client

    def judge(
        self,
        step: Step,
        premises: list[Step],
        failures: list[str],
    ) -> Verdict:
        premises_text = "\n".join(f"- {p.id}: {p.statement}" for p in premises) if premises else "(none)"
        failures_text = "\n".join(f"- {f}" for f in failures) if failures else "(none)"
        conclusion_text = step.statement
        if step.justification:
            conclusion_text = f"{step.statement}\nJustification: {step.justification}"

        user_msg = (
            "Premises:\n"
            f"{premises_text}\n\n"
            "Proposed conclusion:\n"
            f"- {step.id}: {conclusion_text}\n\n"
            "Previous verification failures:\n"
            f"{failures_text}\n\n"
            "Is the conclusion valid given the premises? Reply with JSON only."
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        try:
            resp = self.client.chat(messages, temperature=0.0)
            content = resp["choices"][0]["message"]["content"]
        except Exception as exc:
            return Verdict(
                verified=VerifyState.UNCERTAIN,
                evidence="",
                reason=f"llm judge client error: {exc}",
            )

        m = _JSON_RE.search(content)
        if not m:
            return Verdict(
                verified=VerifyState.UNCERTAIN,
                evidence=content,
                reason="could not parse judge reply: no JSON object found",
            )
        try:
            parsed = json.loads(m.group(0))
            verdict = str(parsed.get("verdict", "")).lower()
            reason = str(parsed.get("reason", ""))
        except (json.JSONDecodeError, TypeError):
            return Verdict(
                verified=VerifyState.UNCERTAIN,
                evidence=content,
                reason="could not parse judge reply: invalid JSON",
            )

        if verdict == "true":
            return Verdict(verified=VerifyState.TRUE, evidence=content, reason=reason)
        if verdict == "false":
            return Verdict(verified=VerifyState.FALSE, evidence=content, reason=reason)
        return Verdict(
            verified=VerifyState.UNCERTAIN,
            evidence=content,
            reason=reason or "could not parse judge reply: verdict not true/false",
        )
