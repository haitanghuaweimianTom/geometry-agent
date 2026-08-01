"""Example: full closed-loop reasoning with GLM-5.2 on a synthesized tangent problem.

Uses the GT PrimitiveSet (with labels) to bypass perception (which needs OCR),
so it isolates the Graph -> Agents -> Verifier -> DSL -> LLM -> Solver loop.

Run:
    python examples/demo_tangent_proof.py
"""
from __future__ import annotations

import time

from geometry_agent.config import load_settings
from geometry_agent.data.synth.generator import SynthGenerator
from geometry_agent.pipeline import GeometryPipeline


def main() -> None:
    settings = load_settings("configs/default.yaml")
    pipeline = GeometryPipeline(settings)

    # 1. Synthesize a "AB tangent to circle O at A" scene (GT primitives carry labels)
    scene = SynthGenerator(rng_seed=7).generate(1, template_names=["circle_tangent"])[0]
    print("=== Scene ===")
    print(f"points: {[(p.id, p.label) for p in scene.primitives.points]}")
    print(f"answer (GT): {scene.answer}")

    # 2. Build graph + extract relations + verify (skipping perception/OCR)
    g = pipeline.graph_builder.build(scene.primitives)
    g = pipeline.verifier.verify(pipeline.agent_scheduler.extract(g), g)
    n_verified = sum(1 for e in g.edges if e.verified.value == "true")
    print(f"\n=== Geometry Graph ===\n{len(g.nodes)} nodes, {n_verified} verified edges")

    # 3. DSL
    dsl = pipeline.dsl_serializer(g, settings.dsl)
    print(f"\n=== DSL ===\n{dsl[:500]}...")

    # 4. LLM reasoning (GLM-5.2 via ai-gateway) + Solver
    print("\n=== LLM Reasoning (GLM-5.2) ===")
    t = time.time()
    plan = pipeline.llm_agent.reason(
        dsl, "如图,AB切圆O于A。求证OA垂直AB。", pipeline._tools(g)
    )
    sol = pipeline.solver.solve(plan, g)
    print(f"({time.time()-t:.1f}s) tool_calls={len(plan.tool_calls)}")

    print("\n=== Solution ===")
    print(f"answer:    {sol.answer}")
    print(f"confidence:{sol.confidence:.2f}  verified: {sol.verified}")
    print("proof:")
    for st in sol.proof:
        print(f"  {st.step}. {st.statement}")
        print(f"     reason: {st.reason}  [verified={st.verified}]")


if __name__ == "__main__":
    main()
