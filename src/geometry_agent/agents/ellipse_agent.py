"""Ellipse Agent: focus relation (On), tangent to ellipse (design/04 §7)."""

from __future__ import annotations

import math

from ..types import GeometryGraph, Node, NodeType, RelationCandidate, RelType
from .base import AgentBase, angle_between_dirs, line_direction, line_from_two_points, node_coords


def _foci(e: Node) -> list[tuple[float, float]]:
    f = e.attrs.get("foci") or []
    if len(f) >= 2:
        return [(float(f[0][0]), float(f[0][1])), (float(f[1][0]), float(f[1][1]))]
    a = float(e.attrs.get("semi_major", 0.0))
    b = float(e.attrs.get("semi_minor", 0.0))
    cx, cy = e.attrs.get("center", (0.0, 0.0))
    rot = float(e.attrs.get("rotation", 0.0))
    c = math.sqrt(max(0.0, a * a - b * b))
    return [
        (float(cx) + c * math.cos(rot), float(cy) + c * math.sin(rot)),
        (float(cx) - c * math.cos(rot), float(cy) - c * math.sin(rot)),
    ]


def _label(n: Node) -> str:
    return n.label or n.id


class EllipseAgent(AgentBase):
    name = "EllipseAgent"

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        ellipses = [n for n in graph.nodes if n.type == NodeType.ELLIPSE]
        if not ellipses:
            return cands
        points = [n for n in graph.nodes if n.type == NodeType.POINT]
        lines = [n for n in graph.nodes if n.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)]

        for e in ellipses:
            a = float(e.attrs.get("semi_major", 0.0))
            f1, f2 = _foci(e)
            target = 2.0 * a
            tol = max(2.0, 0.03 * target)
            on_points: list[tuple[str, tuple[float, float]]] = []
            for p in points:
                pc = node_coords(p)
                if pc is None:
                    continue
                s = math.hypot(pc[0] - f1[0], pc[1] - f1[1]) + math.hypot(pc[0] - f2[0], pc[1] - f2[1])
                if abs(s - target) < tol:
                    on_points.append((p.id, pc))
                    cands.append(
                        RelationCandidate(
                            src=p.id, dst=e.id, rel=RelType.ON,
                            evidence=f"|PF1|+|PF2|={s:.2f}≈2a={target:.2f}",
                            confidence=0.85, agent=self.name,
                            attrs={"sum": s, "2a": target},
                        )
                    )
            # tangent: a line passing through an on-ellipse point and perpendicular
            # to the normal (gradient) at that point.
            for L in lines:
                ld = line_direction(L)
                if ld is None:
                    continue
                coeffs = line_coeffs_safe(L)
                if coeffs is None:
                    continue
                la, lb, lc = coeffs
                for pid, pc in on_points:
                    normal = _ellipse_normal(e, pc)
                    ang = angle_between_dirs(ld, normal)
                    if ang is None:
                        continue
                    # tangent iff direction ⊥ normal => angle between them ≈ 90
                    if 87.0 <= ang <= 93.0 and abs(la * pc[0] + lb * pc[1] + lc) < 2.0:
                        cands.append(
                            RelationCandidate(
                                src=L.id, dst=e.id, rel=RelType.TANGENT,
                                evidence=f"{_label(L)} tangent to {_label(e)} at {_label(graph_node(graph, pid))}",
                                confidence=0.8, agent=self.name,
                                attrs={"tangent_point": pid},
                            )
                        )
                        break
        return cands


def line_coeffs_safe(node: Node):
    if node.type not in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY):
        return None
    eq = node.attrs.get("equation")
    if eq:
        a, b, c = float(eq["a"]), float(eq["b"]), float(eq["c"])
        n = math.hypot(a, b)
        if n < 1e-12:
            return None
        return a / n, b / n, c / n
    ep = node.attrs.get("endpoints")
    if ep and len(ep) >= 2:
        return line_from_two_points(ep[0], ep[1])
    return None


def _ellipse_normal(e: Node, p: tuple[float, float]) -> tuple[float, float]:
    """Gradient of the ellipse implicit function at p (= outward normal)."""
    cx, cy = e.attrs.get("center", (0.0, 0.0))
    a = float(e.attrs.get("semi_major", 1.0))
    b = float(e.attrs.get("semi_minor", 1.0))
    rot = float(e.attrs.get("rotation", 0.0))
    cos_r, sin_r = math.cos(rot), math.sin(rot)
    dx, dy = p[0] - cx, p[1] - cy
    # rotate into ellipse frame
    u = dx * cos_r + dy * sin_r
    v = -dx * sin_r + dy * cos_r
    gu = 2.0 * u / (a * a)
    gv = 2.0 * v / (b * b)
    # rotate gradient back to world frame
    nx = gu * cos_r - gv * sin_r
    ny = gu * sin_r + gv * cos_r
    return (nx, ny)


def graph_node(graph: GeometryGraph, nid: str) -> Node:
    for n in graph.nodes:
        if n.id == nid:
            return n
    return Node(id=nid, type=NodeType.POINT)
