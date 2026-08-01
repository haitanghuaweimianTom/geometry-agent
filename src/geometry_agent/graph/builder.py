"""GraphBuilder: PrimitiveSet -> GeometryGraph (nodes only).

Registers every primitive as a Node with its raw geometry in `attrs`.
Does NOT call agents or verifier (see design/03 §6.1, pipeline.py).
"""

from __future__ import annotations

from ..config import GraphConfig
from ..types import (
    Circle,
    GeometryGraph,
    GraphMetaData,
    Line,
    LineType,
    Node,
    NodeType,
    Point,
    PointSource,
    Polygon,
    PrimitiveSet,
    Ellipse,
)


def _is_arc(c: Circle) -> bool:
    if c.coverage < 1.0:
        return True
    return c.arc_range is not None


def _register_point(p: Point) -> Node:
    return Node(
        id=p.id,
        type=NodeType.POINT,
        label=p.label,
        attrs={
            "coords": [float(p.coords[0]), float(p.coords[1])],
            "confidence": float(p.confidence),
            "source": p.source.value if isinstance(p.source, PointSource) else str(p.source),
            "subpixel": bool(p.subpixel),
        },
    )


def _register_line(L: Line) -> Node:
    if L.type == LineType.LINE:
        ntype = NodeType.LINE
    elif L.type == LineType.RAY:
        ntype = NodeType.RAY
    else:
        ntype = NodeType.SEGMENT
    attrs: dict = {"confidence": float(L.confidence)}
    if L.endpoints:
        attrs["endpoints"] = [[float(e[0]), float(e[1])] for e in L.endpoints]
    if L.equation:
        attrs["equation"] = {
            "a": float(L.equation.a),
            "b": float(L.equation.b),
            "c": float(L.equation.c),
        }
    if L.length is not None:
        attrs["length"] = float(L.length)
    return Node(id=L.id, type=ntype, label=L.label, attrs=attrs)


def _register_circle(c: Circle) -> Node:
    attrs: dict = {
        "center": [float(c.center[0]), float(c.center[1])],
        "radius": float(c.radius),
        "fit_residual": float(c.fit_residual),
        "coverage": float(c.coverage),
        "confidence": float(c.confidence),
    }
    if c.arc_range:
        attrs["arc_range"] = [float(c.arc_range[0]), float(c.arc_range[1])]
    return Node(
        id=c.id,
        type=NodeType.ARC if _is_arc(c) else NodeType.CIRCLE,
        label=c.label,
        attrs=attrs,
    )


def _register_ellipse(e: Ellipse) -> Node:
    attrs: dict = {
        "center": [float(e.center[0]), float(e.center[1])],
        "semi_major": float(e.semi_major),
        "semi_minor": float(e.semi_minor),
        "rotation": float(e.rotation),
        "foci": [[float(f[0]), float(f[1])] for f in e.foci],
        "eccentricity": float(e.eccentricity),
        "fit_residual": float(e.fit_residual),
        "confidence": float(e.confidence),
    }
    return Node(id=e.id, type=NodeType.ELLIPSE, label=e.label, attrs=attrs)


def _register_polygon(poly: Polygon) -> Node:
    attrs: dict = {
        "vertices": [[float(v[0]), float(v[1])] for v in poly.vertices],
        "poly_type": poly.poly_type,
        "confidence": float(poly.confidence),
    }
    return Node(id=poly.id, type=NodeType.POLYGON, label=poly.label, attrs=attrs)


class GraphBuilder:
    """Builds a node-only GeometryGraph from a PrimitiveSet."""

    def __init__(self, config: GraphConfig | None = None):
        self.config = config or GraphConfig()

    def build(self, primitives: PrimitiveSet) -> GeometryGraph:
        nodes: list[Node] = []
        for p in primitives.points:
            nodes.append(_register_point(p))
        for L in primitives.lines:
            nodes.append(_register_line(L))
        for c in primitives.circles:
            nodes.append(_register_circle(c))
        for e in primitives.ellipses:
            nodes.append(_register_ellipse(e))
        for poly in primitives.polygons:
            nodes.append(_register_polygon(poly))

        metadata = GraphMetaData(
            image_size=tuple(primitives.metadata.image_size),  # type: ignore[arg-type]
            scale_px_per_cm=float(primitives.metadata.scale_px_per_cm),
            version="1.0",
        )
        graph = GeometryGraph(nodes=nodes, edges=[], metadata=metadata)

        # Marks are not part of the Node schema; carry them on the graph object
        # so MarkAgent can read them at extraction time (design/04 §9).
        object.__setattr__(graph, "_marks", list(primitives.marks))
        object.__setattr__(graph, "_primitive_metadata", primitives.metadata)
        return graph
