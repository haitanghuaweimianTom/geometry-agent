"""Point Agent: On, Center, Collinear, intersection completion (design/04 §4)."""

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
    line_coeffs,
    line_from_two_points,
    line_length,
    node_coords,
    point_line_distance,
)


def _label(n: Node) -> str:
    return n.label or n.id


class PointAgent(AgentBase):
    name = "PointAgent"

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        try:
            cands.extend(self._on_relations(graph))
        except Exception:
            pass
        try:
            cands.extend(self._center_relations(graph))
        except Exception:
            pass
        try:
            cands.extend(self._collinear(graph))
        except Exception:
            pass
        try:
            cands.extend(self._intersection_completion(graph))
        except Exception:
            pass
        return cands

    # ------------------------------------------------------------------
    def _on_relations(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        points = [n for n in graph.nodes if n.type == NodeType.POINT]
        for p in points:
            pc = node_coords(p)
            if pc is None:
                continue
            px, py = pc
            for n in graph.nodes:
                if n.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY):
                    d = point_line_distance(px, py, n)
                    if d is None:
                        continue
                    scale = line_length(n) or 1.0
                    tol = max(2.0, 0.01 * scale)
                    if d < tol:
                        cands.append(
                            RelationCandidate(
                                src=p.id, dst=n.id, rel=RelType.ON,
                                evidence=f"dist({_label(p)},{_label(n)})={d:.2f}px",
                                confidence=0.9, agent=self.name, attrs={"dist": d},
                            )
                        )
                elif n.type in (NodeType.CIRCLE, NodeType.ARC):
                    c = n.attrs.get("center")
                    r = n.attrs.get("radius")
                    if c is None or r is None:
                        continue
                    d = math.hypot(px - c[0], py - c[1])
                    tol = max(2.0, 0.03 * float(r))
                    if abs(d - float(r)) < tol:
                        cands.append(
                            RelationCandidate(
                                src=p.id, dst=n.id, rel=RelType.ON,
                                evidence=f"|O{_label(p)}|={d:.2f}≈r={float(r):.2f}",
                                confidence=0.9, agent=self.name,
                                attrs={"dist": d, "radius": float(r)},
                            )
                        )
                elif n.type == NodeType.ELLIPSE:
                    a = float(n.attrs.get("semi_major", 0.0))
                    b = float(n.attrs.get("semi_minor", 0.0))
                    foci = n.attrs.get("foci") or []
                    if len(foci) < 2 and a >= b:
                        cx, cy = n.attrs["center"]
                        rot = float(n.attrs.get("rotation", 0.0))
                        cc = math.sqrt(max(0.0, a * a - b * b))
                        foci = [(cx + cc * math.cos(rot), cy + cc * math.sin(rot)),
                                (cx - cc * math.cos(rot), cy - cc * math.sin(rot))]
                    if len(foci) < 2:
                        continue
                    s = math.hypot(px - foci[0][0], py - foci[0][1]) + \
                        math.hypot(px - foci[1][0], py - foci[1][1])
                    target = 2.0 * a
                    tol = max(2.0, 0.03 * target)
                    if abs(s - target) < tol:
                        cands.append(
                            RelationCandidate(
                                src=p.id, dst=n.id, rel=RelType.ON,
                                evidence=f"|PF1|+|PF2|={s:.2f}≈2a={target:.2f}",
                                confidence=0.85, agent=self.name,
                                attrs={"sum": s, "2a": target},
                            )
                        )
        return cands

    # ------------------------------------------------------------------
    def _center_relations(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        points = [n for n in graph.nodes if n.type == NodeType.POINT]
        circles = [n for n in graph.nodes if n.type in (NodeType.CIRCLE, NodeType.ARC)]
        for p in points:
            pc = node_coords(p)
            if pc is None:
                continue
            for c in circles:
                ctr = c.attrs.get("center")
                if ctr is None:
                    continue
                d = math.hypot(pc[0] - ctr[0], pc[1] - ctr[1])
                tol = max(2.0, 0.02 * float(c.attrs.get("radius", 0.0)))
                if d < tol:
                    cands.append(
                        RelationCandidate(
                            src=p.id, dst=c.id, rel=RelType.CENTER,
                            evidence=f"{_label(p)} coincides with center of {_label(c)} (d={d:.2f})",
                            confidence=0.95, agent=self.name, attrs={"center_dist": d},
                        )
                    )
        return cands

    # ------------------------------------------------------------------
    def _collinear(self, graph: GeometryGraph) -> list[RelationCandidate]:
        """Detect collinear triples via per-pair point gathering (design/04 §4.2)."""
        cands: list[RelationCandidate] = []
        points = [n for n in graph.nodes if n.type == NodeType.POINT]
        seen_groups: set[tuple[str, ...]] = set()
        for i, p1 in enumerate(points):
            c1 = node_coords(p1)
            if c1 is None:
                continue
            for p2 in points[i + 1:]:
                c2 = node_coords(p2)
                if c2 is None:
                    continue
                a, b, c = line_from_two_points(c1, c2)
                group_ids = [p1.id, p2.id]
                group_coords = [list(c1), list(c2)]
                for p3 in points:
                    if p3.id in (p1.id, p2.id):
                        continue
                    c3 = node_coords(p3)
                    if c3 is None:
                        continue
                    d = abs(a * c3[0] + b * c3[1] + c)
                    if d < 2.0:
                        group_ids.append(p3.id)
                        group_coords.append(list(c3))
                if len(group_ids) >= 3:
                    key = tuple(sorted(group_ids))
                    if key in seen_groups:
                        continue
                    seen_groups.add(key)
                    cands.append(
                        RelationCandidate(
                            src=group_ids[0], dst=group_ids[1], rel=RelType.COLLINEAR,
                            evidence=f"collinear group {[_label(graph_node(graph, i)) for i in group_ids]}",
                            confidence=0.85, agent=self.name,
                            attrs={"point_ids": group_ids, "points": group_coords},
                        )
                    )
        return cands

    # ------------------------------------------------------------------
    def _intersection_completion(self, graph: GeometryGraph) -> list[RelationCandidate]:
        cands: list[RelationCandidate] = []
        lines = [n for n in graph.nodes if n.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)]
        circles = [n for n in graph.nodes if n.type in (NodeType.CIRCLE, NodeType.ARC)]
        # line x line
        for i, l1 in enumerate(lines):
            for l2 in lines[i + 1:]:
                ip = _ll(l1, l2)
                if not ip:
                    continue
                cands.append(
                    RelationCandidate(
                        src=l1.id, dst=l2.id, rel=RelType.INTERSECT,
                        evidence=f"intersection at ({ip[0]:.1f},{ip[1]:.1f})",
                        confidence=0.8, agent=self.name,
                        attrs={"intersection_points": [list(ip)]},
                    )
                )
        # line x circle
        for L in lines:
            for c in circles:
                pts = _lc(L, c)
                if not pts:
                    continue
                cands.append(
                    RelationCandidate(
                        src=L.id, dst=c.id, rel=RelType.INTERSECT,
                        evidence=f"line-circle intersection x{len(pts)}",
                        confidence=0.8, agent=self.name,
                        attrs={"intersection_points": [list(p) for p in pts]},
                    )
                )
        # circle x circle
        for i, c1 in enumerate(circles):
            for c2 in circles[i + 1:]:
                pts = _cc(c1, c2)
                if not pts:
                    continue
                cands.append(
                    RelationCandidate(
                        src=c1.id, dst=c2.id, rel=RelType.INTERSECT,
                        evidence=f"circle-circle intersection x{len(pts)}",
                        confidence=0.8, agent=self.name,
                        attrs={"intersection_points": [list(p) for p in pts]},
                    )
                )
        return cands


