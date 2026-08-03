"""Symbolic Solver orchestrator (design/08 §2, §8).

Integrates the SymPy engine, Z3 bridge and the self-contained rule engine. The
LLM Reasoning Agent emits a :class:`ProofPlan`; the solver enriches the graph
via forward-chaining, then verifies/executes each :class:`ProofStep` (and any
attached :class:`ToolCall`), producing a :class:`Solution`.
"""

from __future__ import annotations

import random
import re
from typing import Any

import sympy as sp

from ..config import SolverConfig
from ..types import (
    GeometryGraph,
    ProofPlan,
    ProofStep,
    Solution,
    ToolCall,
)
from .rule_engine import BUILTIN_RULES, forward_chain
from .sympy_engine import solve_equations as _sympy_solve
from .z3_engine import check_satisfiable as _z3_check
from .z3_engine import find_counterexample as _z3_counter

_MATH_CHARS = re.compile(r"[0-9A-Za-z_αβγδεθπφω√·×²³⁴⁄+\-*/^().\[\]]")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _normalize_math(s: str) -> str:
    """Map common unicode math glyphs to sympy-parseable ASCII."""
    s = s.replace("×", "*").replace("·", "*").replace("−", "-").replace("﹣", "-")
    s = s.replace("²", "**2").replace("³", "**3").replace("√", "sqrt")
    s = re.sub(r"(\d)⁴", r"\1**4", s)
    s = re.sub(r"([A-Za-z])(\d)", r"\1_\2", s)  # S1 -> S_1
    return s


def _math_run(s: str) -> str | None:
    """Return the longest contiguous math-token run in ``s``, or None."""
    m = re.findall(f"{_MATH_CHARS.pattern}+", s)
    return m[-1].strip() if m else None


def _find_equations(statement: str) -> list[tuple[str, str]]:
    """Extract ``lhs = rhs`` pairs whose sides are clean pure-math token runs.

    Only yields pairs that can be verified without ambiguity: both sides are
    contiguous math runs (no CJK inside), so definitions like ``c = 1`` and
    solve-equations like ``x + 1 = 2`` are naturally filtered out when the
    ``=`` sides are not both self-contained math expressions.
    """
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"=", statement):
        left = statement[: m.start()].rstrip()
        right = statement[m.start() + 1 :].lstrip()
        lhs = _math_run(left)
        rhs = _math_run(right)
        if not lhs or not rhs:
            continue
        if _CJK.search(lhs) or _CJK.search(rhs):
            continue
        out.append((lhs, rhs))
    return out


def _verify_equation(lhs: str, rhs: str) -> bool | None:
    """Verify ``lhs = rhs`` as an identity. True / False / None (undecidable).

    Requires at least one free symbol shared between both sides (so pure
    definitions and constant assignments are skipped), then checks symbolically
    and falls back to numeric sampling.
    """
    try:
        le = sp.sympify(_normalize_math(lhs))
        re_ = sp.sympify(_normalize_math(rhs))
    except Exception:
        return None
    shared = le.free_symbols & re_.free_symbols
    if not shared:
        return None
    try:
        diff = sp.simplify(le - re_)
        if diff == 0:
            return True
        if not diff.free_symbols:
            return abs(float(diff)) < 1e-9
        rng = random.Random(42)
        for _ in range(5):
            subs = {s_: rng.randint(1, 5) for s_ in diff.free_symbols}
            try:
                if abs(float(diff.subs(subs))) > 1e-6:
                    return False
            except (TypeError, ValueError):
                pass
        return None
    except Exception:
        return None


def _selfcheck_equations(statement: str) -> tuple[bool | None, str]:
    """Cross-check equations embedded in a step statement.

    Returns ``(result, note)`` where result is True (all passed), False (a
    definite violation was found) or None (nothing verifiable).
    """
    pairs = _find_equations(statement)
    if not pairs:
        return None, ""
    for lhs, rhs in pairs:
        verdict = _verify_equation(lhs, rhs)
        if verdict is False:
            return False, f"equation self-check failed: {lhs} != {rhs}"
    return True, ""


