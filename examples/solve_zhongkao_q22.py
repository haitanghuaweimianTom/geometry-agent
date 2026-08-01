"""Solve the Zhongkao problem from the user's image using the full pipeline.

Problem (题22):
  在Rt△ABC中，∠BAC=90°，AC=2√5，点D在AB上，且BD=3AD，连接CD。
  过点A作CD的垂线交CD于点E，交BC于点F，连接BE，AE=2。
  (1) 求 CE 的长;
  (2) 求证：BD² = 9·DE·DC;
  (3) 求 S△BEF / S△BDE 的值.

The geometry is constructed from the exact coordinates (computed via SymPy from
the given conditions), bypassing the perception layer (which would need SAM for
this complex real image). This exercises the full reasoning + solving stack:
knowledge retrieval -> enhanced LLM agent -> code execution -> symbolic solver.
"""
from __future__ import annotations

import math
import time

from geometry_agent.config import load_settings
from geometry_agent.types import (
    Edge, GeometryGraph, GoalSpec, Node, NodeType, RelType, SolveRequest,
    SolveResponse, VerifyState,
)
from geometry_agent.pipeline import GeometryPipeline
from geometry_agent.graph.builder import GraphBuilder
from geometry_agent.agents.scheduler import AgentScheduler
from geometry_agent.verifier.engine import VerifierEngine
from geometry_agent.perception.orchestrator import GeometryParser
from geometry_agent.types import (
    Point, Line, LineType, LineEquation, PrimitiveSet, PointSource, MetaData,
)

SQRT5 = math.sqrt(5.0)


def build_primitives() -> PrimitiveSet:
    """Construct primitives from the exact solved coordinates."""
    pts = {
        "A": (0.0, 0.0),
        "B": (4 * SQRT5, 0.0),
        "C": (0.0, 2 * SQRT5),
        "D": (SQRT5, 0.0),
        "E": (4 * SQRT5 / 5, 2 * SQRT5 / 5),
        "F": (2 * SQRT5, SQRT5),
    }
    points = [
        Point(id=f"P_{k}", label=k, coords=v, source=PointSource.EXPLICIT)
        for k, v in pts.items()
    ]
    segs = [
        ("AB", "A", "B"), ("AC", "A", "C"), ("BC", "B", "C"),
        ("CD", "C", "D"), ("AE", "A", "E"), ("AF", "A", "F"),
        ("BE", "B", "E"), ("BF", "B", "F"),
    ]
    lines = []
    for lab, p1, p2 in segs:
        x1, y1 = pts[p1]; x2, y2 = pts[p2]
        a = y1 - y2; b = x2 - x1; c = -(a * x1 + b * y1)
        n = math.hypot(a, b)
        lines.append(Line(
            id=f"L_{lab}", label=lab, type=LineType.SEGMENT,
            endpoints=[(x1, y1), (x2, y2)],
            equation=LineEquation(a=a/n, b=b/n, c=c/n),
            length=math.hypot(x2-x1, y2-y1),
        ))
    return PrimitiveSet(
        points=points, lines=lines,
        metadata=MetaData(image_size=(500, 400)),
    )


def build_graph(pipeline: GeometryPipeline) -> GeometryGraph:
    prim = build_primitives()
    g = pipeline.graph_builder.build(prim)
    cands = pipeline.agent_scheduler.extract(g)
    g = pipeline.verifier.verify(cands, g)
    return g


def solve_question(pipeline, g, dsl, question: str, goal_kind: str = "Solve") -> SolveResponse:
    """Solve one sub-question via the enhanced reasoning agent + solver."""
    tools = pipeline._tools(g)
    plan = pipeline.llm_agent.reason(dsl, question, tools)
    sol = pipeline.solver.solve(plan, g)
    return sol


def main() -> None:
    settings = load_settings("configs/default.yaml")
    settings.human_loop.enabled = False  # skip review for batch solve
    pipeline = GeometryPipeline(settings)

    g = build_graph(pipeline)
    dsl = pipeline.dsl_serializer(g, settings.dsl)
    print("=== Geometry Graph ===")
    print(f"nodes={len(g.nodes)} verified_edges={sum(1 for e in g.edges if e.verified.value=='true')}")
    print(dsl[:600])

    problem = (
        "在Rt△ABC中，∠BAC=90°，AC=2√5，点D在AB上，且BD=3AD，连接CD。"
        "过点A作CD的垂线交CD于点E，交BC于点F，连接BE，AE=2。"
    )

    questions = [
        ("(1) 求 CE 的长", "(1) 求 CE 的长"),
        ("(2) 求证 BD² = 9·DE·DC", "(2) 求证 BD² = 9·DE·DC"),
        ("(3) 求 S△BEF / S△BDE 的值", "(3) 求 S△BEF / S△BDE 的值"),
    ]

    for title, q in questions:
        print(f"\n{'='*60}\n{title}\n{'='*60}")
        t = time.time()
        full_q = problem + q
        try:
            sol = solve_question(pipeline, g, dsl, full_q)
            print(f"({time.time()-t:.1f}s) confidence={sol.confidence:.2f} verified={sol.verified}")
            print(f"answer: {sol.answer}")
            for st in sol.proof:
                print(f"  {st.step}. {st.statement}")
                if st.reason:
                    print(f"     理由: {st.reason}")
        except Exception as e:
            print(f"失败: {e!r}")


if __name__ == "__main__":
    main()
