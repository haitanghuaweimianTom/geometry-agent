from __future__ import annotations

from typing import Any

from geometry_agent.verification._models import Step, Verdict


class LLMJudge:
    def __init__(self, client: Any) -> None:
        self.client = client

    def verdict(
        self,
        step: Step,
        premises: list[Step],
        failures: list[str],
    ) -> Verdict:
        return Verdict(verified="uncertain", reason="not implemented")