def graph_node(graph: GeometryGraph, nid: str) -> Node:
    for n in graph.nodes:
        if n.id == nid:
            return n
    return Node(id=nid, type=NodeType.POINT)


def _ll(s: Node, d: Node):
    c1 = line_coeffs(s)
    c2 = line_coeffs(d)
    if c1 is None or c2 is None:
        return None
    a1, b1, cc1 = c1
    a2, b2, cc2 = c2
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
        return None
    x = (b1 * cc2 - b2 * cc1) / det
    y = (a2 * cc1 - a1 * cc2) / det
    return (x, y)


def _lc(line: Node, circle: Node):
    coeffs = line_coeffs(line)
    if coeffs is None:
        return []
    a, b, c = coeffs
    ctr = circle.attrs.get("center")
    r = circle.attrs.get("radius")
    if ctr is None or r is None:
        return []
    r = float(r)
    sd = a * ctr[0] + b * ctr[1] + c
    h2 = r * r - sd * sd
    if h2 < -1e-9:
        return []
    h = math.sqrt(max(0.0, h2))
    fx = ctr[0] - a * sd
    fy = ctr[1] - b * sd
    if h < 1e-6:
        return [(fx, fy)]
    return [(fx - b * h, fy + a * h), (fx + b * h, fy - a * h)]


def _cc(c1: Node, c2: Node):
    o1 = c1.attrs.get("center")
    o2 = c2.attrs.get("center")
    r1 = c1.attrs.get("radius")
    r2 = c2.attrs.get("radius")
    if None in (o1, o2, r1, r2):
        return []
    r1, r2 = float(r1), float(r2)
    d = math.hypot(o1[0] - o2[0], o1[1] - o2[1])
    if d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9 or d < 1e-9:
        return []
    a = (d * d + r1 * r1 - r2 * r2) / (2 * d)
    h = math.sqrt(max(0.0, r1 * r1 - a * a))
    px = o1[0] + a * (o2[0] - o1[0]) / d
    py = o1[1] + a * (o2[1] - o1[1]) / d
    if h < 1e-6:
        return [(px, py)]
    return [
        (px + h * (o2[1] - o1[1]) / d, py - h * (o2[0] - o1[0]) / d),
        (px - h * (o2[1] - o1[1]) / d, py + h * (o2[0] - o1[0]) / d),
    ]
