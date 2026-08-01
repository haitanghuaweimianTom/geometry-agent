"""End-to-end integration test (pytest).

Synthesizes a triangle scene, runs the full pipeline, and asserts it completes
without crashing across all parallel-developed modules. With no LLM api key the
LLM agent degrades to an empty plan (by design), so we assert structural
soundness rather than a non-empty answer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from geometry_agent.config import load_settings
from geometry_agent.data.synth.generator import SynthGenerator
from geometry_agent.data.synth.renderer import render_to_file
from geometry_agent.dsl.parser import from_dsl
from geometry_agent.dsl.serializer import to_dsl
from geometry_agent.pipeline import GeometryPipeline
from geometry_agent.types import (
    Edge, GeometryGraph, Node, NodeType, RelType, SolveRequest, VerifyState,
)


@pytest.fixture(scope="module")
def triangle_image(tmp_path_factory):
    out = tmp_path_factory.mktemp("e2e")
    gen = SynthGenerator(rng_seed=42)
    scene = gen.generate(1, template_names=["triangle_basic"])[0]
    img_path = out / "triangle.png"
    render_to_file(scene, str(img_path))
    return img_path, scene


def test_pipeline_runs_end_to_end(triangle_image):
    """Full pipeline: parse -> graph -> agents -> verifier -> dsl -> llm -> solver."""
    img_path, scene = triangle_image
    settings = load_settings("configs/default.yaml")
    pipeline = GeometryPipeline(settings)
    req = SolveRequest(image_path=str(img_path), problem_text="如图三角形。")
    resp = pipeline.run(req)
    # Must complete and return a well-formed response (no crash)
    assert resp is not None
    assert isinstance(resp.answer, str)
    assert isinstance(resp.proof, list)
    assert isinstance(resp.verification_log, list)
    # No api key => offline LLM => empty plan => confidence 0 (by design)
    assert resp.confidence >= 0.0


def test_pipeline_modules_all_wired(triangle_image):
    """Each lazy property loads without import error."""
    settings = load_settings("configs/default.yaml")
    p = GeometryPipeline(settings)
    assert p.parser is not None
    assert p.graph_builder is not None
    assert p.agent_scheduler is not None
    assert p.verifier is not None
    assert p.solver is not None
    assert p.theorem_db is not None
    # dsl_serializer is a function
    assert callable(p.dsl_serializer)


def test_solver_equations():
    settings = load_settings("configs/default.yaml")
    p = GeometryPipeline(settings)
    res = p.solver.solve_equations(["x + 2 = 5"], "x = 3")
    assert res["verified"] is True


def test_dsl_round_trip():
    g = GeometryGraph(
        nodes=[
            Node(id="P_A", type=NodeType.POINT, label="A", attrs={"coords": [180.0, 84.5]}),
            Node(id="P_O", type=NodeType.POINT, label="O", attrs={"coords": [180.0, 160.0]}),
            Node(id="C_O", type=NodeType.CIRCLE, label="O",
                 attrs={"center": [180.0, 160.0], "radius": 75.5}),
        ],
        edges=[
            Edge(src="P_A", dst="C_O", rel=RelType.ON, verified=VerifyState.TRUE, evidence="ok"),
            Edge(src="P_O", dst="C_O", rel=RelType.CENTER, verified=VerifyState.TRUE),
        ],
    )
    dsl = to_dsl(g)
    g2 = from_dsl(dsl)
    assert len(g2.nodes) == 3
    assert len(g2.edges) == 2
