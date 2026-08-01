"""Unit tests for the Geometry DSL parser/serializer (design/06 §10).

Covers:
  1. serialization of a small graph (On / Tangent / Perpendicular)
  2. round-trip from_dsl(to_dsl(g)) isomorphism
  3. compact mode omits coordinates
  4. uncertain edges emitted as comments
  5. undefined references raise
"""

from __future__ import annotations

import pytest

from geometry_agent.config import DSLConfig
from geometry_agent.dsl.parser import from_dsl
from geometry_agent.dsl.serializer import to_dsl
from geometry_agent.types import (
    Edge,
    GeometryGraph,
    GoalSpec,
    Node,
    NodeType,
    RelType,
    VerifyState,
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _sample_graph() -> GeometryGraph:
    """Point A on circle O; AB tangent to circle O at A; OA perpendicular AB."""
    return GeometryGraph(
        nodes=[
            Node(id="P_A", type=NodeType.POINT, label="A",
                 attrs={"coords": [180.0, 84.5], "confidence": 1.0}),
            Node(id="P_B", type=NodeType.POINT, label="B",
                 attrs={"coords": [260.0, 140.0], "confidence": 1.0}),
            Node(id="P_O", type=NodeType.POINT, label="O",
                 attrs={"coords": [180.0, 160.0], "confidence": 1.0}),
            Node(id="C_O", type=NodeType.CIRCLE, label="O",
                 attrs={"radius": 75.5, "confidence": 1.0}),
            Node(id="S_AB", type=NodeType.SEGMENT, label="AB", attrs={"confidence": 1.0}),
            Node(id="S_OA", type=NodeType.SEGMENT, label="OA", attrs={"confidence": 1.0}),
        ],
        edges=[
            Edge(src="P_A", dst="C_O", rel=RelType.ON,
                 verified=VerifyState.TRUE, confidence=0.98),
            Edge(src="S_AB", dst="C_O", rel=RelType.TANGENT,
                 verified=VerifyState.TRUE, confidence=0.95,
                 attrs={"tangent_point": "P_A"}),
            Edge(src="S_OA", dst="S_AB", rel=RelType.PERPENDICULAR,
                 verified=VerifyState.TRUE, confidence=1.0),
        ],
        goal=GoalSpec(kind="Prove", statement="Equal(Product(AB, AC), Product(AD, AE))"),
    )


def _node_sig(n: Node) -> tuple:
    return (n.type.value, n.label)


def _edge_sig(e: Edge, id2label: dict[str, str]) -> tuple:
    return (
        e.rel.value,
        id2label.get(e.src, e.src),
        id2label.get(e.dst, e.dst),
        e.verified.value,
    )


# --------------------------------------------------------------------------- #
# 1. serialization
# --------------------------------------------------------------------------- #
def test_to_dsl_contains_key_fields():
    s = to_dsl(_sample_graph())
    assert "Objects:" in s
    assert "Point(A)" in s and "[180" in s and "84.5" in s
    assert "Circle(O, r=75.5)" in s
    assert "Segment(AB)" in s and "Segment(OA)" in s
    assert "Relations:" in s
    assert "On(A, Circle(O))" in s
    assert "Tangent(Segment(AB), Circle(O), at=A)" in s
    assert "Perpendicular(Segment(OA), Segment(AB))" in s
    assert "Goal:" in s
    assert "Prove: Equal(Product(AB, AC), Product(AD, AE))" in s


# --------------------------------------------------------------------------- #
# 2. round-trip isomorphism
# --------------------------------------------------------------------------- #
def test_round_trip_isomorphic():
    g = _sample_graph()
    s = to_dsl(g)
    g2 = from_dsl(s)

    # nodes match by (type, label)
    assert {_node_sig(n) for n in g.nodes} == {_node_sig(n) for n in g2.nodes}

    # point coords and circle radius survive
    a2 = next(n for n in g2.nodes if n.label == "A" and n.type == NodeType.POINT)
    assert a2.attrs["coords"] == [180.0, 84.5]
    co2 = next(n for n in g2.nodes if n.type == NodeType.CIRCLE)
    assert co2.attrs["radius"] == 75.5

    # verified edges match by (rel, src_label, dst_label, verified)
    def label_map(graph):
        return {n.id: n.label for n in graph.nodes}
    lm1, lm2 = label_map(g), label_map(g2)
    e1 = {_edge_sig(e, lm1) for e in g.edges if e.verified == VerifyState.TRUE}
    e2 = {_edge_sig(e, lm2) for e in g2.edges if e.verified == VerifyState.TRUE}
    assert e1 == e2

    # tangent_point attr survives (resolved to the point label)
    tan = next(e for e in g2.edges if e.rel == RelType.TANGENT)
    assert tan.attrs["tangent_point"] == "P_A"

    # goal survives
    assert g2.goal is not None
    assert g2.goal.kind == "Prove"
    assert g2.goal.statement == "Equal(Product(AB, AC), Product(AD, AE))"

    # double round-trip is stable
    assert to_dsl(g2) == to_dsl(from_dsl(to_dsl(g2)))


# --------------------------------------------------------------------------- #
# 3. compact mode omits coordinates
# --------------------------------------------------------------------------- #
def test_compact_mode_omits_coords():
    g = _sample_graph()
    s = to_dsl(g, DSLConfig(compact=True))
    # point coords are gone, but topology / radius remain
    assert "Point(A)" in s
    assert "[180" not in s
    assert "Circle(O, r=75.5)" in s
    assert "Segment(AB)" in s
    assert "On(A, Circle(O))" in s
    # non-compact still carries coords
    assert "[180" in to_dsl(g)


# --------------------------------------------------------------------------- #
# 4. uncertain edges as comments
# --------------------------------------------------------------------------- #
def test_uncertain_edge_emitted_as_comment():
    g = _sample_graph()
    g.edges.append(Edge(src="P_B", dst="C_O", rel=RelType.ON,
                        verified=VerifyState.UNCERTAIN, confidence=0.4))

    # default: uncertain dropped
    default_out = to_dsl(g)
    assert "uncertain" not in default_out
    assert "On(B, Circle(O))" not in default_out

    # include_uncertain: emitted as comment
    out = to_dsl(g, DSLConfig(include_uncertain=True))
    assert "# uncertain: On(B, Circle(O))" in out

    # the comment round-trips back as an uncertain edge
    g2 = from_dsl(out)
    unc = [e for e in g2.edges if e.verified == VerifyState.UNCERTAIN]
    assert len(unc) == 1
    assert unc[0].rel == RelType.ON


# --------------------------------------------------------------------------- #
# 5. undefined reference raises
# --------------------------------------------------------------------------- #
def test_undefined_reference_raises():
    dsl = (
        "Objects:\n"
        "  - Point(A): [1, 2]\n"
        "  - Circle(O, r=5)\n"
        "Relations:\n"
        "  - On(C, Circle(O))\n"  # C is not declared
    )
    with pytest.raises(ValueError, match="undefined point reference: 'C'"):
        from_dsl(dsl)


def test_type_mismatch_raises():
    dsl = (
        "Objects:\n"
        "  - Point(A): [1, 2]\n"
        "  - Segment(AB)\n"
        "Relations:\n"
        "  - On(A, Segment(AB))\n"  # Segment is not a Curve
    )
    with pytest.raises(ValueError, match="type mismatch"):
        from_dsl(dsl)
