"""Symbolic (algebraic) step-verifier backend using SymPy with timeout."""

from __future__ import annotations

import random
import threading
from typing import Any, Optional

import sympy as sp

from geometry_agent.types import VerifyState
from geometry_agent.verification._models import Step, Verdict
from geometry_agent.verification.step_parser import parse_claim


_GEOMETRIC_KEYWORDS = ("平行", "∥", "垂直", "⊥", "共线")


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
        stmt = step.statement or ""
        for kw in _GEOMETRIC_KEYWORDS:
            if kw in stmt:
                return Verdict(
                    verified=VerifyState.UNCERTAIN,
                    reason="geometric relation (keyword), not verified by symbolic engine",
                )

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
                s = sp.simplify(diff, assumptions=assumptions)
                if s == 0:
                    return s
                e = sp.expand(diff)
                if e == 0:
                    return e
                diff2 = diff
                solved_subs: dict[Any, Any] = {}
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
                            solved_subs[sym] = sv
                return s, solved_subs, diff, eq_premises

            res = _run_with_timeout(_compute, timeout_s)
            return _judge_eq(res, eq_premises, timeout_s)
        else:
            def _compute():
                return sp.simplify(rel(lhs, rhs), assumptions=assumptions)

            res = _run_with_timeout(_compute, timeout_s)
            return _judge_rel(res)


def _judge_eq(res: _Result, eq_premises=None, timeout_s: float = 0.2) -> Verdict:
    if res.timed_out:
        return Verdict(verified=VerifyState.UNCERTAIN, reason="timeout")
    if res.exc is not None:
        return Verdict(verified=VerifyState.UNCERTAIN, reason=f"simplify raised: {res.exc}")
    value = res.value
    if isinstance(value, tuple) and len(value) == 4:
        diff, solved_subs, orig_diff, all_eq_premises = value
    else:
        diff = value
        solved_subs = {}
        orig_diff = diff
        all_eq_premises = eq_premises or []
    if diff == 0:
        return Verdict(
            verified=VerifyState.TRUE,
            evidence=f"simplified(lhs-rhs)=0 -> {diff}",
        )
    if diff.is_constant() and diff != 0:
        return Verdict(
            verified=VerifyState.FALSE,
            evidence=f"lhs-rhs = {diff} != 0",
        )
    try:
        e = sp.expand(diff)
        if e.is_constant() and e != 0:
            return Verdict(
                verified=VerifyState.FALSE,
                evidence=f"lhs-rhs = {e} != 0",
            )
    except Exception:
        pass
    try:
        e = sp.expand(diff)
        if e != 0 and not getattr(e, "free_symbols", None):
            return Verdict(
                verified=VerifyState.FALSE,
                evidence=f"lhs-rhs = {e} != 0",
            )
        if e != 0 and bool(getattr(e, "free_symbols", set())) and not all_eq_premises:
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

    numeric_verdict = _numeric_cross_check(orig_diff, all_eq_premises, solved_subs, timeout_s)
    if numeric_verdict is not None:
        return numeric_verdict

    return Verdict(
        verified=VerifyState.UNCERTAIN,
        reason=f"could not simplify difference to 0 (got {diff})",
    )


def _numeric_cross_check(diff, eq_premises, solved_subs, timeout_s: float):
    if not eq_premises:
        return None
    try:
        reduced_diff = diff
        for sym, val in solved_subs.items():
            reduced_diff = reduced_diff.subs(sym, val)
        reduced_diff = sp.simplify(reduced_diff)

        eqs = []
        all_symbols = set(reduced_diff.free_symbols)
        for plhs, prhs in eq_premises:
            pe = plhs - prhs
            pe = pe.subs(solved_subs)
            pe = sp.simplify(pe)
            if pe == 0:
                continue
            eqs.append(sp.Eq(pe, 0))
            all_symbols.update(pe.free_symbols)
        syms = sorted(all_symbols, key=str)

        if not syms:
            val = sp.N(reduced_diff)
            if abs(val) < 1e-10:
                return Verdict(verified=VerifyState.TRUE, evidence="numeric cross-check passed")
            if abs(val) > 1e-6:
                return Verdict(verified=VerifyState.FALSE, evidence=f"numeric cross-check: diff={val} != 0")
            return None

        solutions = []
        try:
            sol_result = sp.solve(eqs, syms, dict=True, set=False)
            if isinstance(sol_result, list):
                solutions = sol_result
            elif isinstance(sol_result, dict):
                solutions = [sol_result]
            else:
                solutions = []
        except Exception:
            solutions = []

        if solutions:
            all_zero = True
            any_zero = False
            for sol in solutions:
                try:
                    val = sp.N(reduced_diff.subs(sol))
                except Exception:
                    return None
                if abs(val) > 1e-6:
                    return Verdict(
                        verified=VerifyState.FALSE,
                        evidence=f"numeric cross-check: diff={val} != 0 at satisfying point",
                    )
                if abs(val) < 1e-10:
                    any_zero = True
                else:
                    all_zero = False
            if all_zero and any_zero:
                return Verdict(
                    verified=VerifyState.TRUE,
                    evidence="numeric cross-check passed",
                )

        try:
            f_diff = sp.lambdify(syms, reduced_diff, modules="math")
            f_premises = [sp.lambdify(syms, (eq.lhs - eq.rhs), modules="math") for eq in eqs]
        except Exception:
            return None

        random.seed(42)

        def _try_point(point):
            try:
                for f in f_premises:
                    v = f(*point)
                    if abs(v) > 1e-6:
                        return None
                return f_diff(*point)
            except Exception:
                return None

        true_hits = 0
        false_found = None
        for _ in range(500):
            point = tuple(random.uniform(-5, 5) for _ in syms)
            dv = _try_point(point)
            if dv is None:
                continue
            if abs(dv) > 1e-6:
                false_found = dv
                break
            if abs(dv) < 1e-10:
                true_hits += 1
                if true_hits >= 5:
                    break

        if false_found is not None:
            return Verdict(
                verified=VerifyState.FALSE,
                evidence=f"numeric cross-check: diff={false_found} != 0 at satisfying point",
            )
        if true_hits >= 5:
            return Verdict(
                verified=VerifyState.TRUE,
                evidence="numeric cross-check passed",
            )
        return None
    except Exception:
        return None


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
