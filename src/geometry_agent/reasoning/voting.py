"""Self-consistency voting (design/07 §3.4).

Sample ``n`` independent proof paths at varying temperatures and vote on the
final answer; the most-agreed plan wins.
"""

from __future__ import annotations

from collections import Counter
from typing import Callable

from ..types import ProofPlan


def self_consistency(
    problem: str,
    run_fn: Callable[[float], ProofPlan],
    n: int = 5,
) -> ProofPlan:
    """Run ``run_fn`` at ``n`` temperatures and return the consensus plan."""
    if n <= 1:
        try:
            return run_fn(0.3)
        except Exception:
            return ProofPlan()

    temps = [round(0.3 + 0.15 * i, 3) for i in range(n)]
    plans: list[ProofPlan] = []
    for t in temps:
        try:
            p = run_fn(t)
        except Exception:
            continue
        if isinstance(p, ProofPlan):
            plans.append(p)

    if not plans:
        return ProofPlan()

    answers = [_answer(p) for p in plans]
    counter = Counter(answers)
    best, _ = counter.most_common(1)[0]
    for p, a in zip(plans, answers):
        if a == best:
            return p
    return plans[0]


def _answer(plan: ProofPlan) -> str:
    if plan.goal and plan.goal.statement:
        return plan.goal.statement.strip()
    if plan.plan:
        return plan.plan[-1].statement.strip()
    return ""


__all__ = ["self_consistency"]
