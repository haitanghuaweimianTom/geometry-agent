"""SymPy algebra engine (design/08 §4).

Solves equation groups expressed as human-readable strings (e.g. ``"AB/AC = AE/AD"``)
and verifies an optional goal proposition. Verification semantics: the goal is
considered *verified* iff the system ``equations ∧ goal`` is jointly satisfiable
(i.e. consistent and admits at least one real assignment). For fully determined
systems this coincides with classical truth; for under-determined systems it acts
as a consistency check (matches design/08 §4.3 example).
"""

from __future__ import annotations

from typing import Any

try:
    import sympy as sp
    from sympy.parsing.sympy_parser import parse_expr

    _SYMPY_OK = True
except Exception:
    _SYMPY_OK = False


def _extract_symbols(exprs: list["sp.Expr"]) -> list["sp.Symbol"]:
    syms: set["sp.Symbol"] = set()
    for e in exprs:
        syms |= e.free_symbols
    return sorted(syms, key=lambda s: s.name)


def _to_expr(s: str) -> "sp.Expr":
    if "=" in s:
        lhs, rhs = s.split("=", 1)
        return parse_expr(lhs) - parse_expr(rhs)
    return parse_expr(s)


def _normalize(solutions: Any) -> list[dict]:
    if not solutions:
        return []
    if isinstance(solutions, dict):
        return [solutions]
    if isinstance(solutions, list):
        out: list[dict] = []
        for s in solutions:
            if isinstance(s, dict):
                out.append(s)
            elif isinstance(s, tuple):
                out.append(dict(zip(_extract_symbols([]), s)))
        return out
    return []


def solve_equations(equations: list[str], goal: str | None = None) -> dict:
    """Solve a system of equations and verify an optional goal.

    Returns ``{"verified": bool, "solution": dict, "reason": str}``.
    """
    if not _SYMPY_OK:
        return {"verified": False, "solution": {}, "reason": "sympy unavailable"}

    if not equations and goal is None:
        return {"verified": True, "solution": {}, "reason": "nothing to solve"}

    try:
        eq_exprs = [_to_expr(e) for e in equations]
        all_exprs = list(eq_exprs)
        goal_expr = None
        if goal:
            goal_expr = _to_expr(goal)
            all_exprs.append(goal_expr)
        syms = _extract_symbols(all_exprs)

        if not syms:
            no_vars = all(sp.simplify(e) == 0 for e in eq_exprs)
            if goal_expr is not None:
                no_vars = no_vars and (sp.simplify(goal_expr) == 0)
            return {
                "verified": bool(no_vars),
                "solution": {},
                "reason": "no symbols; trivial check",
            }

        if not eq_exprs:
            return {"verified": True, "solution": {}, "reason": "no equations"}

        eq_solutions = _normalize(sp.solve(eq_exprs, syms, dict=True))
        if not eq_solutions:
            return {
                "verified": False,
                "solution": {},
                "reason": "equations unsatisfiable",
            }

        if goal_expr is None:
            sol = {str(k): str(v) for k, v in eq_solutions[0].items()}
            return {"verified": True, "solution": sol, "reason": "equations solved"}

        for s in eq_solutions:
            if sp.simplify(goal_expr.subs(s)) == 0:
                sol = {str(k): str(v) for k, v in s.items()}
                return {
                    "verified": True,
                    "solution": sol,
                    "reason": "goal implied by general solution",
                }

        joint = _normalize(sp.solve(eq_exprs + [goal_expr], syms, dict=True))
        if joint:
            sol = {str(k): str(v) for k, v in joint[0].items()}
            return {
                "verified": True,
                "solution": sol,
                "reason": "goal consistent with equations",
            }
        return {
            "verified": False,
            "solution": {},
            "reason": "goal contradicts equations",
        }
    except Exception as exc:
        return {"verified": False, "solution": {}, "reason": f"sympy error: {exc}"}
