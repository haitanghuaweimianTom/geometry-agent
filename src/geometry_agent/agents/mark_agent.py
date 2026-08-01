"""Mark Agent: convert detected annotation marks into high-confidence
relation candidates (design/04 §9).

Marks are not part of the GeometryGraph Node schema; GraphBuilder attaches
the raw Mark list to the graph object as `_marks`. This agent reads them.
"""

from __future__ import annotations

import math

from ..types import (
    GeometryGraph,
    MarkType,
    Node,
    NodeType,
    RelationCandidate,
    RelType,
)
from .base import AgentBase, node_coords


def _label(n: Node) -> str:
    return n.label or n.id


class MarkAgent(AgentBase):
    name = "MarkAgent"

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        marks = getattr(graph, "_marks", []) or []
        if not marks:
            return cands
        node_by_id = {n.id: n for n in graph.nodes}
        for m in marks:
            try:
                if m.type == MarkType.RIGHT_ANGLE and m.vertex:
                    cands.extend(self._right_angle(graph, m, node_by_id))
                elif m.type == MarkType.PARALLEL:
                    cands.extend(self._parallel(graph, m, node_by_id))
                elif m.type == MarkType.EQUAL:
                    cands.extend(self._equal(graph, m, node_by_id))
                elif m.type == MarkType.ANGLE and m.vertex:
                    cands.extend(self._angle_value(graph, m, node_by_id))
            except Exception:
                continue
        return cands

    def _right_angle(self, graph, m, node_by_id):
        out = []
        vertex = node_by_id.get(m.vertex)
        if vertex is None:
            return out
        vc = node_coords(vertex)
        if vc is None:
            return out
        # find two lines through the vertex
        lines = []
        for n in graph.nodes:
            if n.type not in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY):
                continue
            ep = n.attrs.get("endpoints")
            if not ep:
                continue
            for e in ep:
                if math.hypot(e[0] - vc[0], e[1] - vc[1]) < 3.0:
                    lines.append(n)
                    break
        for i, l1 in enumerate(lines):
            for l2 in lines[i + 1:]:
                out.append(
                    RelationCandidate(
                        src=l1.id, dst=l2.id, rel=RelType.PERPENDICULAR,
                        evidence=f"right-angle mark at {_label(vertex)}",
                        confidence=0.9, agent=self.name, source="mark", attrs={"angle": 90.0},
                    )
                )
        return out

    def _parallel(self, graph, m, node_by_id):
        out = []
        rel_ids = [r for r in m.related if r in node_by_id]
        for i, a in enumerate(rel_ids):
            for b in rel_ids[i + 1:]:
                out.append(
                    RelationCandidate(
                        src=a, dst=b, rel=RelType.PARALLEL,
                        evidence="parallel mark", confidence=0.9, agent=self.name,
                        source="mark", attrs={},
                    )
                )
        return out

    def _equal(self, graph, m, node_by_id):
        out = []
        rel_ids = [r for r in m.related if r in node_by_id]
        for i, a in enumerate(rel_ids):
            for b in rel_ids[i + 1:]:
                out.append(
                    RelationCandidate(
                        src=a, dst=b, rel=RelType.EQUAL,
                        evidence=f"equal mark (count={m.count})", confidence=0.9,
                        agent=self.name, source="mark", attrs={"count": m.count},
                    )
                )
        return out

    def _angle_value(self, graph, m, node_by_id):
        out = []
        if m.angle_value is None or not m.related:
            return out
        rel_ids = [r for r in m.related if r in node_by_id]
        for i, a in enumerate(rel_ids):
            for b in rel_ids[i + 1:]:
                out.append(
                    RelationCandidate(
                        src=a, dst=b, rel=RelType.EQUAL,
                        evidence=f"angle mark = {m.angle_value}°", confidence=0.9,
                        agent=self.name, source="mark",
                        attrs={"angle1": float(m.angle_value), "angle2": float(m.angle_value)},
                    )
                )
        return out
