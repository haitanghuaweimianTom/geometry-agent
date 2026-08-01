"""Unit tests for the VerifierEngine (design/05 §7)."""

from __future__ import annotations

import math

import pytest

from geometry_agent.config import VerifierConfig
from geometry_agent.types import (
    Edge,
    GeometryGraph,
    Node,
    NodeType,
    RelationCandidate,
    RelType,
    VerifyState,
)
from geometry_agent.verifier.engine import VerifierEngine


# ---------------------------------------------------------------------------
# Fixture: "Point A on circle O; AB tangent to circle at A; OA perpendicular AB"
# (design/03 §5, design/05 §4.1/§4.2)
# ---------------------------------------------------------------------------
CENTER = (180.0, 160.0)
R = 75.5
A = (180.0, 84.5)          # directly above center, |OA| = 75.5 = r
B = (260.0, 84.5)          # horizontal through A => AB tangent at A, OA perp AB


def _build_graph(extra_points=None) -> GeometryGraph:
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
            attrs={"endpoints": [list(A), list(B)], "length": math.hypot(B[0] - A[0], B[1] - A[1])},
        ),
        Node(
            id="L_OA",
            type=NodeType.SEGMENT,
            label="OA",
            attrs={"endpoints": [list(CENTER), list(A)], "length": R},
        ),
    ]
    if extra_points:
        nodes.extend(extra_points)
    return GeometryGraph(nodes=nodes, edges=[])


# ---------------------------------------------------------------------------
# verify_one: true cases
# ---------------------------------------------------------------------------
def test_on_point_on_circle_true():
    eng = VerifierEngine(VerifierConfig())
    g = _build_graph()
    eng.attach(g)
    res = eng.verify_one(RelType.ON, "P_A", "C_O", {})
    assert res.verified == VerifyState.TRUE
    assert abs(res.measured["dist"] - R) < 1e-6
    assert "OP-r" in res.evidence


def test_tangent_line_circle_true_with_tangent_point():
    eng = VerifierEngine(VerifierConfig())
    g = _build_graph()
    eng.attach(g)
    res = eng.verify_one(RelType.TANGENT, "L_AB", "C_O", {"tangent_point": "P_A"})
    assert res.verified == VerifyState.TRUE
    # foot of perpendicular = A exactly
    assert abs(res.attrs["tangent_coords"][0] - A[0]) < 1e-6
    assert abs(res.attrs["tangent_coords"][1] - A[1]) < 1e-6
    assert res.attrs["tangent_point"] == "P_A"


def test_perpendicular_oa_ab_true():
    eng = VerifierEngine(VerifierConfig())
    g = _build_graph()
    eng.attach(g)
    res = eng.verify_one(RelType.PERPENDICULAR, "L_OA", "L_AB", {})
    assert res.verified == VerifyState.TRUE
    assert abs(res.measured["angle_deg"] - 90.0) < 1e-6


# ---------------------------------------------------------------------------
# false cases
# ---------------------------------------------------------------------------
def test_center_point_not_on_circle_false():
    eng = VerifierEngine(VerifierConfig())
    g = _build_graph()
    eng.attach(g)
    # P_O is the center, distance 0 from center => |0 - r| = r >> tol
    res = eng.verify_one(RelType.ON, "P_O", "C_O", {})
    assert res.verified == VerifyState.FALSE


def test_far_point_on_circle_false():
    eng = VerifierEngine(VerifierConfig())
    # point 10 px beyond the radius => error = 10 > 3*tol(=6) => false
    far = Node(id="P_X", type=NodeType.POINT, label="X",
               attrs={"coords": [CENTER[0], CENTER[1] - (R + 10.0)]})
    g = _build_graph(extra_points=[far])
    eng = VerifierEngine(VerifierConfig())
    eng.attach(g)
    res = eng.verify_one(RelType.ON, "P_X", "C_O", {})
    assert res.verified == VerifyState.FALSE


# ---------------------------------------------------------------------------
# three-state boundary
# ---------------------------------------------------------------------------
def test_three_state_boundary_uncertain():
    """tol = max(2.0, 0.015*75.5) = 2.0; uncertain_band = (2.0, 6.0]."""
    cfg = VerifierConfig()
    tol = max(cfg.on_circle_abs_tol, cfg.on_circle_rel_tol * R)
    assert abs(tol - 2.0) < 1e-6  # sanity

    # exactly at tol => true
    p_true = Node(id="P_T", type=NodeType.POINT, attrs={"coords": [CENTER[0], CENTER[1] - (R + tol)]})
    g = _build_graph(extra_points=[p_true])
    eng = VerifierEngine(cfg)
    eng.attach(g)
    r_true = eng.verify_one(RelType.ON, "P_T", "C_O", {})
    assert r_true.verified == VerifyState.TRUE

    # just over tol => uncertain
    p_unc = Node(id="P_U", type=NodeType.POINT, attrs={"coords": [CENTER[0], CENTER[1] - (R + tol + 1.0)]})
    g2 = _build_graph(extra_points=[p_unc])
    eng2 = VerifierEngine(cfg)
    eng2.attach(g2)
    r_unc = eng.verify_one(RelType.ON, "P_U", "C_O", {}) if False else eng2.verify_one(RelType.ON, "P_U", "C_O", {})
    assert r_unc.verified == VerifyState.UNCERTAIN

    # at mult*tol => still uncertain (boundary inclusive)
    p_edge = Node(id="P_E", type=NodeType.POINT,
                  attrs={"coords": [CENTER[0], CENTER[1] - (R + cfg.uncertain_band_mult * tol)]})
    g3 = _build_graph(extra_points=[p_edge])
    eng3 = VerifierEngine(cfg)
    eng3.attach(g3)
    r_edge = eng3.verify_one(RelType.ON, "P_E", "C_O", {})
    assert r_edge.verified == VerifyState.UNCERTAIN

    # just beyond mult*tol => false
    p_far = Node(id="P_F", type=NodeType.POINT,
                 attrs={"coords": [CENTER[0], CENTER[1] - (R + cfg.uncertain_band_mult * tol + 1.0)]})
    g4 = _build_graph(extra_points=[p_far])
    eng4 = VerifierEngine(cfg)
    eng4.attach(g4)
    r_far = eng4.verify_one(RelType.ON, "P_F", "C_O", {})
    assert r_far.verified == VerifyState.FALSE