class SymbolicSolver:
    """Coordinates SymPy / Z3 / rule-engine to materialise a Solution."""

    def __init__(self, config: SolverConfig | None = None):
        self.config = config or SolverConfig()
        self._rules = list(BUILTIN_RULES) if self.config.rule_engine_enabled else []
        self._db = None
        try:
            from ..theorems.db import TheoremDB

            self._db = TheoremDB(self.config.theorem_db_path)
        except Exception:
            self._db = None

    # ------------------------------------------------------------------ #
    # LLM-facing tool: solve_equations(equations, goal)
    # ------------------------------------------------------------------ #
    def solve_equations(self, equations: list[str], goal: str | None = None) -> dict:
        if not self.config.sympy_enabled:
            return {"verified": False, "solution": {}, "reason": "sympy disabled"}
        return _sympy_solve(equations, goal)

    def check_satisfiable(self, constraints: list[str]) -> str:
        if not self.config.z3_enabled:
            return "unknown"
        return _z3_check(constraints)

    def find_counterexample(self, constraints: list[str], proposition: str) -> dict | None:
        if not self.config.z3_enabled:
            return None
        return _z3_counter(constraints, proposition)

    # ------------------------------------------------------------------ #
    # main entry: solve(plan, graph) -> Solution
    # ------------------------------------------------------------------ #
    def solve(self, plan: ProofPlan, graph: GeometryGraph) -> Solution:
        log: list[dict[str, Any]] = []
        working = graph.model_copy(deep=True)

        if self.config.rule_engine_enabled and self._rules:
            before = len(working.edges)
            working = forward_chain(working, self._rules, max_iter=10)
            log.append({
                "step": "forward_chain",
                "rules": [r.rule_id for r in self._rules],
                "edges_before": before,
                "edges_after": len(working.edges),
            })

        verified_steps: list[ProofStep] = []
        verified_count = 0
        for st in plan.plan:
            new_step, ok = self._verify_step(st, working)
            if self.config.equation_selfcheck_enabled:
                verdict, note = _selfcheck_equations(st.statement)
                if verdict is False:
                    new_step = new_step.model_copy(update={
                        "verified": False,
                        "reason": (new_step.reason or note) + f"; {note}",
                    })
                    ok = False
                    log.append({"step": f"selfcheck:{st.step}", "note": note})
            verified_steps.append(new_step)
            if ok:
                verified_count += 1

        total = len(verified_steps)
        confidence = (verified_count / total) if total else 0.0
        all_verified = bool(verified_steps) and verified_count == total

        answer = ""
        if plan.goal and plan.goal.statement:
            answer = plan.goal.statement
        if verified_steps and verified_steps[-1].verified:
            if not answer:
                answer = verified_steps[-1].statement
        elif verified_steps and not answer:
            answer = verified_steps[-1].statement

        reasoning_path = " -> ".join(
            s.statement for s in verified_steps if s.statement
        )

        return Solution(
            answer=answer,
            proof=verified_steps,
            confidence=confidence,
            verified=all_verified,
            geometry_graph=working,
            verification_log=log,
            reasoning_path=reasoning_path,
        )

    # ------------------------------------------------------------------ #
    # per-step verification
    # ------------------------------------------------------------------ #
    def _verify_step(self, step: ProofStep, graph: GeometryGraph) -> tuple[ProofStep, bool]:
        tc = step.tool_call
        # Steps already verified True by the LLM during the CoT tool-calling
        # loop (verify/search were actually invoked there) are trusted. The
        # solver only independently re-runs its own symbolic tools below.
        if tc is None or tc.name in ("verify", "search", "graph_query", "reflect"):
            return step.model_copy(), bool(step.verified)
        return self._run_tool(step, tc, graph)

    def _run_tool(self, step: ProofStep, tc: ToolCall, graph: GeometryGraph) -> tuple[ProofStep, bool]:
        name = tc.name
        args = tc.args or {}

        if name == "solve":
            equations = list(args.get("equations") or [])
            goal = args.get("goal")
            res = self.solve_equations(equations, goal)
            new_tc = tc.model_copy(update={"result": res})
            ok = bool(res.get("verified"))
            reason = step.reason or res.get("reason", "")
            return step.model_copy(update={"verified": ok, "tool_call": new_tc, "reason": reason}), ok

        if name == "check_satisfiable":
            constraints = list(args.get("constraints") or [])
            res = self.check_satisfiable(constraints)
            new_tc = tc.model_copy(update={"result": res})
            ok = res == "sat"
            return step.model_copy(update={"verified": ok, "tool_call": new_tc,
                                            "reason": step.reason or f"z3:{res}"}), ok

        if name == "find_counterexample":
            constraints = list(args.get("constraints") or [])
            proposition = args.get("proposition", "")
            res = self.find_counterexample(constraints, proposition)
            new_tc = tc.model_copy(update={"result": res})
            ok = res is None
            return step.model_copy(update={"verified": ok, "tool_call": new_tc,
                                            "reason": step.reason or "no counterexample"}), ok

        new_tc = tc.model_copy(update={"result": {"error": f"unknown tool: {name}"}})
        return step.model_copy(update={"tool_call": new_tc}), False
