"""Self-contained geometric forward-chaining rule engine (design/08 §6).

Rules are expressed as ``(premise_patterns, conclude)`` pairs. Premise patterns
are matched against :class:`GeometryGraph` edges, binding logical variables to
node ids. When all premises match, ``conclude(binding, graph)`` produces a new
derived :class:`Edge` (or ``None``). Forward-chaining iterates until a fixed
point or ``max_iter`` is reached.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..types import (
    Edge,
    GeometryGraph,
    Node,
    NodeType,
    RelType,
    VerifyState,
)

_LINE_TYPES = (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)
_CURVE_TYPES = (NodeType.CIRCLE, NodeType.ARC)

Pattern = dict[str, Any]
Conclude = Callable[[dict[str, str], GeometryGraph], Optional[Edge]]


@dataclass
class Rule:
    rule_id: str
    premise_patterns: list[Pattern]
    conclude: Conclude
    description: str = ""
    distinct: bool = True


# --------------------------------------------------------------------------- #
# graph helpers
# --------------------------------------------------------------------------- #
def _node(graph: GeometryGraph, node_id: str) -> Optional[Node]:
    for n in graph.nodes:
        if n.id == node_id:
            return n
    return None


def _coords_eq(a: Any, b: Any, tol: float = 1e-6) -> bool:
    if a is None or b is None:
        return False
    try:
        return abs(float(a[0]) - float(b[0])) < tol and abs(float(a[1]) - float(b[1])) < tol
    except Exception:
        return False


def _type_match(node_type: NodeType, spec: Any) -> bool:
    if isinstance(spec, NodeType):
        return node_type == spec
    if isinstance(spec, (tuple, list)):
        return node_type in spec
    return True


def _center_point(graph: GeometryGraph, circle_id: str) -> Optional[str]:
    for e in graph.edges:
        if e.rel == RelType.CENTER and e.dst == circle_id:
            return e.src
    circle = _node(graph, circle_id)
    if circle is None:
        return None
    center = circle.attrs.get("center")
    if center is None:
        return None
    for n in graph.nodes:
        if n.type == NodeType.POINT and _coords_eq(n.attrs.get("coords"), center):
            return n.id
    return None


def _segment_by_endpoints(graph: GeometryGraph, c1: Any, c2: Any) -> Optional[str]:
    for n in graph.nodes:
        if n.type not in _LINE_TYPES:
            continue
        eps = n.attrs.get("endpoints")
        if not eps or len(eps) != 2:
            continue
        if (_coords_eq(eps[0], c1) and _coords_eq(eps[1], c2)) or (
            _coords_eq(eps[0], c2) and _coords_eq(eps[1], c1)
        ):
            return n.id
    return None


def _endpoints_of(graph: GeometryGraph, line_id: str) -> Optional[tuple[Any, Any]]:
    n = _node(graph, line_id)
    if n is None:
        return None
    eps = n.attrs.get("endpoints")
    if not eps or len(eps) != 2:
        return None
    return eps[0], eps[1]


def _point_coords(graph: GeometryGraph, point_id: str) -> Any:
    n = _node(graph, point_id)
    if n is None:
        return None
    return n.attrs.get("coords")


# --------------------------------------------------------------------------- #
# pattern matching
# --------------------------------------------------------------------------- #
def _try_bind(
    pat: Pattern,
    edge: Edge,
    binding: dict[str, str],
    graph: GeometryGraph,
    distinct: bool,
) -> Optional[dict[str, str]]:
    if edge.rel != pat["rel"]:
        return None
    b = dict(binding)
    used_ids = set(b.values())

    for side_key, edge_id in (("src", edge.src), ("dst", edge.dst)):
        spec = pat.get(side_key)
        if not spec:
            continue
        node = _node(graph, edge_id)
        if node is None:
            return None
        t = spec.get("type")
        if t is not None and not _type_match(node.type, t):
            return None
        var = spec.get("var")
        if var:
            if var in b:
                if b[var] != edge_id:
                    return None
            else:
                if distinct and edge_id in used_ids:
                    return None
                b[var] = edge_id
                used_ids = used_ids | {edge_id}

    for ak, av in pat.get("attrs", {}).items():
        if ak not in edge.attrs:
            return None
        val = edge.attrs[ak]
        if isinstance(av, dict) and "var" in av:
            var = av["var"]
            if var in b:
                if b[var] != val:
                    return None
            else:
                if distinct and val in used_ids:
                    return None
                b[var] = val
                used_ids = used_ids | {val}
        else:
            if val != av:
                return None
    return b


def _match_all(
    patterns: list[Pattern],
    edges_by_rel: dict[RelType, list[Edge]],
    graph: GeometryGraph,
    binding: dict[str, str],
    used: set[int],
    distinct: bool,
):
    if not patterns:
        yield dict(binding)
        return
    pat = patterns[0]
    for edge in edges_by_rel.get(pat["rel"], []):
        if id(edge) in used:
            continue
        nb = _try_bind(pat, edge, binding, graph, distinct)
        if nb is None:
            continue
        yield from _match_all(
            patterns[1:], edges_by_rel, graph, nb, used | {id(edge)}, distinct
        )


def _index_edges(graph: GeometryGraph) -> dict[RelType, list[Edge]]:
    idx: dict[RelType, list[Edge]] = {}
    for e in graph.edges:
        idx.setdefault(e.rel, []).append(e)
    return idx


def _edge_key(edge: Edge) -> tuple[str, str, RelType]:
    return (edge.src, edge.dst, edge.rel)


def forward_chain(
    graph: GeometryGraph, rules: list[Rule], max_iter: int = 10
) -> GeometryGraph:
    """Apply rules repeatedly until a fixed point or ``max_iter`` reached."""
    for _ in range(max_iter):
        edges_by_rel = _index_edges(graph)
        existing = {_edge_key(e) for e in graph.edges}
        changed = False
        for rule in rules:
            for binding in _match_all(
                rule.premise_patterns, edges_by_rel, graph, {}, set(), rule.distinct
            ):
                new_edge = rule.conclude(binding, graph)
                if new_edge is None:
                    continue
                key = _edge_key(new_edge)
                if key in existing:
                    continue
                graph.edges.append(new_edge)
                existing.add(key)
                changed = True
        if not changed:
            break
    return graph


# --------------------------------------------------------------------------- #
# built-in rules (design/08 §6.2)
# --------------------------------------------------------------------------- #
def _r1_conclude(b: dict[str, str], graph: GeometryGraph) -> Optional[Edge]:
    L1, L2 = b.get("L1"), b.get("L2")
    if not L1 or not L2:
        return None
    ep1 = _endpoints_of(graph, L1)
    ep2 = _endpoints_of(graph, L2)
    if not ep1 or not ep2:
        return None
    A, B, C, D = b.get("A"), b.get("B"), b.get("C"), b.get("D")
    ac = _point_coords(graph, A) if A else None
    bc = _point_coords(graph, B) if B else None
    cc = _point_coords(graph, C) if C else None
    dc = _point_coords(graph, D) if D else None
    ok1 = (_coords_eq(ep1[0], ac) and _coords_eq(ep1[1], bc)) or (
        _coords_eq(ep1[0], bc) and _coords_eq(ep1[1], ac)
    )
    ok2 = (_coords_eq(ep2[0], cc) and _coords_eq(ep2[1], dc)) or (
        _coords_eq(ep2[0], dc) and _coords_eq(ep2[1], cc)
    )
    if not (ok1 and ok2):
        return None
    return Edge(
        src=L1,
        dst=L2,
        rel=RelType.EQUAL,
        confidence=1.0,
        verified=VerifyState.TRUE,
        evidence="R1:inscribed angle (same arc)",
        source="derived",
        attrs={"rule": "R1", "note": "Angle(ACB)=Angle(ADB)"},
    )


def _r2_conclude(b: dict[str, str], graph: GeometryGraph) -> Optional[Edge]:
    A = b.get("A")
    circ = b.get("O_circle")
    L = b.get("L")
    if not (A and circ and L):
        return None
    O = _center_point(graph, circ)
    if O is None:
        return None
    ac = _point_coords(graph, A)
    oc = _point_coords(graph, O)
    if ac is None or oc is None:
        return None
    OA = _segment_by_endpoints(graph, oc, ac)
    if OA is None:
        return None
    return Edge(
        src=OA,
        dst=L,
        rel=RelType.PERPENDICULAR,
        confidence=1.0,
        verified=VerifyState.TRUE,
        evidence="R2:tangent perpendicular to radius",
        source="derived",
        attrs={"rule": "R2"},
    )


def _r3_conclude(b: dict[str, str], graph: GeometryGraph) -> Optional[Edge]:
    T1, T2 = b.get("T1"), b.get("T2")
    if not (T1 and T2):
        return None
    return Edge(
        src=T1,
        dst=T2,
        rel=RelType.EQUAL,
        confidence=1.0,
        verified=VerifyState.TRUE,
        evidence="R3:similar triangles corresponding sides proportional",
        source="derived",
        attrs={"rule": "R3", "note": "AB/DE=BC/EF=AC/DF"},
    )


def _r4_conclude(b: dict[str, str], graph: GeometryGraph) -> Optional[Edge]:
    L1, L2 = b.get("L1"), b.get("L2")
    if not (L1 and L2):
        return None
    ep1 = _endpoints_of(graph, L1)
    ep2 = _endpoints_of(graph, L2)
    if not ep1 or not ep2:
        return None
    shared = None
    for c in ep1:
        for d in ep2:
            if _coords_eq(c, d):
                shared = c
                break
        if shared is not None:
            break
    if shared is None:
        return None
    A_coords = shared
    B_coords = ep1[0] if _coords_eq(ep1[1], shared) else ep1[1]
    C_coords = ep2[0] if _coords_eq(ep2[1], shared) else ep2[1]
    BC = _segment_by_endpoints(graph, B_coords, C_coords)
    if BC is None:
        return None
    return Edge(
        src=L1,
        dst=BC,
        rel=RelType.EQUAL,
        confidence=1.0,
        verified=VerifyState.TRUE,
        evidence="R4:Pythagorean theorem",
        source="derived",
        attrs={"rule": "R4", "expr": "AB^2+AC^2=BC^2"},
    )


def _r5_conclude(b: dict[str, str], graph: GeometryGraph) -> Optional[Edge]:
    P, E = b.get("P"), b.get("E")
    if not (P and E):
        return None
    ellipse = _node(graph, E)
    if ellipse is None or ellipse.type != NodeType.ELLIPSE:
        return None
    foci = ellipse.attrs.get("foci") or []
    semi_major = ellipse.attrs.get("semi_major")
    if len(foci) < 2 or semi_major is None:
        return None
    return Edge(
        src=P,
        dst=E,
        rel=RelType.EQUAL,
        confidence=1.0,
        verified=VerifyState.TRUE,
        evidence="R5:ellipse definition",
        source="derived",
        attrs={"rule": "R5", "expr": "PF1+PF2=2a", "foci": foci, "a": semi_major},
    )


BUILTIN_RULES: list[Rule] = [
    Rule(
        rule_id="R1",
        description="同弧圆周角相等 (inscribed angles subtending the same arc are equal)",
        premise_patterns=[
            {"rel": RelType.ON, "src": {"var": "A", "type": NodeType.POINT},
             "dst": {"var": "O_circle", "type": _CURVE_TYPES}},
            {"rel": RelType.ON, "src": {"var": "B", "type": NodeType.POINT},
             "dst": {"var": "O_circle"}},
            {"rel": RelType.ON, "src": {"var": "C", "type": NodeType.POINT},
             "dst": {"var": "O_circle"}},
            {"rel": RelType.ON, "src": {"var": "D", "type": NodeType.POINT},
             "dst": {"var": "O_circle"}},
            {"rel": RelType.SAME_ARC, "src": {"var": "L1", "type": _LINE_TYPES},
             "dst": {"var": "L2", "type": _LINE_TYPES}},
        ],
        conclude=_r1_conclude,
    ),
    Rule(
        rule_id="R2",
        description="切线垂直于过切点的半径 (tangent ⟂ radius at tangent point)",
        premise_patterns=[
            {"rel": RelType.ON, "src": {"var": "A", "type": NodeType.POINT},
             "dst": {"var": "O_circle", "type": _CURVE_TYPES}},
            {"rel": RelType.TANGENT, "src": {"var": "L", "type": _LINE_TYPES},
             "dst": {"var": "O_circle"},
             "attrs": {"tangent_point": {"var": "A"}}},
        ],
        conclude=_r2_conclude,
    ),
    Rule(
        rule_id="R3",
        description="相似三角形对应边成比例 (similar triangles → proportional sides)",
        premise_patterns=[
            {"rel": RelType.SIMILAR, "src": {"var": "T1", "type": NodeType.POLYGON},
             "dst": {"var": "T2", "type": NodeType.POLYGON}},
        ],
        conclude=_r3_conclude,
    ),
    Rule(
        rule_id="R4",
        description="勾股定理 (Pythagorean theorem for right triangles)",
        premise_patterns=[
            {"rel": RelType.PERPENDICULAR, "src": {"var": "L1", "type": _LINE_TYPES},
             "dst": {"var": "L2", "type": _LINE_TYPES}},
        ],
        conclude=_r4_conclude,
    ),
    Rule(
        rule_id="R5",
        description="椭圆定义 (sum of distances to foci = 2a)",
        premise_patterns=[
            {"rel": RelType.ON, "src": {"var": "P", "type": NodeType.POINT},
             "dst": {"var": "E", "type": NodeType.ELLIPSE}},
        ],
        conclude=_r5_conclude,
    ),
]
