"""Cross Agent: cross-class relations not owned by a single-type agent
(design/04 §10). Acts as a safety net."""

from __future__ import annotations

import math

from ..types import GeometryGraph, Node, NodeType, RelationCandidate, RelType
from .base import (
    AgentBase,
    line_circle_distance,
    node_coords,
)


def _label(n: Node) -> str:
    return n.label or n.id


class CrossAgent(AgentBase):
    name = "CrossAgent"

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        try:
            cands.extend(self._line_circle_tangent(graph))
        except Exception:
            pass
        try:
            cands.extend(self._point_on_arc(graph))
        except Exception:
            pass
        try:
            cands.extend(self._polygon_inscribed_circle(graph))
        except Exception:
            pass
        return cands

    # ------------------------------------------------------------------
    def _line_circle_tangent(self, graph: GeometryGraph) -> list[RelationCandidate]:
        """Re-emit line-circle tangency as a cross-class safety net
        (deduped later by the scheduler)."""
        cands: list[RelationCandidate] = []
        lines = [n for n in graph.nodes if n.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)]
        circles = [n for n in graph.nodes if n.type in (NodeType.CIRCLE, NodeType.ARC)]
        for L in lines:
            for c in circles:
                info = line_circle_distance(L, c)
                if info is None:
                    continue
                d, foot = info
                r = float(c.attrs.get("radius", 0.0))
                tol = max(2.0, 0.03 * r)
                if abs(d - r) < tol:
                    cands.append(
                        RelationCandidate(
                            src=L.id, dst=c.id, rel=RelType.TANGENT,
                            evidence=f"cross: d={d:.2f}≈r={r:.2f}",
                            confidence=0.7, agent=self.name,
                            attrs={"tangent_coords": [foot[0], foot[1]], "dist": d, "radius": r},
                        )
                    )
        return cands

    # ------------------------------------------------------------------
    def _point_on_arc(self, graph: GeometryGraph) -> list[RelationCandidate]:
        """Point on an arc: On(circle) AND angle within arc_range."""
        cands: list[RelationCandidate] = []
        arcs = [n for n in graph.nodes if n.type == NodeType.ARC]
        for arc in arcs:
            ctr = arc.attrs.get("center")
            r = arc.attrs.get("radius")
            rng = arc.attrs.get("arc_range")
            if ctr is None or r is None or not rng:
                continue
            r = float(r)
            a0, a1 = float(rng[0]), float(rng[1])
            for p in graph.nodes:
                if p.type != NodeType.POINT:
                    continue
                pc = node_coords(p)
                if pc is None:
                    continue
                d = math.hypot(pc[0] - ctr[0], pc[1] - ctr[1])
                if abs(d - r) >= max(2.0, 0.03 * r):
                    continue
                ang = math.atan2(pc[1] - ctr[1], pc[0] - ctr[0])
                if _angle_in_range(ang, a0, a1):
                    cands.append(
                        RelationCandidate(
                            src=p.id, dst=arc.id, rel=RelType.ON,
                            evidence=f"point on arc (angle {math.degrees(ang):.1f}° in range)",
                            confidence=0.8, agent=self.name,
                        )
                    )
        return cands

    # ------------------------------------------------------------------
    def _polygon_inscribed_circle(self, graph: GeometryGraph) -> list[RelationCandidate]:
        polys = [n for n in graph.nodes if n.type == NodeType.POLYGON]
        circles = [n for n in graph.nodes if n.type == NodeType.CIRCLE]
        cands: list[RelationCandidate] = []
        for poly in polys:
            verts = poly.attrs.get("vertices") or []
            if len(verts) < 3:
                continue
            for c in circles:
                ctr = c.attrs.get("center")
                r = c.attrs.get("radius")
                if ctr is None or r is None:
                    continue
                r = float(r)
                tol = max(2.0, 0.03 * r)
                if all(abs(math.hypot(v[0] - ctr[0], v[1] - ctr[1]) - r) < tol for v in verts):
                    cands.append(
                        RelationCandidate(
                            src=poly.id, dst=c.id, rel=RelType.INSCRIBED,
                            evidence=f"cross: {_label(poly)} vertices on {_label(c)}",
                            confidence=0.7, agent=self.name,
                        )
                    )
        return cands


def _angle_in_range(ang: float, a0: float, a1: float) -> bool:
    """True if ang (radians) lies in [a0, a1], handling wrap-around."""
    import math as _m
    two_pi = 2 * _m.pi
    a = ang % two_pi
    lo = a0 % two_pi
    hi = a1 % two_pi
    if lo <= hi:
        return lo - 1e-6 <= a <= hi + 1e-6
    return a >= lo - 1e-6 or a <= hi + 1e-6