def test_perpendicular_three_state_boundary():
    """tol = 3deg, mult=3 => 9deg; angle 91deg -> true, 95deg -> uncertain, 95deg+..."""
    cfg = VerifierConfig()
    eng = VerifierEngine(cfg)
    g = _build_graph()
    eng.attach(g)
    # true: 90deg exactly (already covered). Use a slightly off line.
    # Build a line at 91deg to OA: OA is vertical (direction (0,-1)). A line at 91deg
    # from it has direction (cos(1deg), sin(1deg)) ~ (0.9998, 0.0175) => 1deg off perp.
    A_off = (180.0, 84.5)
    B_off = (A_off[0] + 80.0 * math.cos(math.radians(1.0)),
             A_off[1] + 80.0 * math.sin(math.radians(1.0)))
    g.nodes.append(Node(id="L_T1", type=NodeType.SEGMENT,
                        attrs={"endpoints": [list(A_off), list(B_off)]}))
    eng.attach(g)
    r_true = eng.verify_one(RelType.PERPENDICULAR, "L_OA", "L_T1", {})
    assert r_true.verified == VerifyState.TRUE

    # uncertain: 5deg off (tol < 5 <= 9)
    B_unc = (A_off[0] + 80.0 * math.cos(math.radians(5.0)),
             A_off[1] + 80.0 * math.sin(math.radians(5.0)))
    g.nodes.append(Node(id="L_U1", type=NodeType.SEGMENT,
                        attrs={"endpoints": [list(A_off), list(B_unc)]}))
    eng.attach(g)
    r_unc = eng.verify_one(RelType.PERPENDICULAR, "L_OA", "L_U1", {})
    assert r_unc.verified == VerifyState.UNCERTAIN

    # false: 15deg off
    B_far = (A_off[0] + 80.0 * math.cos(math.radians(15.0)),
             A_off[1] + 80.0 * math.sin(math.radians(15.0)))
    g.nodes.append(Node(id="L_F1", type=NodeType.SEGMENT,
                        attrs={"endpoints": [list(A_off), list(B_far)]}))
    eng.attach(g)
    r_far = eng.verify_one(RelType.PERPENDICULAR, "L_OA", "L_F1", {})
    assert r_far.verified == VerifyState.FALSE


# ---------------------------------------------------------------------------
# Full verify(candidates, graph) flow
# ---------------------------------------------------------------------------
def test_verify_writes_back_edges():
    eng = VerifierEngine(VerifierConfig())
    g = _build_graph()
    cands = [
        RelationCandidate(src="P_A", dst="C_O", rel=RelType.ON, agent="PointAgent"),
        RelationCandidate(src="L_AB", dst="C_O", rel=RelType.TANGENT,
                          agent="CircleAgent", attrs={"tangent_point": "P_A"}),
        RelationCandidate(src="L_OA", dst="L_AB", rel=RelType.PERPENDICULAR, agent="LineAgent"),
        # false candidate: center point on circle -> should be dropped
        RelationCandidate(src="P_O", dst="C_O", rel=RelType.ON, agent="PointAgent"),
    ]
    eng.verify(cands, g)
    by_key = {(e.src, e.dst, e.rel.value): e for e in g.edges}
    assert ("P_A", "C_O", "On") in by_key
    assert by_key[("P_A", "C_O", "On")].verified == VerifyState.TRUE
    assert ("L_AB", "C_O", "Tangent") in by_key
    assert by_key[("L_AB", "C_O", "Tangent")].verified == VerifyState.TRUE
    assert by_key[("L_AB", "C_O", "Tangent")].attrs.get("tangent_point") == "P_A"
    assert ("L_OA", "L_AB", "Perpendicular") in by_key
    assert by_key[("L_OA", "L_AB", "Perpendicular")].verified == VerifyState.TRUE
    # false candidate dropped
    assert ("P_O", "C_O", "On") not in by_key
    # verification log recorded every call
    assert len(eng.verification_log) == 4


def test_verify_one_accepts_string_rel():
    eng = VerifierEngine(VerifierConfig())
    g = _build_graph()
    eng.attach(g)
    res = eng.verify_one("On", "P_A", "C_O", {})
    assert res.verified == VerifyState.TRUE


def test_verify_one_unknown_node_returns_false():
    eng = VerifierEngine(VerifierConfig())
    g = _build_graph()
    eng.attach(g)
    res = eng.verify_one("On", "P_NOPE", "C_O", {})
    assert res.verified == VerifyState.FALSE
