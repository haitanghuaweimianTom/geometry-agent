"""Unit tests for the Symbolic Solver (design/08)."""

from __future__ import annotations

import math

import pytest

from geometry_agent.config import SolverConfig
from geometry_agent.solver.engine import SymbolicSolver, _selfcheck_equations
from geometry_agent.solver.rule_engine import BUILTIN_RULES, forward_chain
from geometry_agent.solver.sympy_engine import solve_equations
from geometry_agent.theorems.db import TheoremDB
from geometry_agent.types import (
    Edge,
    GeometryGraph,
    GoalSpec,
    Node,
    NodeType,
    ProofPlan,
    ProofStep,
    RelType,
    ToolCall,
    VerifyState,
)


# --------------------------------------------------------------------------- #
# 1. SymPy: ratio equation -> cross-multiplied goal
# --------------------------------------------------------------------------- #
def test_solve_equations_ratio_goal_verified():
    res = solve_equations(["AB/AC = AE/AD"], "AB*AC = AD*AE")
    assert res["verified"] is True
    assert isinstance(res["solution"], dict)


def test_solve_equations_contradictory_goal():
    res = solve_equations(["x+1=2"], "x=5")
    assert res["verified"] is False


def test_solve_equations_simple_goal():
    res = solve_equations(["x+1=2"], "x=1")
    assert res["verified"] is True
    assert res["solution"].get("x") == "1"


# --------------------------------------------------------------------------- #
# 2. rule_engine: On + Tangent -> Perpendicular(OA, AB) via R2
# --------------------------------------------------------------------------- #
CENTER = (180.0, 160.0)
R = 75.5
A = (180.0, 84.5)
B = (260.0, 84.5)


def _tangent_graph() -> GeometryGraph:
    nodes = [
        Node(id="P_A", type=NodeType.POINT, label="A", attrs={"coords": list(A)}),
        Node(id="P_O", type=NodeType.POINT, label="O", attrs={"coords": list(CENTER)}),
        Node(id="P_B", type=NodeType.POINT, label="B", attrs={"coords": list(B)}),
        Node(
            id="C_O",
            type=NodeType.CIRCLE,
            label="O",
            attrs={"center": list(CENTER), "radius": R},
        ),
        Node(
            id="L_AB",
            type=NodeType.SEGMENT,
            label="AB",
            attrs={"endpoints": [list(A), list(B)],
                   "length": math.hypot(B[0] - A[0], B[1] - A[1])},
        ),
        Node(
            id="L_OA",
            type=NodeType.SEGMENT,
            label="OA",
            attrs={"endpoints": [list(CENTER), list(A)], "length": R},
        ),
    ]
    edges = [
        Edge(src="P_A", dst="C_O", rel=RelType.ON, verified=VerifyState.TRUE),
        Edge(
            src="L_AB", dst="C_O", rel=RelType.TANGENT, verified=VerifyState.TRUE,
            attrs={"tangent_point": "P_A"},
        ),
    ]
    return GeometryGraph(nodes=nodes, edges=edges)


def test_forward_chain_tangent_radius_perp():
    g = _tangent_graph()
    r2 = next(r for r in BUILTIN_RULES if r.rule_id == "R2")
    forward_chain(g, [r2], max_iter=5)
    keys = {(e.src, e.dst, e.rel) for e in g.edges}
    assert ("L_OA", "L_AB", RelType.PERPENDICULAR) in keys
    perp = next(e for e in g.edges if e.rel == RelType.PERPENDICULAR)
    assert perp.source == "derived"
    assert perp.verified == VerifyState.TRUE


# --------------------------------------------------------------------------- #
# 3. TheoremDB.search("圆周角") returns non-empty
# --------------------------------------------------------------------------- #
def test_theorem_db_search_circle_angle():
    db = TheoremDB()
    results = db.search("圆周角")
    assert len(results) > 0
    assert any("圆周角" in t.name for t in results)


def test_theorem_db_all_nonempty():
    db = TheoremDB()
    assert len(db.all_theorems()) >= 15


# --------------------------------------------------------------------------- #
# 4. SymbolicSolver.solve produces a Solution with non-empty proof
# --------------------------------------------------------------------------- #
def test_symbolic_solver_solve_simple_plan():
    solver = SymbolicSolver(SolverConfig())
    plan = ProofPlan(
        goal=GoalSpec(kind="Solve", statement="求 x 的值"),
        plan=[
            ProofStep(
                step=1,
                statement="由方程 x+1=2 解得 x=1",
                reason="solve_equations",
                tool_call=ToolCall(
                    name="solve",
                    args={"equations": ["x+1=2"], "goal": "x=1"},
                ),
            ),
        ],
    )
    graph = _tangent_graph()
    sol = solver.solve(plan, graph)
    assert sol.proof, "proof must be non-empty"
    assert len(sol.proof) == 1
    assert sol.proof[0].verified is True
    assert sol.confidence == pytest.approx(1.0)
    assert sol.verified is True


def test_symbolic_solver_solve_equations_tool():
    solver = SymbolicSolver(SolverConfig())
    res = solver.solve_equations(["AB/AC = AE/AD"], "AB*AC = AD*AE")
    assert res["verified"] is True


# --------------------------------------------------------------------------- #
# 5. Equation self-check (algebraic transcription typos)
# --------------------------------------------------------------------------- #
def test_selfcheck_accepts_identity():
    verdict, note = _selfcheck_equations("由 (a+1)^2 = a^2+2*a+1 展开")
    assert verdict is True
    assert note == ""


def test_selfcheck_rejects_wrong_identity():
    verdict, note = _selfcheck_equations("由 (a+1)^2 = a^2+3*a+1 展开")
    assert verdict is False
    assert "self-check" in note


def test_selfcheck_skips_definition_and_solve_equations():
    # c = 1 is a definition, x+1=2 is a solve-equation: neither is an identity
    assert _selfcheck_equations("c = 1")[0] in (None, True)
    assert _selfcheck_equations("由 x+1=2 得 x=1")[0] in (None, True)


def test_selfcheck_skips_function_value_and_param_definitions():
    assert _selfcheck_equations("f(a_min)**2 = (47+21*sqrt(5))/2")[0] in (None, True)
    assert _selfcheck_equations("S1/S2 = 2a*(a**2+1)/(a**2-1)")[0] in (None, True)


def test_selfcheck_catches_numeric_equality():
    verdict, note = _selfcheck_equations("答案 6 = 2+4")
    assert verdict is True


def test_solver_selfcheck_downgrades_wrong_step():
    solver = SymbolicSolver(SolverConfig())
    plan = ProofPlan(
        goal=GoalSpec(kind="Solve", statement="展开 (a+1)^2"),
        plan=[
            ProofStep(
                step=1,
                statement="展开得 (a+1)^2 = a^2+3*a+1",
                reason="expand",
                verified=True,
            ),
        ],
    )
    graph = _tangent_graph()
    sol = solver.solve(plan, graph)
    assert sol.proof[0].verified is False
    assert "self-check" in sol.proof[0].reason
    assert sol.verified is False


def test_solver_selfcheck_keeps_correct_step():
    solver = SymbolicSolver(SolverConfig())
    plan = ProofPlan(
        goal=GoalSpec(kind="Solve", statement="展开 (a+1)^2"),
        plan=[
            ProofStep(
                step=1,
                statement="展开得 (a+1)^2 = a^2+2*a+1",
                reason="expand",
                verified=True,
            ),
        ],
    )
    graph = _tangent_graph()
    sol = solver.solve(plan, graph)
    assert sol.proof[0].verified is True
    assert sol.verified is True
