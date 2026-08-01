"""Polygon Agent: Inscribed/Circumscribed, Similar/Congruent (design/04 §8)."""

from __future__ import annotations

import math

from ..types import GeometryGraph, Node, NodeType, RelationCandidate, RelType
from .base import AgentBase, line_from_two_points


def _label(n: Node) -> str:
    return n.label or n.id


class PolygonAgent(AgentBase):
    name = "PolygonAgent"

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        try:
            cands.extend(self._inscribed_circumscribed(graph))
        except Exception:
            pass
        try:
            cands.extend(self._similar(graph))
        except Exception:
            pass
        return cands

    # ------------------------------------------------------------------
    def _inscribed_circumscribed(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        polys = [n for n in graph.nodes if n.type == NodeType.POLYGON]
        circles = [n for n in graph.nodes if n.type in (NodeType.CIRCLE, NodeType.ARC)]
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
                # Inscribed: all vertices on circle
                if all(abs(math.hypot(v[0] - ctr[0], v[1] - ctr[1]) - r) < tol for v in verts):
                    cands.append(
                        RelationCandidate(
                            src=poly.id, dst=c.id, rel=RelType.INSCRIBED,
                            evidence=f"all vertices of {_label(poly)} on {_label(c)}",
                            confidence=0.85, agent=self.name,
                        )
                    )
                # Circumscribed: every edge tangent to circle
                edges_tangent = True
                for i in range(len(verts)):
                    p1 = verts[i]
                    p2 = verts[(i + 1) % len(verts)]
                    a, b, cc = line_from_two_points(p1, p2)
                    d = abs(a * ctr[0] + b * ctr[1] + cc)
                    if abs(d - r) >= tol:
                        edges_tangent = False
                        break
                if edges_tangent and len(verts) >= 3:
                    cands.append(
                        RelationCandidate(
                            src=poly.id, dst=c.id, rel=RelType.CIRCUMSCRIBED,
                            evidence=f"all edges of {_label(poly)} tangent to {_label(c)}",
                            confidence=0.85, agent=self.name,
                        )
                    )
        return cands

    # ------------------------------------------------------------------
    def _similar(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        polys = [n for n in graph.nodes if n.type == NodeType.POLYGON]
        tris = [p for p in polys if (p.attrs.get("poly_type") == "triangle" or len(p.attrs.get("vertices") or []) == 3)]
        for i, t1 in enumerate(tris):
            ang1 = _triangle_angles(t1)
            if not ang1:
                continue
            for t2 in tris[i + 1:]:
                ang2 = _triangle_angles(t2)
                if not ang2:
                    continue
                if _angles_match(sorted(ang1), sorted(ang2), tol_deg=3.0):
                    cands.append(
                        RelationCandidate(
                            src=t1.id, dst=t2.id, rel=RelType.SIMILAR,
                            evidence=f"corresponding angles match ({[f'{a:.1f}' for a in sorted(ang1)]})",
                            confidence=0.8, agent=self.name,
                            attrs={"angles1": sorted(ang1), "angles2": sorted(ang2)},
                        )
                    )
        return cands


def _triangle_angles(poly: Node) -> list[float]:
    verts = poly.attrs.get("vertices") or []
    if len(verts) != 3:
        return []
    pts = [tuple(v) for v in verts]
    sides = [
        math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]),
        math.hypot(pts[2][0] - pts[1][0], pts[2][1] - pts[1][1]),
        math.hypot(pts[0][0] - pts[2][0], pts[0][1] - pts[2][1]),
    ]
    angles = []
    for i in range(3):
        a, b, c = sides[i], sides[(i + 1) % 3], sides[(i + 2) % 3]
        if b < 1e-9 or c < 1e-9:
            return []
        cosA = (b * b + c * c - a * a) / (2 * b * c)
        cosA = max(-1.0, min(1.0, cosA))
        angles.append(math.degrees(math.acos(cosA)))
    return angles


def _angles_match(a1: list[float], a2: list[float], tol_deg: float = 3.0) -> bool:
    if len(a1) != len(a2):
        return False
    return all(abs(x - y) <= tol_deg for x, y in zip(a1, a2))
