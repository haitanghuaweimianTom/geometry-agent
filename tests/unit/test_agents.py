"""Unit tests for the AgentScheduler (design/04 §11, §12)."""

from __future__ import annotations

import pytest

from geometry_agent.config import GraphConfig
from geometry_agent.graph.builder import GraphBuilder
from geometry_agent.agents.scheduler import AgentScheduler
from geometry_agent.types import (
    Circle,
    Line,
    LineType,
    Point,
    PointSource,
    PrimitiveSet,
    RelType,
)


def _primitives() -> PrimitiveSet:
    """A on circle O (center (180,160), r=75.5); AB horizontal at y=84.5
    (tangent at A); OA vertical (perp to AB)."""
    return PrimitiveSet(
        points=[
            Point(id="P_A", label="A", coords=(180.0, 84.5)),
            Point(id="P_O", label="O", coords=(180.0, 160.0), source=PointSource.EXPLICIT),
            Point(id="P_B", label="B", coords=(260.0, 84.5)),
        ],
        lines=[
            Line(id="L_AB", type=LineType.SEGMENT, label="AB",
                 endpoints=[(180.0, 84.5), (260.0, 84.5)], length=80.0),
            Line(id="L_OA", type=LineType.SEGMENT, label="OA",
                 endpoints=[(180.0, 160.0), (180.0, 84.5)], length=75.5),
        ],
        circles=[
            Circle(id="C_O", label="O", center=(180.0, 160.0), radius=75.5),
        ],
    )


def _extract():
    g = GraphBuilder(GraphConfig()).build(_primitives())
    cands = AgentScheduler(GraphConfig()).extract(g)
    return g, cands


def test_scheduler_returns_candidates():
    _, cands = _extract()
    assert len(cands) > 0
    rels = {c.rel for c in cands}
    assert RelType.ON in rels


def test_scheduler_finds_tangent_candidate():
    _, cands = _extract()
    tangents = [c for c in cands if c.rel == RelType.TANGENT]
    assert len(tangents) >= 1
    tgt = [c for c in tangents if c.src == "L_AB" and c.dst == "C_O"]
    assert len(tgt) == 1
    assert tgt[0].agent in {"CircleAgent", "CrossAgent"}
    # tangent point was located
    assert tgt[0].attrs.get("tangent_point") == "P_A"
    assert abs(tgt[0].attrs["tangent_coords"][0] - 180.0) < 1e-6
    assert abs(tgt[0].attrs["tangent_coords"][1] - 84.5) < 1e-6


def test_scheduler_finds_perpendicular_candidate():
    _, cands = _extract()
    perps = [c for c in cands if c.rel == RelType.PERPENDICULAR]
    assert len(perps) >= 1
    pair = [c for c in perps if {c.src, c.dst} == {"L_OA", "L_AB"}]
    assert len(pair) == 1
    assert pair[0].agent == "LineAgent"
    assert abs(pair[0].attrs["angle"] - 90.0) < 1e-6


def test_scheduler_finds_on_center_candidates():
    _, cands = _extract()
    on_a = [c for c in cands if c.rel == RelType.ON and c.src == "P_A" and c.dst == "C_O"]
    assert len(on_a) == 1
    center = [c for c in cands if c.rel == RelType.CENTER and c.src == "P_O" and c.dst == "C_O"]
    assert len(center) == 1


def test_scheduler_dedupes_duplicates():
    """CircleAgent and CrossAgent both emit Tangent(L_AB, C_O); scheduler
    must keep exactly one (highest confidence)."""
    _, cands = _extract()
    tangents = [c for c in cands if c.rel == RelType.TANGENT and c.src == "L_AB" and c.dst == "C_O"]
    assert len(tangents) == 1


def test_scheduler_does_not_crash_on_empty_graph():
    from geometry_agent.types import GeometryGraph
    cands = AgentScheduler(GraphConfig()).extract(GeometryGraph())
    assert cands == []


def test_candidates_carry_agent_name():
    _, cands = _extract()
    assert all(c.agent for c in cands)
