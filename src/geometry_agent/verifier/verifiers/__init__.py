"""Shared geometry helpers for verifiers."""

from __future__ import annotations

import math
from typing import Optional

from ...types import Node, NodeType

_LINE_NODE_TYPES = (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)
_CURVE_NODE_TYPES = (NodeType.CIRCLE, NodeType.ARC)


def line_from_two_points(p, q) -> tuple[float, float, float]:
    """Normalized (a,b,c) with a^2+b^2=1 for line through p, q."""
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
    """Normalized (a,b,c) for a Line/Segment/Ray node, else None."""
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


def proj_param(px: float, py: float, p, q) -> float:
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return 0.0
    return ((px - p[0]) * dx + (py - p[1]) * dy) / L2


def point_coords(node: Node) -> Optional[tuple[float, float]]:
    c = node.attrs.get("coords")
    if c is None or len(c) < 2:
        return None
    return float(c[0]), float(c[1])


def angle_between_dirs(u: tuple[float, float], v: tuple[float, float]) -> Optional[float]:
    nu = math.hypot(*u)
    nv = math.hypot(*v)
    if nu < 1e-9 or nv < 1e-9:
        return None
    cos = (u[0] * v[0] + u[1] * v[1]) / (nu * nv)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(abs(cos)))
