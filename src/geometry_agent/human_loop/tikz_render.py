"""Render a GeometryGraph to a TikZ figure (geometry diagram redraw).

The diagram is rebuilt from the parsed node coordinates (not from the original
raster image), so the user sees exactly what the Agent understood. Pixel
coordinates (y-down) are flipped to TikZ (y-up) and scaled to a readable size.

Public API: :func:`graph_to_tikz`.
"""

from __future__ import annotations

import math
from typing import Any

from ..types import GeometryGraph, Node, NodeType


def _segment_endpoints(n: Node) -> tuple[list, list] | None:
    """Extract the two endpoints of a Segment/Line/Ray node.

    Supports both ``endpoints`` (``[[x1,y1],[x2,y2]]``) and legacy
    ``p1``/``p2`` attribute layouts.
    """
    a = n.attrs
    ep = a.get("endpoints")
    if ep and len(ep) >= 2:
        return list(ep[0]), list(ep[1])
    p1 = a.get("p1")
    p2 = a.get("p2")
    if p1 and p2:
        return list(p1), list(p2)
    return None


def _coords_of(node: Node) -> tuple[float, float] | None:
    a = node.attrs
    if node.type == NodeType.POINT:
        c = a.get("coords")
        if c is not None:
            return (float(c[0]), float(c[1]))
    if node.type == NodeType.CIRCLE:
        c = a.get("center")
        if c is not None:
            return (float(c[0]), float(c[1]))
    if node.type == NodeType.ELLIPSE:
        c = a.get("center")
        if c is not None:
            return (float(c[0]), float(c[1]))
    if node.type in (NodeType.SEGMENT, NodeType.LINE, NodeType.RAY):
        ep = _segment_endpoints(node)
        if ep:
            return (float(ep[0][0]), float(ep[0][1]))
    return None


def _ellipse_extent(a: float, b: float, rot_rad: float) -> tuple[float, float]:
    """Axis-aligned half-extents (sx, sy) of a rotated ellipse.

    For a rotation ``rot_rad`` (radians) the extents are
    ``sqrt((a*cos)^2 + (b*sin)^2)`` along x and
    ``sqrt((a*sin)^2 + (b*cos)^2)`` along y.
    """
    c, s = math.cos(rot_rad), math.sin(rot_rad)
    sx = math.hypot(a * c, b * s)
    sy = math.hypot(a * s, b * c)
    return sx, sy


def _arc_angles(n: Node) -> tuple[float, float] | None:
    """Extract (start, end) angles in radians for an Arc node.

    Prefers ``arc_range`` (list of two radians, as produced by the graph
    builder); falls back to legacy ``start_angle``/``end_angle`` (degrees).
    """
    a = n.attrs
    ar = a.get("arc_range")
    if ar and len(ar) >= 2:
        return float(ar[0]), float(ar[1])
    a0 = a.get("start_angle")
    a1 = a.get("end_angle")
    if a0 is not None and a1 is not None:
        return math.radians(float(a0)), math.radians(float(a1))
    return None


