"""Line Agent: Parallel, Perpendicular, Intersect (design/04 §5)."""

from __future__ import annotations

from ..types import GeometryGraph, Node, NodeType, RelationCandidate, RelType
from .base import AgentBase, angle_between_dirs, line_direction
from .point_agent import _ll  # reuse line-line intersection helper


def _label(n: Node) -> str:
    return n.label or n.id


class LineAgent(AgentBase):
    name = "LineAgent"

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        lines = [n for n in graph.nodes if n.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)]
        for i, l1 in enumerate(lines):
            u = line_direction(l1)
            if u is None:
                continue
            for l2 in lines[i + 1:]:
                v = line_direction(l2)
                if v is None:
                    continue
                ang = angle_between_dirs(u, v)
                if ang is None:
                    continue
                # Parallel
                if ang < 3.0:
                    cands.append(
                        RelationCandidate(
                            src=l1.id, dst=l2.id, rel=RelType.PARALLEL,
                            evidence=f"∠({_label(l1)},{_label(l2)})={ang:.2f}°≈0°",
                            confidence=0.9, agent=self.name, attrs={"angle": ang},
                        )
                    )
                # Perpendicular
                if 87.0 <= ang <= 93.0:
                    cands.append(
                        RelationCandidate(
                            src=l1.id, dst=l2.id, rel=RelType.PERPENDICULAR,
                            evidence=f"∠({_label(l1)},{_label(l2)})={ang:.2f}°≈90°",
                            confidence=0.9, agent=self.name, attrs={"angle": ang},
                        )
                    )
                # Intersect (non-parallel lines intersect unless collinear)
                if ang > 1.0:
                    ip = _ll(l1, l2)
                    if ip:
                        cands.append(
                            RelationCandidate(
                                src=l1.id, dst=l2.id, rel=RelType.INTERSECT,
                                evidence=f"intersection at ({ip[0]:.1f},{ip[1]:.1f})",
                                confidence=0.75, agent=self.name,
                                attrs={"intersection_points": [list(ip)]},
                            )
                        )
        return cands
