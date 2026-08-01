"""Circle Agent: tangent (line-circle & circle-circle), chord, inscribed angle,
concentric, intersect, tangent point (design/04 §6)."""

from __future__ import annotations

import math

from ..types import (
    GeometryGraph,
    Node,
    NodeType,
    RelationCandidate,
    RelType,
)
from .base import (
    AgentBase,
    line_circle_distance,
    nearest_point_id,
    node_coords,
)
from .point_agent import _cc


def _label(n: Node) -> str:
    return n.label or n.id


class CircleAgent(AgentBase):
    name = "CircleAgent"

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        try:
            cands.extend(self._line_circle_tangent(graph))
        except Exception:
            pass
        try:
            cands.extend(self._circle_circle_relations(graph))
        except Exception:
            pass
        try:
            cands.extend(self._chords(graph))
        except Exception:
            pass
        return cands

    # ------------------------------------------------------------------
    def _line_circle_tangent(self, graph: GeometryGraph) -> list[RelationCandidate]:
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
                    tp = nearest_point_id(graph, foot, tol=max(3.0, 0.05 * r + 2.0))
                    cands.append(
                        RelationCandidate(
                            src=L.id, dst=c.id, rel=RelType.TANGENT,
                            evidence=f"d(O,{_label(L)})={d:.2f}≈r={r:.2f}",
                            confidence=0.9, agent=self.name,
                            attrs={
                                "tangent_point": tp,
                                "tangent_coords": [foot[0], foot[1]],
                                "dist": d,
                                "radius": r,
                            },
                        )
                    )
                    if tp:
                        cands.append(
                            RelationCandidate(
                                src=tp, dst=c.id, rel=RelType.TANGENT_POINT,
                                evidence=f"tangent point {_label(graph_node(graph, tp))} on {_label(c)}",
                                confidence=0.85, agent=self.name,
                                attrs={"tangent_coords": [foot[0], foot[1]]},
                            )
                        )
        return cands

    # ------------------------------------------------------------------
    def _circle_circle_relations(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        circles = [n for n in graph.nodes if n.type in (NodeType.CIRCLE, NodeType.ARC)]
        for i, c1 in enumerate(circles):
            o1 = c1.attrs.get("center")
            r1 = float(c1.attrs.get("radius", 0.0))
            for c2 in circles[i + 1:]:
                o2 = c2.attrs.get("center")
                r2 = float(c2.attrs.get("radius", 0.0))
                if o1 is None or o2 is None:
                    continue
                d = math.hypot(o1[0] - o2[0], o1[1] - o2[1])
                tol = max(2.0, 0.03 * (r1 + r2))
                # tangent
                if abs(d - (r1 + r2)) < tol or abs(d - abs(r1 - r2)) < tol:
                    mode = "external" if abs(d - (r1 + r2)) <= abs(d - abs(r1 - r2)) else "internal"
                    cands.append(
                        RelationCandidate(
                            src=c1.id, dst=c2.id, rel=RelType.TANGENT,
                            evidence=f"|O1O2|={d:.2f}, r1+r2={r1 + r2:.2f}, |r1-r2|={abs(r1 - r2):.2f} ({mode})",
                            confidence=0.85, agent=self.name,
                            attrs={"mode": mode, "center_dist": d},
                        )
                    )
                # concentric
                if d < max(2.0, 0.02 * 0.5 * (r1 + r2)):
                    cands.append(
                        RelationCandidate(
                            src=c1.id, dst=c2.id, rel=RelType.CONCENTRIC,
                            evidence=f"|O1O2|={d:.2f}≈0",
                            confidence=0.9, agent=self.name,
                            attrs={"center_dist": d},
                        )
                    )
                # intersect (crossing)
                if abs(r1 - r2) - tol < d < r1 + r2 - tol:
                    pts = _cc(c1, c2)
                    cands.append(
                        RelationCandidate(
                            src=c1.id, dst=c2.id, rel=RelType.INTERSECT,
                            evidence=f"two circles cross (d={d:.2f}), x{len(pts)}",
                            confidence=0.8, agent=self.name,
                            attrs={"center_dist": d, "intersection_points": [list(p) for p in pts]},
                        )
                    )
        return cands

    # ------------------------------------------------------------------
    def _chords(self, graph: GeometryGraph) -> list[RelationCandidate]:
        """A segment whose endpoints both lie on a circle is a chord."""
        cands: list[RelationCandidate] = []
        circles = [n for n in graph.nodes if n.type in (NodeType.CIRCLE, NodeType.ARC)]
        segs = [n for n in graph.nodes if n.type == NodeType.SEGMENT]
        for c in circles:
            ctr = c.attrs.get("center")
            r = c.attrs.get("radius")
            if ctr is None or r is None:
                continue
            r = float(r)
            on_points = set()
            for p in graph.nodes:
                if p.type != NodeType.POINT:
                    continue
                pc = node_coords(p)
                if pc is None:
                    continue
                if abs(math.hypot(pc[0] - ctr[0], pc[1] - ctr[1]) - r) < max(2.0, 0.03 * r):
                    on_points.add(p.id)
            for s in segs:
                ep = s.attrs.get("endpoints")
                if not ep or len(ep) < 2:
                    continue
                e1 = nearest_point_id(graph, (ep[0][0], ep[0][1]), tol=max(3.0, 0.05 * r))
                e2 = nearest_point_id(graph, (ep[1][0], ep[1][1]), tol=max(3.0, 0.05 * r))
                if e1 in on_points and e2 in on_points and e1 != e2:
                    cands.append(
                        RelationCandidate(
                            src=s.id, dst=c.id, rel=RelType.ON,
                            evidence=f"{_label(s)} is a chord of {_label(c)} (endpoints on circle)",
                            confidence=0.8, agent=self.name,
                            attrs={"chord": True},
                        )
                    )
        return cands


def graph_node(graph: GeometryGraph, nid: str) -> Node:
    for n in graph.nodes:
        if n.id == nid:
            return n
    return Node(id=nid, type=NodeType.POINT)
