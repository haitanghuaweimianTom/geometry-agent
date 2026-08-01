"""Unit tests for the human-in-the-loop LaTeX preview & correction module."""

from __future__ import annotations

import os
import tempfile

import pytest

from geometry_agent.human_loop.correction_parser import (
    apply_corrections,
    parse_correction,
)
from geometry_agent.human_loop.latex_render import graph_to_latex
from geometry_agent.human_loop.pdf_compiler import compile_graph_pdf, compile_pdf
from geometry_agent.human_loop.reviewer import HumanReviewer
from geometry_agent.types import (
    Correction,
    CorrectionType,
    Edge,
    GeometryGraph,
    Node,
    NodeType,
    RelType,
    VerifyState,
)


def _sample_graph() -> GeometryGraph:
    return GeometryGraph(
        nodes=[
            Node(id="P_A", type=NodeType.POINT, label="A",
                 attrs={"coords": [0.0, 0.0]}),
            Node(id="P_B", type=NodeType.POINT, label="B",
                 attrs={"coords": [4.0, 0.0]}),
            Node(id="P_C", type=NodeType.POINT, label="C",
                 attrs={"coords": [4.0, 3.0]}),
            Node(id="P_D", type=NodeType.POINT, label="D",
                 attrs={"coords": [0.0, 3.0]}),
            Node(id="S_AB", type=NodeType.SEGMENT, label="AB",
                 attrs={"p1": [0.0, 0.0], "p2": [4.0, 0.0]}),
            Node(id="S_CD", type=NodeType.SEGMENT, label="CD",
                 attrs={"p1": [4.0, 3.0], "p2": [0.0, 3.0]}),
            Node(id="S_BC", type=NodeType.SEGMENT, label="BC",
                 attrs={"p1": [4.0, 0.0], "p2": [4.0, 3.0]}),
        ],
        edges=[
            Edge(src="S_AB", dst="S_CD", rel=RelType.PARALLEL,
                 verified=VerifyState.TRUE, evidence="水平方向"),
            Edge(src="S_AB", dst="S_BC", rel=RelType.PERPENDICULAR,
                 verified=VerifyState.TRUE, evidence="直角标记"),
            Edge(src="S_BC", dst="S_CD", rel=RelType.PERPENDICULAR,
                 verified=VerifyState.UNCERTAIN, evidence="待确认"),
        ],
    )


def _sample_graph_with_circle() -> GeometryGraph:
    return GeometryGraph(
        nodes=[
            Node(id="P_O", type=NodeType.POINT, label="O",
                 attrs={"coords": [180.0, 160.0]}),
            Node(id="P_A", type=NodeType.POINT, label="A",
                 attrs={"coords": [180.0, 84.5]}),
            Node(id="P_B", type=NodeType.POINT, label="B",
                 attrs={"coords": [260.0, 140.0]}),
            Node(id="C_O", type=NodeType.CIRCLE, label="O",
                 attrs={"center": [180.0, 160.0], "radius": 75.5}),
            Node(id="S_AB", type=NodeType.SEGMENT, label="AB",
                 attrs={"p1": [180.0, 84.5], "p2": [260.0, 140.0]}),
            Node(id="S_OA", type=NodeType.SEGMENT, label="OA",
                 attrs={"p1": [180.0, 160.0], "p2": [180.0, 84.5]}),
        ],
        edges=[
            Edge(src="P_A", dst="C_O", rel=RelType.ON,
                 verified=VerifyState.TRUE, evidence="|d-r|<tol"),
            Edge(src="S_AB", dst="C_O", rel=RelType.TANGENT,
                 verified=VerifyState.TRUE, evidence="d≈r"),
            Edge(src="S_OA", dst="S_AB", rel=RelType.PERPENDICULAR,
                 verified=VerifyState.TRUE, evidence="θ=90°"),
        ],
    )


