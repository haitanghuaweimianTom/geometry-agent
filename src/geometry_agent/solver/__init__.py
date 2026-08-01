"""Symbolic Solver: SymPy + Z3 + rule engine + Lean bridge (design/08)."""

from __future__ import annotations

from .engine import SymbolicSolver
from .rule_engine import Rule, BUILTIN_RULES, forward_chain
from .sympy_engine import solve_equations
from .z3_engine import check_satisfiable, find_counterexample
from .lean_bridge import verify_proof

__all__ = [
    "SymbolicSolver",
    "Rule",
    "BUILTIN_RULES",
    "forward_chain",
    "solve_equations",
    "check_satisfiable",
    "find_counterexample",
    "verify_proof",
]
