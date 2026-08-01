"""Unit tests for GraphBuilder and GQuery (design/03 §6, §7)."""

from __future__ import annotations

import networkx as nx
import pytest

from geometry_agent.config import GraphConfig
from geometry_agent.graph.builder import GraphBuilder
from geometry_agent.graph.queries import GQuery, to_networkx
from geometry_agent.types import (
    Circle,
    GeometryGraph,
    Line,
    LineType,
    MetaData,
    Node,
    NodeType,
    Point,
    PointSource,
    PrimitiveSet,
    RelType,
    VerifyState,
    Edge,
)


def _primitives() -> PrimitiveSet:
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
        metadata=MetaData(image_size=(400, 320), scale_px_per_cm=12.0),
    )


# ---------------------------------------------------------------------------
def test_builder_registers_all_primitives_as_nodes():
    g = GraphBuilder(GraphConfig()).build(_primitives())
    ids = {n.id for n in g.nodes}
    assert ids == {"P_A", "P_O", "P_B", "L_AB", "L_OA", "C_O"}
    types = {n.id: n.type for n in g.nodes}
    assert types["P_A"] == NodeType.POINT
    assert types["L_AB"] == NodeType.SEGMENT
    assert types["C_O"] == NodeType.CIRCLE
    # no edges yet (builder does not run agents/verifier)
    assert g.edges == []


def test_builder_preserves_node_attrs():
    g = GraphBuilder(GraphConfig()).build(_primitives())
    circle = next(n for n in g.nodes if n.id == "C_O")
    assert circle.attrs["center"] == [180.0, 160.0]
    assert circle.attrs["radius"] == 75.5
    seg = next(n for n in g.nodes if n.id == "L_AB")
    assert seg.attrs["endpoints"] == [[180.0, 84.5], [260.0, 84.5]]
    assert seg.attrs["length"] == 80.0
    pt = next(n for n in g.nodes if n.id == "P_A")
    assert pt.attrs["coords"] == [180.0, 84.5]


def test_builder_metadata_propagated():
    g = GraphBuilder(GraphConfig()).build(_primitives())
    assert g.metadata.image_size == (400, 320)
    assert g.metadata.scale_px_per_cm == 12.0


def test_to_networkx_returns_multidigraph():
    g = GraphBuilder(GraphConfig()).build(_primitives())
    G = to_networkx(g)
    assert isinstance(G, nx.MultiDiGraph)
    assert G.number_of_nodes() == 6
    assert G.number_of_edges() == 0


# ---------------------------------------------------------------------------
# Query tests: build a graph with pre-verified edges (design/03 §5 example).
# ---------------------------------------------------------------------------
def _graph_with_verified_edges() -> GeometryGraph:
    g = GraphBuilder(GraphConfig()).build(_primitives())
    g.edges = [
        Edge(src="P_A", dst="C_O", rel=RelType.ON, verified=VerifyState.TRUE, confidence=0.98,
             evidence="ok"),
        Edge(src="P_A", dst="L_AB", rel=RelType.ON, verified=VerifyState.TRUE, confidence=1.0),
        Edge(src="P_O", dst="C_O", rel=RelType.CENTER, verified=VerifyState.TRUE, confidence=1.0),
        Edge(src="L_AB", dst="C_O", rel=RelType.TANGENT, verified=VerifyState.TRUE,
             confidence=0.95, attrs={"tangent_point": "P_A"}),
        Edge(src="P_A", dst="C_O", rel=RelType.TANGENT_POINT, verified=VerifyState.TRUE,
             confidence=0.9),
        # an unverified (pending) edge that should be filtered out
        Edge(src="P_B", dst="C_O", rel=RelType.ON, verified=VerifyState.PENDING, confidence=0.5),
    ]
    return g


def test_points_on_returns_only_verified_on_points():
    q = GQuery(_graph_with_verified_edges())
    pts = q.points_on("C_O")
    assert "P_A" in pts
    assert "P_B" not in pts  # pending, filtered out


def test_circles_through_point():
    q = GQuery(_graph_with_verified_edges())
    assert q.circles_through("P_A") == ["C_O"]


def test_tangent_lines_and_tangent_points():
    q = GQuery(_graph_with_verified_edges())
    assert q.tangent_lines("C_O") == ["L_AB"]
    assert q.tangent_points("C_O") == ["P_A"]


def test_lines_through_point():
    q = GQuery(_graph_with_verified_edges())
    lines = q.lines_through("P_A")
    assert "L_AB" in lines


def test_neighbors_filtered_by_rel():
    q = GQuery(_graph_with_verified_edges())
    nbrs = q.neighbors("C_O", rel=RelType.TANGENT.value)
    assert "L_AB" in nbrs
    # P_A -> C_O is a TangentPoint edge, not Tangent
    tp_nbrs = q.neighbors("C_O", rel=RelType.TANGENT_POINT.value)
    assert "P_A" in tp_nbrs


def test_all_verified_returns_true_edges_only():
    q = GQuery(_graph_with_verified_edges())
    on_edges = q.all_verified(RelType.ON.value)
    srcs = {u for u, v, d in on_edges}
    assert "P_A" in srcs
    assert "P_B" not in srcs  # pending edge excluded


def test_gquery_handles_empty_graph():
    g = GeometryGraph()
    q = GQuery(g)
    assert q.points_on("nothing") == []
    assert q.all_verified(RelType.ON.value) == []