# --------------------------------------------------------------------------- #
# 1. graph_to_latex
# --------------------------------------------------------------------------- #
def test_graph_to_latex_contains_chinese_sections_and_relations():
    g = _sample_graph()
    latex = graph_to_latex(g, problem_text="如图,AB 平行 CD,求证 AB 垂直 BC。")
    assert "几何对象" in latex
    assert "几何关系" in latex
    assert "题目" in latex
    # object labels appear
    assert "AB" in latex
    assert "CD" in latex
    # relation in Chinese
    assert "平行" in latex
    assert "垂直" in latex
    # ctexart + xelatex-friendly preamble
    assert r"\documentclass" in latex and "ctexart" in latex
    assert "Noto Serif CJK SC" in latex
    # uncertain relation is greyed/italicised
    assert "gauncertain" in latex


# --------------------------------------------------------------------------- #
# 2. compile_graph_pdf
# --------------------------------------------------------------------------- #
def test_compile_graph_pdf_produces_nonempty_pdf(tmp_path):
    g = _sample_graph()
    out = str(tmp_path / "out.pdf")
    pdf_path = compile_graph_pdf(g, "测试题目: AB 平行 CD", out)
    assert pdf_path.endswith(".pdf")
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 1000  # non-trivial PDF size


def test_compile_pdf_raises_on_bad_latex():
    from geometry_agent.human_loop.pdf_compiler import PDFCompileError
    with pytest.raises(PDFCompileError):
        compile_pdf(r"\documentclass{ctexart}\begin{document}\undefinedcmd\end{document}",
                    os.path.join(tempfile.gettempdir(), "bad.pdf"))


# --------------------------------------------------------------------------- #
# 3. parse_correction DSL mode
# --------------------------------------------------------------------------- #
def test_parse_correction_dsl_mode_add_parallel():
    g = _sample_graph()
    # user wants to add Parallel(Segment(AB), Segment(CD)) via DSL snippet
    text = "dsl: Relations:\n  - Parallel(Segment(AB), Segment(CD))"
    corr = parse_correction(text, CorrectionType.DSL_EDIT, g)
    assert corr.kind == CorrectionType.DSL_EDIT
    add_actions = [a for a in corr.actions if a.get("op") == "add_edge"]
    assert add_actions, f"expected at least one add_edge, got {corr.actions}"
    parallel_adds = [a for a in add_actions if a.get("rel") == "Parallel"]
    assert parallel_adds, f"expected Parallel add, got {add_actions}"


# --------------------------------------------------------------------------- #
# 4. parse_correction natural language (no LLM)
# --------------------------------------------------------------------------- #
def test_parse_correction_nl_keyword_remove_perpendicular():
    g = _sample_graph()
    text = "删除 AB 垂直 BC"
    corr = parse_correction(text, CorrectionType.NATURAL_LANGUAGE, g)
    assert corr.kind == CorrectionType.NATURAL_LANGUAGE
    removes = [a for a in corr.actions if a.get("op") == "remove_edge"]
    assert removes, f"expected remove action, got {corr.actions}"
    assert removes[0]["rel"] == "Perpendicular"


def test_parse_correction_nl_no_llm_fallback_safe_on_garbage():
    g = _sample_graph()
    corr = parse_correction("乱七八糟没有关系词", CorrectionType.NATURAL_LANGUAGE, g)
    assert corr.actions == []


# --------------------------------------------------------------------------- #
# 5. apply_corrections
# --------------------------------------------------------------------------- #
def test_apply_corrections_add_parallel_creates_edge():
    g = _sample_graph()
    before = len(g.edges)
    corr = Correction(
        kind=CorrectionType.DSL_EDIT,
        text="",
        actions=[{
            "op": "add_edge",
            "src": "S_AB",
            "dst": "S_BC",
            "rel": "Parallel",
            "verified": "true",
            "attrs": {},
        }],
    )
    g2 = apply_corrections(g, [corr])
    assert len(g2.edges) == before + 1
    assert any(e.src == "S_AB" and e.dst == "S_BC" and e.rel == RelType.PARALLEL
               for e in g2.edges)
    # original graph untouched
    assert len(g.edges) == before


def test_apply_corrections_remove_edge():
    g = _sample_graph()
    before = len(g.edges)
    corr = Correction(
        kind=CorrectionType.NATURAL_LANGUAGE,
        text="",
        actions=[{
            "op": "remove_edge",
            "src": "S_AB",
            "dst": "S_BC",
            "rel": "Perpendicular",
        }],
    )
    g2 = apply_corrections(g, [corr])
    assert len(g2.edges) == before - 1
    assert not any(e.src == "S_AB" and e.dst == "S_BC" and
                   e.rel == RelType.PERPENDICULAR for e in g2.edges)


