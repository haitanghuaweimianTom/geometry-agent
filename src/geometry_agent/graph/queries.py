"""NetworkX bridge and high-level query API (design/03 §7)."""

from __future__ import annotations

from typing import Any, Optional

import networkx as nx

from ..types import GeometryGraph, NodeType, RelType, VerifyState

_LINE_TYPES = ("Line", "Segment", "Ray")
_CURVE_TYPES = ("Circle", "Arc")


def to_networkx(graph: GeometryGraph) -> nx.MultiDiGraph:
    """Convert a GeometryGraph into a networkx MultiDiGraph (with edge attrs)."""
    G: nx.MultiDiGraph = nx.MultiDiGraph()
    for n in graph.nodes:
        G.add_node(n.id, type=n.type.value, label=n.label, **dict(n.attrs))
    for e in graph.edges:
        data = {
            "rel": e.rel.value,
            "verified": e.verified.value,
            "confidence": float(e.confidence),
            "evidence": e.evidence,
            "source": e.source,
        }
        data.update(dict(e.attrs))
        G.add_edge(e.src, e.dst, **data)
    return G


class GQuery:
    """High-level query facade over a GeometryGraph (networkx-backed)."""

    def __init__(self, graph: GeometryGraph):
        self.graph = graph
        self.g: nx.MultiDiGraph = to_networkx(graph)

    # ------------------------------------------------------------------
    def _edge_matches(self, u: str, v: str, rel: Optional[str], verified_only: bool) -> list[dict]:
        out = []
        if not self.g.has_edge(u, v):
            return out
        for d in self.g[u][v].values():
            if rel is not None and d.get("rel") != rel:
                continue
            if verified_only and d.get("verified") != VerifyState.TRUE.value:
                continue
            out.append(d)
        return out

    def points_on(self, obj_id: str) -> list[str]:
        """All Point nodes with a verified On edge into obj_id."""
        if obj_id not in self.g:
            return []
        res: list[str] = []
        for n in self.g.predecessors(obj_id):
            if self.g.nodes[n].get("type") != NodeType.POINT.value:
                continue
            if self._edge_matches(n, obj_id, RelType.ON.value, verified_only=True):
                res.append(n)
        return res

    def circles_through(self, point_id: str) -> list[str]:
        """All Circle/Arc nodes that a point lies on (verified)."""
        if point_id not in self.g:
            return []
        res: list[str] = []
        for n in self.g.successors(point_id):
            if self.g.nodes[n].get("type") not in _CURVE_TYPES:
                continue
            if self._edge_matches(point_id, n, RelType.ON.value, verified_only=True):
                res.append(n)
        return res

    def tangent_lines(self, circle_id: str) -> list[str]:
        """All Line/Segment/Ray nodes tangent to circle_id (verified)."""
        if circle_id not in self.g:
            return []
        res: list[str] = []
        for n in self.g.predecessors(circle_id):
            if self.g.nodes[n].get("type") not in _LINE_TYPES:
                continue
            if self._edge_matches(n, circle_id, RelType.TANGENT.value, verified_only=True):
                res.append(n)
        return res

    def tangent_points(self, circle_id: str) -> list[str]:
        """All Point nodes that are tangent points of circle_id."""
        if circle_id not in self.g:
            return []
        res: list[str] = []
        for n in self.g.predecessors(circle_id):
            if self.g.nodes[n].get("type") != NodeType.POINT.value:
                continue
            if self._edge_matches(n, circle_id, RelType.TANGENT_POINT.value, verified_only=True):
                res.append(n)
        return res

    def lines_through(self, point_id: str) -> list[str]:
        """All Line/Segment/Ray nodes that a point lies on (verified)."""
        if point_id not in self.g:
            return []
        res: list[str] = []
        for n in self.g.successors(point_id):
            if self.g.nodes[n].get("type") not in _LINE_TYPES:
                continue
            if self._edge_matches(point_id, n, RelType.ON.value, verified_only=True):
                res.append(n)
        return res

    def neighbors(self, node: str, rel: Optional[str] = None) -> list[str]:
        """All neighbour node ids (optionally filtered by rel, any verify state)."""
        if node not in self.g:
            return []
        seen: dict[str, None] = {}
        for n in self.g.predecessors(node):
            if self._edge_matches(n, node, rel, verified_only=False):
                seen.setdefault(n, None)
        for n in self.g.successors(node):
            if self._edge_matches(node, n, rel, verified_only=False):
                seen.setdefault(n, None)
        return list(seen.keys())

    def all_verified(self, rel: str) -> list[tuple[str, str, dict]]:
        """All verified-true edges of a given rel type as (src, dst, data)."""
        out: list[tuple[str, str, dict]] = []
        for u, v, d in self.g.edges(data=True):
            if d.get("rel") == rel and d.get("verified") == VerifyState.TRUE.value:
                out.append((u, v, dict(d)))
        return out

    def intersection(self, obj1: str, obj2: str) -> list[Any]:
        """Lookup intersection points recorded on an Intersect edge."""
        ds = self._edge_matches(obj1, obj2, RelType.INTERSECT.value, verified_only=False)
        pts: list[Any] = []
        for d in ds:
            pts.extend(d.get("intersection_points", []) or d.get("attrs", {}).get("intersection_points", []))
        return pts
