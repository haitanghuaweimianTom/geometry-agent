"""Solve Zhongkao Q22 with pure plane-geometry (junior-high) methods, no coordinates.

Problem:
  在Rt△ABC中，∠BAC=90°，AC=2√5，点D在AB上，BD=3AD，连接CD。
  过A作CD的垂线交CD于E，交BC于F，连接BE，AE=2。
  (1) 求 CE 的长;
  (2) 求证 BD² = 9·DE·DC;
  (3) 求 S△BEF / S△BDE 的值.

Methods used (all junior-high plane geometry, NO coordinates):
  (1) 射影定理 (Rt△ 斜边上的高)
  (2) 射影定理 + BD=3AD
  (3) 共高定理 / 同底等高 + 相似三角形面积比

The graph is built from the given conditions (pure geometric construction, the
coordinates are only used internally by the verifier to check relations, NOT
exposed to the LLM as a coordinate method).
"""
from __future__ import annotations

import math
import time

from geometry_agent.config import load_settings
from geometry_agent.types import (
    Point, Line, LineType, LineEquation, PrimitiveSet, PointSource, MetaData,
)
from geometry_agent.pipeline import GeometryPipeline
from geometry_agent.graph.builder import GraphBuilder
from geometry_agent.agents.scheduler import AgentScheduler
from geometry_agent.verifier.engine import VerifierEngine
from geometry_agent.human_loop.pdf_compiler import solution_to_pdf

SQRT5 = math.sqrt(5.0)


def build_primitives() -> PrimitiveSet:
    """Construct primitives. Coordinates are internal-only (for the verifier's
    numerical checks); the LLM is told to use plane-geometry methods."""
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
        ("BE", "B", "E"), ("BF", "B", "F"), ("EF", "E", "F"),
        ("DE", "D", "E"),
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


PLANE_GEOMETRY_HINT = """
【重要】本题是初中平面几何题，必须使用初中课内平面几何方法求解，禁止使用坐标法/解析几何。
可用方法：射影定理、相似三角形、勾股定理、面积法、共高/共底定理、平行线分线段成比例等。
"""


def solve_one(pipeline, g, dsl, problem, question, out_pdf):
    tools = pipeline._tools(g)
    full = problem + "\n" + PLANE_GEOMETRY_HINT + "\n" + question
    t = time.time()
    plan = pipeline.llm_agent.reason(dsl, full, tools)
    sol = pipeline.solver.solve(plan, g)
    # Generate PDF report
    try:
        solution_to_pdf(problem + "\n" + question, sol, g, out_pdf,
                        title="初中几何题解答（平面几何方法）")
    except Exception as e:
        print(f"  PDF 生成失败: {e}")
    print(f"  ({time.time()-t:.1f}s) conf={sol.confidence:.2f} verified={sol.verified}")
    print(f"  answer: {sol.answer[:100]}")
    for st in sol.proof:
        print(f"    {st.step}. {st.statement[:75]} [v={st.verified}]")
    return sol


def main():
    settings = load_settings("configs/default.yaml")
    settings.human_loop.enabled = False
    pipeline = GeometryPipeline(settings)

    prim = build_primitives()
    g = pipeline.graph_builder.build(prim)
    g = pipeline.verifier.verify(pipeline.agent_scheduler.extract(g), g)
    dsl = pipeline.dsl_serializer(g, settings.dsl)

    problem = (
        "在Rt△ABC中，∠BAC=90°，AC=2√5，点D在AB上，且BD=3AD，连接CD。"
        "过点A作CD的垂线交CD于点E，交BC于点F，连接BE，AE=2。"
    )

    print("="*60)
    print("(1) 求 CE 的长")
    print("="*60)
    sol1 = solve_one(pipeline, g, dsl, problem,
                     "(1) 求 CE 的长。（用平面几何方法，不要用坐标）",
                     "outputs/q1_ce.pdf")

    print("\n" + "="*60)
    print("(2) 求证 BD² = 9·DE·DC")
    print("="*60)
    sol2 = solve_one(pipeline, g, dsl, problem,
                     "(2) 求证 BD² = 9·DE·DC。（用平面几何方法，不要用坐标）",
                     "outputs/q2_proof.pdf")

    print("\n" + "="*60)
    print("(3) 求 S△BEF / S△BDE 的值")
    print("="*60)
    sol3 = solve_one(pipeline, g, dsl, problem,
                     "(3) 求 S△BEF / S△BDE 的值。（用平面几何方法，如共高定理、相似三角形面积比，不要用坐标）",
                     "outputs/q3_ratio.pdf")

    print("\n=== PDF 报告 ===")
    print("outputs/q1_ce.pdf")
    print("outputs/q2_proof.pdf")
    print("outputs/q3_ratio.pdf")


if __name__ == "__main__":
    main()
