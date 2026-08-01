"""Regression baseline: GT GeometryGraph must be self-consistent (design/09 §8.1).

For 20 synthesized scenes we re-derive every ``On`` relation from raw coordinates
and assert the GT edges hold analytically (within tight tolerance). This guards
against future regressions in the constructor's analytic derivation.

This test is intentionally deterministic (fixed seed) so it can serve as a
regression baseline: any change that breaks GT self-consistency will fail here.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

import pytest

from geometry_agent.data.synth.generator import SynthGenerator
from geometry_agent.data.synth.constructor import ConstructedScene
from geometry_agent.types import RelType, VerifyState

TOL = 1e-6


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _point_on_segment(p, e1, e2, tol=TOL):
    return abs(_dist(p, e1) + _dist(p, e2) - _dist(e1, e2)) <= tol * 100


def _point_on_circle(p, center, radius, tol=TOL):
    return abs(_dist(p, center) - radius) <= tol * 100


def _point_on_ellipse(p, center, a, b, rotation, tol=TOL * 1000):
    dx = p[0] - center[0]
    dy = p[1] - center[1]
    cr, sr = math.cos(rotation), math.sin(rotation)
    xp = dx * cr + dy * sr
    yp = -dx * sr + dy * cr
    return abs((xp * xp) / (a * a) + (yp * yp) / (b * b) - 1.0) <= tol


@pytest.fixture(scope="module")
def scenes() -> list[ConstructedScene]:
    # Use multiple seeds to cover all templates at least once.
    g = SynthGenerator(rng_seed=1234)
    return g.generate(20)


def test_all_edges_verified_true(scenes):
    for s in scenes:
        for e in s.graph.edges:
            assert e.verified == VerifyState.TRUE, (
                f"{s.template_name}: edge {e.rel} {e.src}->{e.dst} not verified"
            )


def test_on_point_segment_self_consistent(scenes):
    for s in scenes:
        coords = {p.id: (float(p.coords[0]), float(p.coords[1])) for p in s.primitives.points}
        seg_by_id = {L.id: L for L in s.primitives.lines}
        for e in s.graph.edges:
            if e.rel != RelType.ON:
                continue
            # ON edges from point -> segment/circle/ellipse
            src_node = next(n for n in s.graph.nodes if n.id == e.src)
            if src_node.type.value != "Point":
                continue
            pc = coords[e.src]
            # segment?
            if e.dst in seg_by_id:
                L = seg_by_id[e.dst]
                assert L.endpoints is not None
                e1, e2 = L.endpoints
                assert _point_on_segment(pc, e1, e2), (
                    f"{s.template_name}: point {e.src} not on segment {e.dst}"
                )


def test_on_point_circle_self_consistent(scenes):
    for s in scenes:
        coords = {p.id: (float(p.coords[0]), float(p.coords[1])) for p in s.primitives.points}
        circ_by_id = {c.id: c for c in s.primitives.circles}
        for e in s.graph.edges:
            if e.rel != RelType.ON:
                continue
            if e.dst not in circ_by_id:
                continue
            c = circ_by_id[e.dst]
            pc = coords[e.src]
            assert _point_on_circle(pc, c.center, c.radius), (
                f"{s.template_name}: point {e.src} not on circle {e.dst} "
                f"(dist={_dist(pc, c.center)}, r={c.radius})"
            )


def test_on_point_ellipse_self_consistent(scenes):
    for s in scenes:
        coords = {p.id: (float(p.coords[0]), float(p.coords[1])) for p in s.primitives.points}
        ell_by_id = {e.id: e for e in s.primitives.ellipses}
        for e in s.graph.edges:
            if e.rel != RelType.ON:
                continue
            if e.dst not in ell_by_id:
                continue
            ell = ell_by_id[e.dst]
            pc = coords[e.src]
            assert _point_on_ellipse(pc, ell.center, ell.semi_major, ell.semi_minor,
                                      ell.rotation), (
                f"{s.template_name}: point {e.src} not on ellipse {e.dst}"
            )


def test_tangent_distance_equals_radius(scenes):
    """For every Tangent(line, circle) edge: dist(center, line) ≈ radius."""
    for s in scenes:
        coords = {p.id: (float(p.coords[0]), float(p.coords[1])) for p in s.primitives.points}
        seg_by_id = {L.id: L for L in s.primitives.lines}
        circ_by_id = {c.id: c for c in s.primitives.circles}
        for e in s.graph.edges:
            if e.rel != RelType.TANGENT:
                continue
            # Tangent edge could be (line, circle) or (circle, circle)
            if e.src in seg_by_id and e.dst in circ_by_id:
                L = seg_by_id[e.src]
                c = circ_by_id[e.dst]
                e1, e2 = L.endpoints
                # normalized line distance
                dx, dy = e2[0] - e1[0], e2[1] - e1[1]
                n = math.hypot(dx, dy)
                a, b = dy / n, -dx / n
                cc = -(a * e1[0] + b * e1[1])
                d = abs(a * c.center[0] + b * c.center[1] + cc)
                assert abs(d - c.radius) <= 1e-3, (
                    f"{s.template_name}: Tangent dist {d} != radius {c.radius}"
                )


def test_perpendicular_edges_orthogonal(scenes):
    """For every Perpendicular(s1, s2): direction dot product ≈ 0."""
    for s in scenes:
        seg_by_id = {L.id: L for L in s.primitives.lines}
        for e in s.graph.edges:
            if e.rel != RelType.PERPENDICULAR:
                continue
            if e.src not in seg_by_id or e.dst not in seg_by_id:
                continue
            L1 = seg_by_id[e.src]
            L2 = seg_by_id[e.dst]
            d1 = (L1.endpoints[1][0] - L1.endpoints[0][0],
                  L1.endpoints[1][1] - L1.endpoints[0][1])
            d2 = (L2.endpoints[1][0] - L2.endpoints[0][0],
                  L2.endpoints[1][1] - L2.endpoints[0][1])
            n1 = math.hypot(*d1)
            n2 = math.hypot(*d2)
            if n1 < TOL or n2 < TOL:
                continue
            cos_ang = abs((d1[0] * d2[0] + d1[1] * d2[1]) / (n1 * n2))
            assert cos_ang <= 1e-3, (
                f"{s.template_name}: Perpendicular {e.src}->{e.dst} "
                f"cos={cos_ang} not orthogonal"
            )


def test_center_edges_match_coords(scenes):
    """For every Center(point, circle): point coords == circle center."""
    for s in scenes:
        coords = {p.id: (float(p.coords[0]), float(p.coords[1])) for p in s.primitives.points}
        circ_by_id = {c.id: c for c in s.primitives.circles}
        for e in s.graph.edges:
            if e.rel != RelType.CENTER:
                continue
            if e.dst not in circ_by_id:
                continue
            c = circ_by_id[e.dst]
            pc = coords[e.src]
            assert _dist(pc, c.center) <= 1e-6, (
                f"{s.template_name}: Center {e.src} != circle center {c.center}"
            )


def test_template_diversity(scenes):
    """Regression: ensure the 20-scene sample covers multiple templates."""
    counts = defaultdict(int)
    for s in scenes:
        counts[s.template_name] += 1
    assert len(counts) >= 3, f"Low template diversity: {dict(counts)}"


def test_ellipse_focus_sum_property(scenes):
    """For ellipse scenes with point P on ellipse: PF1 + PF2 == 2a."""
    for s in scenes:
        if s.template_name != "ellipse_focus":
            continue
        a = float(s.params["a"])
        f1 = s.params["F1"]
        f2 = s.params["F2"]
        p = s.params["P"]
        ssum = _dist(p, f1) + _dist(p, f2)
        assert abs(ssum - 2 * a) <= 1e-3, f"PF1+PF2={ssum} != 2a={2 * a}"