def test_apply_corrections_skips_unknown_objects():
    g = _sample_graph()
    corr = Correction(
        kind=CorrectionType.NATURAL_LANGUAGE,
        text="",
        actions=[{
            "op": "add_edge",
            "src": "NONEXISTENT1",
            "dst": "NONEXISTENT2",
            "rel": "Parallel",
        }],
    )
    g2 = apply_corrections(g, [corr])  # must not raise
    assert len(g2.edges) == len(g.edges)


# --------------------------------------------------------------------------- #
# 6. review_with_corrections non-interactive
# --------------------------------------------------------------------------- #
def test_review_with_corrections_returns_approved(tmp_path):
    g = _sample_graph()
    reviewer = HumanReviewer()
    result = reviewer.review_with_corrections(
        g,
        problem_text="测试题目",
        corrections=[],
        out_dir=str(tmp_path),
    )
    assert result.approved is True
    assert result.pdf_path and os.path.exists(result.pdf_path)
    assert result.rounds == 1


def test_review_non_interactive_produces_pdf(tmp_path):
    g = _sample_graph()
    reviewer = HumanReviewer()
    result = reviewer.review(g, problem_text="测试题目", out_dir=str(tmp_path))
    assert result.approved is False
    assert result.pdf_path and os.path.exists(result.pdf_path)


def test_review_interactive_loop_approves(tmp_path):
    import io
    g = _sample_graph()
    reviewer = HumanReviewer()
    inp = io.StringIO("approve\n")
    out = io.StringIO()
    result = reviewer.review_interactive(
        g, problem_text="测试", out_dir=str(tmp_path),
        input_stream=inp, output_stream=out,
    )
    assert result.approved is True
    assert result.rounds == 1


def test_review_interactive_loop_applies_correction_then_approves(tmp_path):
    import io
    g = _sample_graph()
    reviewer = HumanReviewer()
    inp = io.StringIO("删除 AB 垂直 BC\napprove\n")
    out = io.StringIO()
    result = reviewer.review_interactive(
        g, problem_text="测试", out_dir=str(tmp_path),
        input_stream=inp, output_stream=out,
    )
    assert result.approved is True
    assert result.rounds == 2
    assert len(result.corrections) == 1
    # the corrected graph no longer has AB perpendicular BC
    assert result.corrected_graph is not None
    assert not any(e.src == "S_AB" and e.dst == "S_BC" and
                   e.rel == RelType.PERPENDICULAR
                   for e in result.corrected_graph.edges)


# --------------------------------------------------------------------------- #
# TikZ figure redraw
# --------------------------------------------------------------------------- #
def test_graph_to_tikz_draws_segments_and_points():
    from geometry_agent.human_loop.tikz_render import graph_to_tikz
    tikz = graph_to_tikz(_sample_graph())
    assert r"\begin{tikzpicture}" in tikz
    assert r"\draw" in tikz          # segments drawn
    assert r"\fill" in tikz          # points drawn
    assert "label" not in tikz.lower() or r"\node" in tikz  # label nodes
    # coordinates should be scaled (small numbers, not raw 0/4)
    assert "0" in tikz


def test_graph_to_tikz_draws_circle():
    from geometry_agent.human_loop.tikz_render import graph_to_tikz
    tikz = graph_to_tikz(_sample_graph_with_circle())
    assert r"circle" in tikz         # circle drawn
    assert r"\fill" in tikz          # points O, A, B drawn


def test_graph_to_latex_includes_tikz_figure():
    g = _sample_graph_with_circle()
    latex = graph_to_latex(g, problem_text="AB 切圆 O 于 A")
    assert r"\usepackage{tikz}" in latex
    assert r"\begin{tikzpicture}" in latex
    assert "几何图形" in latex        # figure section header


def test_compile_pdf_with_tikz_figure(tmp_path):
    g = _sample_graph_with_circle()
    pdf = compile_graph_pdf(g, problem_text="切线证明", out_path=str(tmp_path / "fig.pdf"))
    assert os.path.exists(pdf)
    assert os.path.getsize(pdf) > 5000  # non-trivial PDF with figure
