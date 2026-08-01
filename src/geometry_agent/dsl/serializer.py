"""Geometry DSL serializer: GeometryGraph -> text (design/06 §8).

Strategy (design §8.1):
  * only ``verified=true`` edges are emitted as relations;
  * ``uncertain`` edges are emitted as ``# uncertain: <rel>`` comments when
    ``DSLConfig.include_uncertain`` is set, otherwise dropped;
  * ``compact`` mode omits coordinate pairs (point coords, ellipse center) to
    save tokens -- topology and scalar parameters are preserved.

``to_dsl`` is the inverse of :func:`geometry_agent.dsl.parser.from_dsl` for the
subset of graph state representable in the DSL (nodes by type+label, verified
edges, goal).
"""

from __future__ import annotations

from typing import Any

from ..config import DSLConfig
from ..types import (
    Edge,
    GeometryGraph,
    Node,
    NodeType,
    RelType,
    VerifyState,
)

# NodeType -> DSL object keyword. Polygon/Triangle share NodeType.POLYGON and
# are disambiguated at call sites via attrs["dsl_kind"] / poly_type.
_NODETYPE_TO_KEYWORD = {
    NodeType.POINT: "Point",
    NodeType.LINE: "Line",
    NodeType.SEGMENT: "Segment",
    NodeType.RAY: "Ray",
    NodeType.CIRCLE: "Circle",
    NodeType.ARC: "Arc",
    NodeType.ELLIPSE: "Ellipse",
    NodeType.POLYGON: "Polygon",
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _fmt_num(x: Any) -> str:
    f = float(x)
    if f.is_integer():
        return str(int(f))
    return f"{f:g}"


def _fmt_coords(xy: Any) -> str:
    return f"[{_fmt_num(xy[0])}, {_fmt_num(xy[1])}]"


def _label_of(node: Node) -> str:
    return node.label or node.id


def _obj_keyword(node: Node) -> str:
    if node.type == NodeType.POLYGON:
        if node.attrs.get("dsl_kind") == "Triangle" or node.attrs.get("poly_type") == "triangle":
            return "Triangle"
    return _NODETYPE_TO_KEYWORD[node.type]


def _fmt_obj_ref(node: Node) -> str:
    return f"{_obj_keyword(node)}({_label_of(node)})"


# --------------------------------------------------------------------------- #
# object formatting
# --------------------------------------------------------------------------- #
def _fmt_object(node: Node, compact: bool) -> str:
    t = node.type
    label = _label_of(node)
    a = node.attrs
    if t == NodeType.POINT:
        coords = a.get("coords")
        if compact or coords is None:
            return f"Point({label})"
        return f"Point({label}): {_fmt_coords(coords)}"
    if t == NodeType.CIRCLE:
        r = a.get("radius", 0.0)
        return f"Circle({label}, r={_fmt_num(r)})"
    if t == NodeType.ARC:
        p1 = a.get("p1")
        p2 = a.get("p2")
        if p1 and p2:
            return f"Arc({label}, {p1}, {p2})"
        return f"Arc({label})"
    if t == NodeType.ELLIPSE:
        parts = [f"Ellipse({label}"]
        if not compact:
            c = a.get("center")
            if c is not None:
                parts.append(f"c={_fmt_coords(c)}")
        parts.append(f"a={_fmt_num(a.get('semi_major', 0.0))}")
        parts.append(f"b={_fmt_num(a.get('semi_minor', 0.0))}")
        parts.append(f"theta={_fmt_num(a.get('rotation', 0.0))}")
        return ", ".join(parts) + ")"
    if t in (NodeType.SEGMENT, NodeType.LINE, NodeType.RAY):
        kw = _obj_keyword(node)
        p1 = a.get("p1")
        p2 = a.get("p2")
        if t == NodeType.RAY and p1 is not None and a.get("dir") is not None:
            return f"{kw}({label}, {p1}, {_fmt_coords(a['dir'])})"
        if p1 and p2:
            return f"{kw}({label}, {p1}, {p2})"
        return f"{kw}({label})"
    if t == NodeType.POLYGON:
        kw = _obj_keyword(node)
        verts = a.get("vertices_labels") or []
        if verts:
            return f"{kw}({label}, {', '.join(verts)})"
        return f"{kw}({label})"
    return f"{_obj_keyword(node)}({label})"


# --------------------------------------------------------------------------- #
# relation formatting
# --------------------------------------------------------------------------- #
def _pt_label(node_by_id: dict[str, Node], nid: str) -> str:
    n = node_by_id.get(nid)
    return _label_of(n) if n is not None else nid


def _obj_ref_str(node_by_id: dict[str, Node], nid: str) -> str:
    n = node_by_id.get(nid)
    if n is None:
        return nid
    if n.type == NodeType.POINT:
        return _label_of(n)
    return _fmt_obj_ref(n)


def _fmt_relation(edge: Edge, node_by_id: dict[str, Node]) -> str:
    rel = edge.rel
    src_n = node_by_id.get(edge.src)
    dst_n = node_by_id.get(edge.dst)
    a = edge.attrs

    # DSL-specific kinds stored under attrs["dsl_kind"] (Angle / SumDist) -----
    dsl_kind = a.get("dsl_kind")
    if dsl_kind == "Angle":
        pts = a.get("point_ids") or a.get("points") or [edge.src, edge.dst]
        pts = [p for p in pts if isinstance(p, str)]
        labels = [_pt_label(node_by_id, p) for p in pts]
        val = a.get("angle", 0.0)
        if all(len(lab) == 1 for lab in labels) and len(labels) == 3:
            angle_label = "".join(labels)
            return f"Angle({angle_label}) = {_fmt_num(val)}deg"
        return f"Angle({', '.join(labels)}) = {_fmt_num(val)}deg"
    if dsl_kind == "SumDist":
        pts = a.get("point_ids") or a.get("points") or [edge.src, edge.dst]
        pts = [p for p in pts if isinstance(p, str)]
        labels = [_pt_label(node_by_id, p) for p in pts]
        expr = a.get("expr", "")
        return f"SumDist({', '.join(labels)}) = {expr}"

    # Collinear (n-ary) -------------------------------------------------------
    if rel == RelType.COLLINEAR:
        pts = a.get("point_ids") or [edge.src, edge.dst]
        labels = [_pt_label(node_by_id, p) for p in pts if isinstance(p, str)]
        return f"Collinear({', '.join(labels)})"

    # Tangent with optional at=<point> ---------------------------------------
    if rel == RelType.TANGENT:
        left = _obj_ref_str(node_by_id, edge.src)
        right = _obj_ref_str(node_by_id, edge.dst)
        tp = a.get("tangent_point")
        if tp:
            return f"Tangent({left}, {right}, at={_pt_label(node_by_id, tp)})"
        return f"Tangent({left}, {right})"

    # Binary object-object relations -----------------------------------------
    if rel in (
        RelType.INTERSECT, RelType.PARALLEL, RelType.PERPENDICULAR,
        RelType.EQUAL, RelType.CONCENTRIC, RelType.INSCRIBED,
        RelType.CIRCUMSCRIBED, RelType.SIMILAR, RelType.CONGRUENT,
    ):
        kw = rel.value
        return f"{kw}({_obj_ref_str(node_by_id, edge.src)}, {_obj_ref_str(node_by_id, edge.dst)})"

    # Point-object relations --------------------------------------------------
    if rel in (RelType.ON, RelType.INSIDE, RelType.OUTSIDE,
               RelType.CENTER, RelType.TANGENT_POINT):
        kw = rel.value
        pt = _pt_label(node_by_id, edge.src)
        obj = _obj_ref_str(node_by_id, edge.dst)
        return f"{kw}({pt}, {obj})"

    # Fallback (should not happen for representable relations)
    return f"{rel.value}({_obj_ref_str(node_by_id, edge.src)}, {_obj_ref_str(node_by_id, edge.dst)})"


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def to_dsl(graph: GeometryGraph, config: DSLConfig | None = None) -> str:
    """Serialize a :class:`GeometryGraph` to DSL text.

    Parameters
    ----------
    graph:
        The geometry world model to serialize.
    config:
        Serialization options. ``include_uncertain`` emits uncertain edges as
        ``# uncertain: ...`` comments; ``compact`` omits coordinates.
    """
    cfg = config or DSLConfig()
    node_by_id = {n.id: n for n in graph.nodes}
    lines: list[str] = []

    # ----- Objects -----
    lines.append("Objects:")
    for n in graph.nodes:
        lines.append(f"  - {_fmt_object(n, compact=cfg.compact)}")

    # ----- Relations -----
    verified_lines: list[str] = []
    uncertain_lines: list[str] = []
    for e in graph.edges:
        if e.verified == VerifyState.TRUE:
            verified_lines.append(f"  - {_fmt_relation(e, node_by_id)}")
        elif e.verified == VerifyState.UNCERTAIN and cfg.include_uncertain:
            uncertain_lines.append(f"  # uncertain: {_fmt_relation(e, node_by_id)}")

    if verified_lines or uncertain_lines:
        lines.append("Relations:")
        lines.extend(verified_lines)
        lines.extend(uncertain_lines)

    # ----- Goal -----
    if graph.goal:
        lines.append("Goal:")
        lines.append(f"  - {graph.goal.kind}: {graph.goal.statement}")

    return "\n".join(lines) + "\n"
