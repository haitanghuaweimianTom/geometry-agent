"""Symbolic (algebraic) step-verifier backend using SymPy with timeout."""

from __future__ import annotations

import threading
from typing import Any, Optional

import sympy as sp

from geometry_agent.types import VerifyState
from geometry_agent.verification._models import Step, Verdict
from geometry_agent.verification.step_parser import parse_claim


class _Result:
    __slots__ = ("value", "exc", "timed_out")

    def __init__(self) -> None:
        self.value: Any = None
        self.exc: Optional[BaseException] = None
        self.timed_out: bool = False


def _run_with_timeout(fn, timeout_s: float) -> _Result:
    res = _Result()
    done = threading.Event()

    def target():
        try:
            res.value = fn()
        except BaseException as e:  # noqa: BLE001
            res.exc = e
        finally:
            done.set()

    t = threading.Thread(target=target, daemon=True)
    t.start()
    finished = done.wait(timeout_s)
    if not finished:
        res.timed_out = True
    return res


class SymbolicStepVerifier:
    def __init__(self, timeout_ms: int = 200) -> None:
        self.timeout_ms = timeout_ms

    def _collect_premises(self, premises: list[Step]):
        eq_premises = []
        assumptions = []
        for p in premises:
            parsed = parse_claim(p.statement)
            if parsed is None:
                continue
            plhs, prel, prhs = parsed
            rel_obj = prel(plhs, prhs)
            assumptions.append(rel_obj)
            if prel is sp.Eq:
                eq_premises.append((plhs, prhs))
        return assumptions, eq_premises

    def verify(self, step: Step, premises: list[Step]) -> Verdict:
        parsed = parse_claim(step.statement)
        if parsed is None:
            return Verdict(
                verified=VerifyState.UNCERTAIN,
                reason="could not parse step as algebraic claim",
            )
        lhs, rel, rhs = parsed

        assumptions, eq_premises = self._collect_premises(premises)
        timeout_s = self.timeout_ms / 1000.0

        if rel is sp.Eq:
            def _compute():
                diff = lhs - rhs
                # Try simplify first
                s = sp.simplify(diff, assumptions=assumptions)
                if s == 0:
                    return s
                # Try expand
                e = sp.expand(diff)
                if e == 0:
                    return e
                # Try substituting solutions from premise equalities (best-effort, single-variable solves)
                diff2 = diff
                for plhs, prhs in eq_premises:
                    eq = sp.Eq(plhs, prhs)
                    free = eq.free_symbols
                    if len(free) == 1:
                        sym = next(iter(free))
                        try:
                            sol = sp.solve(eq, sym)
                        except Exception:
                            sol = []
                        for sv in sol:
                            subbed = sp.simplify(diff2.subs(sym, sv))
                            if subbed == 0:
                                return subbed
                            diff2 = subbed
                return s

            res = _run_with_timeout(_compute, timeout_s)
            return _judge_eq(res)
        else:
            def _compute():
                return sp.simplify(rel(lhs, rhs), assumptions=assumptions)

            res = _run_with_timeout(_compute, timeout_s)
            return _judge_rel(res)


def _judge_eq(res: _Result) -> Verdict:
    if res.timed_out:
        return Verdict(verified=VerifyState.UNCERTAIN, reason="timeout")
    if res.exc is not None:
        return Verdict(verified=VerifyState.UNCERTAIN, reason=f"simplify raised: {res.exc}")
    diff = res.value
    if diff == 0:
        return Verdict(
            verified=VerifyState.TRUE,
            evidence=f"simplified(lhs-rhs)=0 -> {diff}",
        )
    # Detect provably non-zero: constant and non-zero, or expand gives non-zero constant
    if diff.is_constant() and diff != 0:
        return Verdict(
            verified=VerifyState.FALSE,
            evidence=f"lhs-rhs = {diff} != 0",
        )
    # Try expanded form to see if it's a nonzero polynomial identity
    try:
        e = sp.expand(diff)
        if e.is_constant() and e != 0:
            return Verdict(
                verified=VerifyState.FALSE,
                evidence=f"lhs-rhs = {e} != 0",
            )
    except Exception:
        pass
    # Free-variable expression: diff has free symbols. For a polynomial identity
    # claim (typical in exam solutions: algebraic identities in arbitrary variables),
    # if the expanded form is a nonzero polynomial, the identity is FALSE.
    try:
        e = sp.expand(diff)
        if e != 0 and not getattr(e, "free_symbols", None):
            return Verdict(
                verified=VerifyState.FALSE,
                evidence=f"lhs-rhs = {e} != 0",
            )
        # nonzero polynomial in free vars → not an identity
        if e != 0 and bool(getattr(e, "free_symbols", set())):
            # Test a random numeric substitution to confirm non-identity
            try:
                syms = list(e.free_symbols)
                sub = {s: (i + 1) * sp.Rational(3, 2) for i, s in enumerate(syms)}
                val = sp.N(e.subs(sub))
                if val != 0:
                    return Verdict(
                        verified=VerifyState.FALSE,
                        evidence=f"lhs-rhs = {e} != 0 (not an identity)",
                    )
            except Exception:
                pass
    except Exception:
        pass
    if getattr(diff, "is_zero", None) is False:
        return Verdict(
            verified=VerifyState.FALSE,
            evidence=f"lhs-rhs = {diff} != 0",
        )
    return Verdict(
        verified=VerifyState.UNCERTAIN,
        reason=f"could not simplify difference to 0 (got {diff})",
    )


def _judge_rel(res: _Result) -> Verdict:
    if res.timed_out:
        return Verdict(verified=VerifyState.UNCERTAIN, reason="timeout")
    if res.exc is not None:
        return Verdict(verified=VerifyState.UNCERTAIN, reason=f"simplify raised: {res.exc}")
    val = res.value
    if val is sp.S.true:
        return Verdict(verified=VerifyState.TRUE, evidence="simplified relation -> True")
    if val is sp.S.false:
        return Verdict(verified=VerifyState.FALSE, evidence="simplified relation -> False")
    return Verdict(
        verified=VerifyState.UNCERTAIN,
        reason=f"could not simplify relation to True/False (got {val})",
    )
