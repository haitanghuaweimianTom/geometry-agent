"""Unified RelationAgent protocol (design/04 §3)."""

from __future__ import annotations

import math
from typing import Optional, Protocol, runtime_checkable

from ..types import GeometryGraph, Node, NodeType, RelationCandidate


@runtime_checkable
class RelationAgent(Protocol):
    """Every relation-extraction agent implements this interface."""

    name: str

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]: ...


class AgentBase:
    """Common helpers for concrete agents."""

    name: str = "AgentBase"

    def __init__(self, config=None):
        self.config = config

    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Shared geometry helpers used by all agents (kept here to avoid an extra
# module outside the prescribed file list).
# ---------------------------------------------------------------------------
_LINE_NODE_TYPES = (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)
_CURVE_NODE_TYPES = (NodeType.CIRCLE, NodeType.ARC)


def node_coords(node: Node) -> Optional[tuple[float, float]]:
    c = node.attrs.get("coords")
    if c is None or len(c) < 2:
        return None
    return float(c[0]), float(c[1])


def line_from_two_points(p, q) -> tuple[float, float, float]:
    """Return normalized (a, b, c) with a^2+b^2=1 for the line through p, q."""
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    a = dy
    b = -dx
    c = -(a * p[0] + b * p[1])
    n = math.hypot(a, b)
    if n < 1e-12:
        return 0.0, 0.0, 0.0
    return a / n, b / n, c / n


def line_coeffs(node: Node) -> Optional[tuple[float, float, float]]:
    """Normalized (a,b,c) for a Line/Segment/Ray node, or None."""
    if node.type not in _LINE_NODE_TYPES:
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


def line_direction(node: Node) -> Optional[tuple[float, float]]:
    coeffs = line_coeffs(node)
    if coeffs is None:
        return None
    a, b, _ = coeffs
    return (-b, a)


def line_length(node: Node) -> float:
    L = node.attrs.get("length")
    if L is not None:
        return float(L)
    ep = node.attrs.get("endpoints")
    if ep and len(ep) >= 2:
        return math.hypot(ep[1][0] - ep[0][0], ep[1][1] - ep[0][1])
    return 0.0


def point_line_distance(px: float, py: float, node: Node) -> Optional[float]:
    coeffs = line_coeffs(node)
    if coeffs is None:
        return None
    a, b, c = coeffs
    return abs(a * px + b * py + c)


def line_circle_distance(line: Node, circle: Node) -> Optional[tuple[float, tuple[float, float]]]:
    """Distance from circle center to line, plus foot of perpendicular."""
    coeffs = line_coeffs(line)
    c = circle.attrs.get("center")
    if coeffs is None or c is None:
        return None
    a, b, cc = coeffs
    signed = a * c[0] + b * c[1] + cc
    d = abs(signed)
    foot = (c[0] - a * signed, c[1] - b * signed)
    return d, foot


def nearest_point_id(graph: GeometryGraph, target: tuple[float, float], tol: float = 5.0) -> Optional[str]:
    best_id = None
    best_d = tol
    for n in graph.nodes:
        if n.type != NodeType.POINT:
            continue
        pc = node_coords(n)
        if pc is None:
            continue
        d = math.hypot(pc[0] - target[0], pc[1] - target[1])
        if d <= best_d:
            best_d = d
            best_id = n.id
    return best_id


def angle_between_dirs(u: tuple[float, float], v: tuple[float, float]) -> Optional[float]:
    nu = math.hypot(*u)
    nv = math.hypot(*v)
    if nu < 1e-9 or nv < 1e-9:
        return None
    cos = (u[0] * v[0] + u[1] * v[1]) / (nu * nv)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(abs(cos)))
