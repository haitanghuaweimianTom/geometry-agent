"""Z3 SMT bridge (design/08 §5).

Provides constraint satisfiability checking and counter-example search. Z3 is an
optional dependency: when unavailable both helpers degrade gracefully
(``check_satisfiable`` → ``"unknown"``, ``find_counterexample`` → ``None``).
"""

from __future__ import annotations

from typing import Any

try:
    import z3 as _z3

    _Z3_OK = True
except Exception:
    _z3 = None
    _Z3_OK = False

try:
    from sympy.parsing.sympy_parser import parse_expr

    _SYMPY_OK = True
except Exception:
    _SYMPY_OK = False


_REL_MAP = {
    "Eq": "__eq__",
    "Ne": "__ne__",
    "Lt": "__lt__",
    "Le": "__le__",
    "Gt": "__gt__",
    "Ge": "__ge__",
}


def _sym_to_z3(expr: Any, env: dict[str, "_z3.ArithRef"]) -> Any:
    if not _SYMPY_OK:
        raise RuntimeError("sympy unavailable")
    if expr.is_Symbol:
        name = str(expr)
        if name not in env:
            env[name] = _z3.Real(name)
        return env[name]
    if expr.is_Integer:
        return _z3.IntVal(int(expr))
    if expr.is_Rational:
        return _z3.RealVal(float(expr))
    if expr.is_Float:
        return _z3.RealVal(float(expr))
    if expr.is_Add:
        args = [_sym_to_z3(a, env) for a in expr.args]
        out = args[0]
        for a in args[1:]:
            out = out + a
        return out
    if expr.is_Mul:
        args = [_sym_to_z3(a, env) for a in expr.args]
        out = args[0]
        for a in args[1:]:
            out = out * a
        return out
    if expr.is_Pow:
        base = _sym_to_z3(expr.base, env)
        exp = expr.exp
        if exp.is_Integer:
            return base ** int(exp)
        return base ** _sym_to_z3(exp, env)
    if expr.is_Relational:
        op = _REL_MAP.get(type(expr).__name__)
        if op is None:
            raise ValueError(f"unsupported relation: {type(expr).__name__}")
        left = _sym_to_z3(expr.lhs, env)
        right = _sym_to_z3(expr.rhs, env)
        return getattr(left, op)(right)
    raise ValueError(f"unsupported expression: {expr!r}")


def _parse_constraint(s: str, env: dict[str, "_z3.ArithRef"]) -> Any:
    expr = parse_expr(s)
    return _sym_to_z3(expr, env)


def check_satisfiable(constraints: list[str]) -> str:
    """Return ``"sat"`` / ``"unsat"`` / ``"unknown"``."""
    if not _Z3_OK or not _SYMPY_OK:
        return "unknown"
    solver = _z3.Solver()
    env: dict[str, _z3.ArithRef] = {}
    try:
        for c in constraints:
            solver.add(_parse_constraint(c, env))
    except Exception:
        return "unknown"
    result = solver.check()
    if result == _z3.sat:
        return "sat"
    if result == _z3.unsat:
        return "unsat"
    return "unknown"


def find_counterexample(constraints: list[str], proposition: str) -> dict | None:
    """Find an assignment satisfying ``constraints ∧ ¬proposition``.

    Returns a ``{var: value}`` dict if a counter-example exists, else ``None``.
    Degrades to ``None`` when Z3 is unavailable or the check is inconclusive.
    """
    if not _Z3_OK or not _SYMPY_OK:
        return None
    solver = _z3.Solver()
    env: dict[str, _z3.ArithRef] = {}
    try:
        for c in constraints:
            solver.add(_parse_constraint(c, env))
        prop = _parse_constraint(proposition, env)
        solver.add(_z3.Not(prop))
    except Exception:
        return None
    if solver.check() != _z3.sat:
        return None
    model = solver.model()
    out: dict[str, float] = {}
    for var in env.values():
        val = model.eval(var, model_completion=True)
        try:
            out[var.name()] = float(val.as_decimal(6).rstrip("?"))
        except Exception:
            out[var.name()] = str(val)
    return out
