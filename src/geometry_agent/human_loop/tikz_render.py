"""Render a GeometryGraph to a TikZ figure (geometry diagram redraw).

The diagram is rebuilt from the parsed node coordinates (not from the original
raster image), so the user sees exactly what the Agent understood. Pixel
coordinates (y-down) are flipped to TikZ (y-up) and scaled to a readable size.

Public API: :func:`graph_to_tikz`.
"""

from __future__ import annotations

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
            cx, cy = c if c else (0, 0)
            xs += [cx - a, cx + a]; ys += [cy - b, cy + b]
        elif n.type in (NodeType.SEGMENT, NodeType.LINE, NodeType.RAY):
            ep = _segment_endpoints(n)
            if ep:
                xs.append(float(ep[1][0])); ys.append(float(ep[1][1]))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def graph_to_tikz(graph: GeometryGraph, target_cm: float = 12.0) -> str:
    """Build a TikZ picture string redrawing the geometry from node coords.

    Returns an empty string when no plottable coordinates exist.
    """
    bbox = _bbox(graph)
    if bbox is None:
        return ""

    min_x, min_y, max_x, max_y = bbox
    w = max(max_x - min_x, 1e-6)
    h = max(max_y - min_y, 1e-6)
    scale = target_cm / max(w, h)

    def tx(px: float) -> str:
        return _fmt((px - min_x) * scale)

    def ty(py: float) -> str:
        return _fmt((max_y - py) * scale)  # flip y

    def tr(r: float) -> str:
        return _fmt(r * scale)

    lines: list[str] = []
    lines.append(r"\begin{center}")
    lines.append(r"\begin{tikzpicture}[>=latex]")

    # 1. Circles & ellipses first (so points/lines overlay)
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
                # TikZ rotate is in degrees, our rotation is radians
                rot_deg = rot * 180 / 3.141592653589793
                lines.append(
                    rf"\draw[thick] ({tx(c[0])},{ty(c[1])}) "
                    rf"ellipse [x radius={tr(float(a))}, y radius={tr(float(b))}, "
                    rf"rotate={rot_deg:.1f}];"
                )
        elif n.type == NodeType.ARC:
            c = n.attrs.get("center")
            r = n.attrs.get("radius")
            a0 = n.attrs.get("start_angle")
            a1 = n.attrs.get("end_angle")
            if c and r and a0 is not None and a1 is not None:
                # arc from a0 to a1 (radians); note y is flipped
                import math
                x0 = c[0] + float(r) * math.cos(float(a0))
                y0 = c[1] + float(r) * math.sin(float(a0))
                lines.append(
                    rf"\draw[thick] ({tx(x0)},{ty(y0)}) arc "
                    rf"[start angle={math.degrees(float(a0)):.1f}, "
                    rf"end angle={math.degrees(float(a1)):.1f}, "
                    rf"radius={tr(float(r))}];"
                )

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