def _arc_sample_points(
    n: Node, steps: int = 48
) -> list[tuple[float, float]] | None:
    """Sample an Arc node into pixel-space points (for drawing + bbox).

    Returns ``[(x, y), ...]`` in pixel coordinates, or None when the node
    cannot be drawn. Sampling (instead of a native TikZ ``arc``) keeps huge
    radii from generating absurd ``start/end angle`` artifacts and lets the
    y-flip be applied per-point.
    """
    c = n.attrs.get("center")
    r = n.attrs.get("radius")
    if not c or not r:
        return None
    angles = _arc_angles(n)
    if angles is None:
        return None
    a0, a1 = angles
    r = float(r)
    cx, cy = float(c[0]), float(c[1])
    if a1 < a0:
        a1 += 2 * math.pi
    if a1 - a0 > 2 * math.pi:  # degenerate full circle
        a1 = a0 + 2 * math.pi
    pts = []
    for i in range(steps + 1):
        t = a0 + (a1 - a0) * i / steps
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def _bbox(graph: GeometryGraph) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for n in graph.nodes:
        c = _coords_of(n)
        if c:
            xs.append(c[0]); ys.append(c[1])
        # include circle/ellipse extent
        if n.type == NodeType.CIRCLE:
            r = float(n.attrs.get("radius", 0) or 0)
            cx, cy = c if c else (0, 0)
            xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
        elif n.type == NodeType.ELLIPSE:
            a = float(n.attrs.get("semi_major", 0) or 0)
            b = float(n.attrs.get("semi_minor", 0) or 0)
            rot = float(n.attrs.get("rotation", 0) or 0)
            sx, sy = _ellipse_extent(a, b, rot)
            cx, cy = c if c else (0, 0)
            xs += [cx - sx, cx + sx]; ys += [cy - sy, cy + sy]
        elif n.type == NodeType.ARC:
            pts = _arc_sample_points(n)
            if pts:
                xs += [p[0] for p in pts]
                ys += [p[1] for p in pts]
        elif n.type in (NodeType.SEGMENT, NodeType.LINE, NodeType.RAY):
            ep = _segment_endpoints(n)
            if ep:
                xs.append(float(ep[1][0])); ys.append(float(ep[1][1]))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def graph_to_tikz(
    graph: GeometryGraph,
    target_cm: float = 12.0,
    y_up: bool = False,
    axes: bool = False,
) -> str:
    """Build a TikZ picture string redrawing the geometry from node coords.

    ``y_up=True`` treats the node coordinates as mathematical coordinates
    (y pointing up, e.g. hand-built graphs for report figures); by default
    coordinates are pixel coordinates (y-down) and get flipped, matching the
    perception pipeline. ``axes=True`` draws an XOY coordinate frame through
    the origin (or the bbox center when the origin is outside).

    Returns an empty string when no plottable coordinates exist.
    """
    bbox = _bbox(graph)
    if bbox is None:
        return ""

    min_x, min_y, max_x, max_y = bbox
    w0 = max(max_x - min_x, 1e-6)
    h0 = max(max_y - min_y, 1e-6)
    # pad so line extensions (LINE nodes draw +/-10%) and labels stay inside
    pad = 0.05 * max(w0, h0)
    min_x, min_y = min_x - pad, min_y - pad
    max_x, max_y = max_x + pad, max_y + pad
    w = max_x - min_x
    h = max_y - min_y
    scale = target_cm / max(w, h)

    def tx(px: float) -> str:
        return _fmt((px - min_x) * scale)

    def ty(py: float) -> str:
        if y_up:
            return _fmt((py - min_y) * scale)
        return _fmt((max_y - py) * scale)  # flip y

    def tr(r: float) -> str:
        return _fmt(r * scale)

    lines: list[str] = []
    lines.append(r"\begin{center}")
    lines.append(r"\begin{tikzpicture}[>=latex]")

    # 0. Coordinate axes (bottom layer)
    if axes:
        ox = 0.0 if min_x <= 0.0 <= max_x else (min_x + max_x) / 2
        oy = 0.0 if min_y <= 0.0 <= max_y else (min_y + max_y) / 2
        lines.append(rf"\draw[->, thin] ({tx(min_x)},{ty(oy)}) -- ({tx(max_x)},{ty(oy)});")
        lines.append(rf"\draw[->, thin] ({tx(ox)},{ty(min_y)}) -- ({tx(ox)},{ty(max_y)});")
        lines.append(rf"\node[below right] at ({tx(max_x)},{ty(oy)}) {{$\small x$}};")
        lines.append(rf"\node[above left] at ({tx(ox)},{ty(max_y)}) {{$\small y$}};")

    # 1. Circles, ellipses & arcs first (so points/lines overlay)
    for n in graph.nodes:
        if n.type == NodeType.CIRCLE:
            c = n.attrs.get("center")
            r = n.attrs.get("radius")
            if c and r:
                lines.append(
                    rf"\draw[thick] ({tx(c[0])},{ty(c[1])}) circle ({tr(float(r))});"
                )
        elif n.type == NodeType.ELLIPSE:
            c = n.attrs.get("center")
            a = n.attrs.get("semi_major")
            b = n.attrs.get("semi_minor")
            if c and a and b:
                rot = float(n.attrs.get("rotation", 0) or 0)
                # pixel y-down -> TikZ y-up mirrors rotation; negate to
                # preserve the visual orientation (math coords need no mirror)
                rot_deg = rot * 180 / math.pi if y_up else -rot * 180 / math.pi
                if abs(rot_deg) < 1e-9:
                    rot_deg = 0.0
                lines.append(
                    rf"\draw[thick] ({tx(c[0])},{ty(c[1])}) "
                    rf"ellipse [x radius={tr(float(a))}, y radius={tr(float(b))}, "
                    rf"rotate={rot_deg:.1f}];"
                )
        elif n.type == NodeType.ARC:
            pts = _arc_sample_points(n)
            if pts:
                path = " -- ".join(rf"({tx(x)},{ty(y)})" for x, y in pts)
                lines.append(rf"\draw[thick] {path};")

    # 2. Lines / segments / rays
    for n in graph.nodes:
        if n.type in (NodeType.SEGMENT, NodeType.LINE, NodeType.RAY):
            ep = _segment_endpoints(n)
            if not ep:
                continue
            p1, p2 = ep
            if n.type == NodeType.SEGMENT:
                lines.append(
                    rf"\draw[thick] ({tx(p1[0])},{ty(p1[1])}) -- "
                    rf"({tx(p2[0])},{ty(p2[1])});"
                )
            elif n.type == NodeType.LINE:
                # extend by 10% on both ends
                dx = p2[0] - p1[0]; dy = p2[1] - p1[1]
                lines.append(
                    rf"\draw[thick] ({tx(p1[0]-0.1*dx)},{ty(p1[1]-0.1*dy)}) -- "
                    rf"({tx(p2[0]+0.1*dx)},{ty(p2[1]+0.1*dy)});"
                )
            else:  # RAY
                lines.append(
                    rf"\draw[thick, ->] ({tx(p1[0])},{ty(p1[1])}) -- "
                    rf"({tx(p2[0])},{ty(p2[1])});"
                )

    # 3. Polygons
    for n in graph.nodes:
        if n.type == NodeType.POLYGON:
            verts = n.attrs.get("vertices") or n.attrs.get("vertices_labels") or []
            if len(verts) >= 2:
                pts = " -- ".join(
                    rf"({tx(float(v[0]))},{ty(float(v[1]))})" for v in verts
                )
                lines.append(rf"\draw[thick] {pts} -- cycle;")

    # 4. Points + labels (on top)
    for n in graph.nodes:
        if n.type == NodeType.POINT:
            c = n.attrs.get("coords")
            if c is None:
                continue
            x, y = tx(c[0]), ty(c[1])
            label = n.label or ""
            lines.append(rf"\fill ({x},{y}) circle (1.8pt);")
            if label:
                lines.append(
                    rf"\node[above right] at ({x},{y}) "
                    rf"{{\small {_tex_safe(label)}}};"
                )

    lines.append(r"\end{tikzpicture}")
    lines.append(r"\end{center}")
    return "\n".join(lines) + "\n"


def _tex_safe(s: str) -> str:
    out = []
    for ch in str(s):
        if ch in "%&$#_{}":
            out.append("\\" + ch)
        elif ch == "\\":
            out.append(r"\textbackslash{}")
        elif ch == "^":
            out.append(r"\textasciicircum{}")
        elif ch == "~":
            out.append(r"\textasciitilde{}")
        else:
            out.append(ch)
    return "".join(out)


__all__ = ["graph_to_tikz"]
