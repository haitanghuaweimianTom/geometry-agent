"""End-to-end integration: human-in-the-loop correction + enhanced reasoning.

Tests the full augmented pipeline:
  GT primitives -> graph -> verify -> human review (with corrections)
  -> DSL -> enhanced reasoning (knowledge + code tools) -> solver -> solution
"""
from __future__ import annotations

import time

import pytest

from geometry_agent.config import load_settings
from geometry_agent.data.synth.generator import SynthGenerator
from geometry_agent.graph.builder import GraphBuilder
from geometry_agent.agents.scheduler import AgentScheduler
from geometry_agent.verifier.engine import VerifierEngine
from geometry_agent.human_loop.reviewer import HumanReviewer
from geometry_agent.human_loop.pdf_compiler import compile_graph_pdf
from geometry_agent.types import Correction, CorrectionType, RelType


@pytest.fixture(scope="module")
def settings():
    s = load_settings("configs/default.yaml")
    s.human_loop.interactive = False
    return s


@pytest.fixture(scope="module")
def verified_graph(settings):
    scene = SynthGenerator(rng_seed=7).generate(1, template_names=["circle_tangent"])[0]
    g = GraphBuilder(settings.graph).build(scene.primitives)
    g = VerifierEngine(settings.verifier).verify(
        AgentScheduler(settings.graph).extract(g), g
    )
    return g


def test_human_review_pdf_generated(verified_graph, tmp_path):
    """LaTeX+TikZ PDF preview is generated for user review."""
    pdf = compile_graph_pdf(verified_graph, "AB切圆O于A", str(tmp_path / "preview.pdf"))
    import os
    assert os.path.exists(pdf)
    assert os.path.getsize(pdf) > 5000


def test_natural_language_correction_removes_relation(verified_graph, settings, tmp_path):
    """User says '删除 OA 垂直 AB' in natural language; the perpendicular edge is removed."""
    reviewer = HumanReviewer(settings.human_loop)
    corr = [Correction(kind=CorrectionType.NATURAL_LANGUAGE, text="删除 OA 垂直 AB")]
    result = reviewer.review_with_corrections(
        verified_graph, "test", corr, str(tmp_path)
    )
    assert result.approved is True
    assert result.corrected_graph is not None
    perp_kept = any(
        e.rel == RelType.PERPENDICULAR for e in result.corrected_graph.edges
    )
    assert perp_kept is False, "perpendicular edge should have been removed"
    assert len(result.corrected_graph.edges) < len(verified_graph.edges)


def test_dsl_correction_adds_relation(verified_graph, settings, tmp_path):
    """User adds a relation via DSL edit; the edge count increases."""
    reviewer = HumanReviewer(settings.human_loop)
    corr = [Correction(
        kind=CorrectionType.DSL_EDIT,
        text="Relations:\n  - Parallel(Segment(OA), Segment(AB))",
    )]
    result = reviewer.review_with_corrections(
        verified_graph, "test", corr, str(tmp_path)
    )
    assert len(result.corrected_graph.edges) > len(verified_graph.edges)


def test_code_executor_solves_equations(settings):
    """The code execution tool can solve symbolic equations."""
    from geometry_agent.tools.code_executor import CodeExecutor
    ce = CodeExecutor(settings.code_exec)
    r = ce.execute("import sympy as sp\nx=sp.symbols('x')\nprint(sp.solve(x**2-9,x))")
    assert r.success
    assert "3" in r.output


def test_enhanced_reasoning_produces_verified_proof(verified_graph, settings):
    """Full enhanced reasoning with GLM-5.2 produces a verified proof.

    Requires LLM api_key configured (skipped if offline).
    """
    from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
    from geometry_agent.knowledge.manager import KnowledgeManager
    from geometry_agent.pipeline import GeometryPipeline
    from geometry_agent.solver.engine import SymbolicSolver

    agent = EnhancedReasoningAgent(
        settings.llm, tools={}, knowledge_manager=KnowledgeManager(settings.knowledge)
    )
    if agent.client.is_offline:
        pytest.skip("LLM api_key not configured")

    dsl = GeometryPipeline(settings).dsl_serializer(verified_graph, settings.dsl)
    tools = GeometryPipeline(settings)._tools(verified_graph)

    t = time.time()
    plan = agent.reason(dsl, "如图,AB切圆O于A。求证OA垂直AB。", tools)
    sol = SymbolicSolver(settings.solver).solve(plan, verified_graph)
    elapsed = time.time() - t

    assert len(sol.proof) > 0, "should produce proof steps"
    assert sol.confidence > 0.5, f"confidence too low: {sol.confidence}"
    assert "垂直" in sol.answer or "⊥" in sol.answer, f"answer: {sol.answer}"
    assert elapsed < 120, f"too slow: {elapsed:.1f}s"
