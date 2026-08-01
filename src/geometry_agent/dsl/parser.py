"""Geometry DSL parser: text -> GeometryGraph (design/06 §7).

Pipeline:
    DSL text --lark--> concrete tree --Transformer--> ASTProgram
           --semantic checks--> GeometryGraph

Semantic checks performed here:
  * reference integrity (every PointRef / ObjRef is declared in Objects)
  * type consistency (e.g. On expects Point + Curve; Perpendicular expects two
    line-like objects)
  * duplicate declaration detection

Uncertain relations are emitted by the serializer as ``# uncertain: <rel>``
comments; this parser recognises that convention and reconstructs them with
``verified=uncertain``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lark import Lark, Transformer, UnexpectedInput

from ..types import (
    Edge,
    GeometryGraph,
    GoalSpec,
    Node,
    NodeType,
    RelType,
    VerifyState,
)
from .ast_nodes import ASTGoal, ASTObject, ASTProgram, ASTRelation

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"


# --------------------------------------------------------------------------- #
# Node id convention (type-prefixed to stay collision-free across object kinds)
# --------------------------------------------------------------------------- #
_ID_PREFIX = {
    "Point": "P",
    "Segment": "S",
    "Line": "L",
    "Ray": "R",
    "Circle": "C",
    "Arc": "A",
    "Ellipse": "E",
    "Polygon": "Poly",
    "Triangle": "Poly",
}

_KIND_TO_NODETYPE = {
    "Point": NodeType.POINT,
    "Segment": NodeType.SEGMENT,
    "Line": NodeType.LINE,
    "Ray": NodeType.RAY,
    "Circle": NodeType.CIRCLE,
    "Arc": NodeType.ARC,
    "Ellipse": NodeType.ELLIPSE,
    "Polygon": NodeType.POLYGON,
    "Triangle": NodeType.POLYGON,
}


def _node_id(kind: str, label: str) -> str:
    return f"{_ID_PREFIX[kind]}_{label}"


# --------------------------------------------------------------------------- #
# Parser construction
# --------------------------------------------------------------------------- #
_PARSER: Lark | None = None


def _parser() -> Lark:
    global _PARSER
    if _PARSER is None:
        _PARSER = Lark(_GRAMMAR_PATH.read_text(encoding="utf-8"), start="start",
                       parser="earley", maybe_placeholders=False)
    return _PARSER


# --------------------------------------------------------------------------- #
# Tree -> AST
# --------------------------------------------------------------------------- #
def _as_str(tok: Any) -> str:
    return str(tok)


def _as_float(tok: Any) -> float:
    return float(tok)


class _ASTBuilder(Transformer):
    # --- containers ---
    def start(self, items):
        prog = ASTProgram()
        for it in items:
            if isinstance(it, _Objects):
                prog.objects.extend(it.objs)
            elif isinstance(it, _Relations):
                prog.relations.extend(it.rels)
            elif isinstance(it, ASTGoal):
                prog.goal = it
        return prog

    def section(self, items):
        return items[0]

    def objects_section(self, items):
        return _Objects([o for o in items if isinstance(o, ASTObject)])

    def relations_section(self, items):
        return _Relations([r for r in items if isinstance(r, ASTRelation)])

    def goal_section(self, items):
        return items[0]

    def object_decl(self, items):
        return items[0]

    def object_expr(self, items):
        return items[0]

    def relation_decl(self, items):
        return items[0]

    def relation_expr(self, items):
        return items[0]

    def goal_decl(self, items):
        return items[0]

    def goal_expr(self, items):
        return items[0]

    # --- objects ---
    def coords(self, items):
        return [_as_float(items[0]), _as_float(items[1])]

    def point_decl(self, items):
        label = _as_str(items[0])
        attrs: dict[str, Any] = {}
        if len(items) > 1:
            attrs["coords"] = items[1]
        return ASTObject("Point", label, attrs)

    def segment_decl(self, items):
        return ASTObject("Segment", _as_str(items[0]))

    def line_decl(self, items):
        label = _as_str(items[0])
        attrs: dict[str, Any] = {}
        if len(items) > 1:
            attrs["p1"] = _as_str(items[1])
            attrs["p2"] = _as_str(items[2])
        return ASTObject("Line", label, attrs)

    def ray_decl(self, items):
        label = _as_str(items[0])
        attrs: dict[str, Any] = {}
        if len(items) > 1:
            attrs["p1"] = _as_str(items[1])
            attrs["dir"] = items[2]
        return ASTObject("Ray", label, attrs)

    def circle_decl(self, items):
        return ASTObject("Circle", _as_str(items[0]), {"radius": _as_float(items[1])})

    def arc_decl(self, items):
        return ASTObject(
            "Arc", _as_str(items[0]),
            {"p1": _as_str(items[1]), "p2": _as_str(items[2])},
        )

    def ellipse_decl(self, items):
        return ASTObject(
            "Ellipse", _as_str(items[0]),
            {
                "center": items[1],
                "semi_major": _as_float(items[2]),
                "semi_minor": _as_float(items[3]),
                "rotation": _as_float(items[4]),
            },
        )

    def polygon_decl(self, items):
        label = _as_str(items[0])
        verts = [_as_str(it) for it in items[1:]]
        return ASTObject("Polygon", label, {"vertices_labels": verts})

    def triangle_decl(self, items):
        label = _as_str(items[0])
        attrs: dict[str, Any] = {"dsl_kind": "Triangle"}
        if len(items) > 1:
            attrs["vertices_labels"] = [
                _as_str(items[1]), _as_str(items[2]), _as_str(items[3])
            ]
        return ASTObject("Triangle", label, attrs)

    # --- obj refs ---
    def segment_obj(self, items):
        return ("obj", "Segment", _as_str(items[0]))

    def line_obj(self, items):
        return ("obj", "Line", _as_str(items[0]))

    def ray_obj(self, items):
        return ("obj", "Ray", _as_str(items[0]))

    def circle_obj(self, items):
        return ("obj", "Circle", _as_str(items[0]))

    def arc_obj(self, items):
        return ("obj", "Arc", _as_str(items[0]))

    def ellipse_obj(self, items):
        return ("obj", "Ellipse", _as_str(items[0]))

    def polygon_obj(self, items):
        return ("obj", "Polygon", _as_str(items[0]))

    def triangle_obj(self, items):
        return ("obj", "Triangle", _as_str(items[0]))

    def obj_call(self, items):
        return items[0]

    def obj_ref(self, items):
        arg = items[0]
        if isinstance(arg, tuple):
            return arg
        # bare label -> object reference of unknown type, resolved later
        return ("obj", None, _as_str(arg))

    # --- relations ---
    def _point_arg(self, label):
        return ("point", _as_str(label))

    def on_rel(self, items):
        return ASTRelation(
            "On",
            args=[self._point_arg(items[0]), items[1]],
        )

    def collinear_rel(self, items):
        return ASTRelation(
            "Collinear",
            args=[self._point_arg(p) for p in items],
        )

    def intersect_rel(self, items):
        return ASTRelation("Intersect", args=[items[0], items[1]])

    def tangent_rel(self, items):
        attrs: dict[str, Any] = {}
        if len(items) > 2:
            attrs["tangent_point"] = _as_str(items[2])
        return ASTRelation("Tangent", args=[items[0], items[1]], attrs=attrs)

    def parallel_rel(self, items):
        return ASTRelation("Parallel", args=[items[0], items[1]])

    def perpendicular_rel(self, items):
        return ASTRelation("Perpendicular", args=[items[0], items[1]])

    def equal_rel(self, items):
        return ASTRelation("Equal", args=[items[0], items[1]])

    def inside_rel(self, items):
        return ASTRelation("Inside", args=[self._point_arg(items[0]), items[1]])

    def outside_rel(self, items):
        return ASTRelation("Outside", args=[self._point_arg(items[0]), items[1]])

    def concentric_rel(self, items):
        return ASTRelation("Concentric", args=[items[0], items[1]])

    def inscribed_rel(self, items):
        return ASTRelation("Inscribed", args=[items[0], items[1]])

    def circumscribed_rel(self, items):
        return ASTRelation("Circumscribed", args=[items[0], items[1]])

    def similar_rel(self, items):
        return ASTRelation("Similar", args=[items[0], items[1]])

    def congruent_rel(self, items):
        return ASTRelation("Congruent", args=[items[0], items[1]])

    def center_rel(self, items):
        return ASTRelation("Center", args=[self._point_arg(items[0]), items[1]])

    def tangent_point_rel(self, items):
        return ASTRelation("TangentPoint", args=[self._point_arg(items[0]), items[1]])

    def angle_args(self, items):
        if len(items) == 1 and isinstance(items[0], str):
            # single LABEL like "BAC" -> split into 3 single-letter points
            label = _as_str(items[0])
            if len(label) < 3:
                raise ValueError(f"Angle({label}) label must have >=3 letters (e.g. BAC)")
            # vertex is the middle letter; arms are first and last
            return [label[0], label[1], label[-1]]
        return [_as_str(p) for p in items]

    def angle_val(self, items):
        return _as_float(items[0])

    def angle_rel(self, items):
        pts = items[0]
        val = items[1]
        return ASTRelation(
            "Angle",
            args=[self._point_arg(p) for p in pts],
            attrs={"angle": val},
        )

    def sumdist_rel(self, items):
        pts = items[:3]
        expr = items[3] if len(items) > 3 else ""
        return ASTRelation(
            "SumDist",
            args=[self._point_arg(p) for p in pts],
            attrs={"expr": expr.strip() if isinstance(expr, str) else expr},
        )

    # --- goal ---
    def prove_goal(self, items):
        return ASTGoal("Prove", _as_str(items[0]).strip())

    def solve_goal(self, items):
        return ASTGoal("Solve", _as_str(items[0]).strip())

    def find_goal(self, items):
        return ASTGoal("Find", _as_str(items[0]).strip())

    def expr_text(self, items):
        return _as_str(items[0])


class _Objects:
    __slots__ = ("objs",)

    def __init__(self, objs):
        self.objs = objs


class _Relations:
    __slots__ = ("rels",)

    def __init__(self, rels):
        self.rels = rels


# --------------------------------------------------------------------------- #
# AST -> GeometryGraph (with semantic checks)
# --------------------------------------------------------------------------- #
class _GraphBuilder:
    def __init__(self, ast: ASTProgram):
        self.ast = ast
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self.point_by_label: dict[str, str] = {}        # label -> node id
        self.obj_by_typed_label: dict[tuple[str, str], str] = {}  # (kind,label)->id
        self.obj_by_label: dict[str, list[str]] = {}    # label -> [node ids]

    def build(self) -> GeometryGraph:
        self._build_objects()
        self._build_relations()
        graph = GeometryGraph(nodes=self.nodes, edges=self.edges)
        if self.ast.goal:
            graph.goal = GoalSpec(kind=self.ast.goal.kind, statement=self.ast.goal.statement)
        return graph

    # ----- objects -----
    def _build_objects(self):
        for obj in self.ast.objects:
            nid = _node_id(obj.kind, obj.label)
            if any(n.id == nid for n in self.nodes):
                raise ValueError(f"duplicate object declaration: {obj.kind}({obj.label})")
            node = Node(
                id=nid,
                type=_KIND_TO_NODETYPE[obj.kind],
                label=obj.label,
                attrs=self._object_attrs(obj),
            )
            self.nodes.append(node)
            if obj.kind == "Point":
                if obj.label in self.point_by_label:
                    raise ValueError(f"duplicate point label: {obj.label}")
                self.point_by_label[obj.label] = nid
            else:
                self.obj_by_typed_label[(obj.kind, obj.label)] = nid
                self.obj_by_label.setdefault(obj.label, []).append(nid)

    @staticmethod
    def _object_attrs(obj: ASTObject) -> dict[str, Any]:
        a = dict(obj.attrs)
        if obj.kind == "Point":
            coords = a.get("coords")
            if coords is not None:
                a["coords"] = [float(coords[0]), float(coords[1])]
            a.setdefault("confidence", 1.0)
        elif obj.kind in ("Segment", "Line", "Ray"):
            a.setdefault("confidence", 1.0)
        elif obj.kind == "Circle":
            a["radius"] = float(a["radius"])
            a.setdefault("confidence", 1.0)
        elif obj.kind == "Arc":
            a.setdefault("confidence", 1.0)
        elif obj.kind == "Ellipse":
            c = a["center"]
            a["center"] = [float(c[0]), float(c[1])]
            a["semi_major"] = float(a["semi_major"])
            a["semi_minor"] = float(a["semi_minor"])
            a["rotation"] = float(a["rotation"])
            a.setdefault("confidence", 1.0)
        elif obj.kind in ("Polygon", "Triangle"):
            a.setdefault("confidence", 1.0)
        return a

    # ----- reference resolution -----
    def _resolve_point(self, label: str) -> str:
        nid = self.point_by_label.get(label)
        if nid is None:
            raise ValueError(f"undefined point reference: '{label}'")
        return nid

    def _resolve_obj(self, kind: str | None, label: str) -> str:
        if kind is not None:
            nid = self.obj_by_typed_label.get((kind, label))
            if nid is None:
                if label in self.point_by_label:
                    raise ValueError(
                        f"type mismatch: '{label}' is a Point, not a {kind}")
                raise ValueError(f"undefined object reference: {kind}({label})")
            return nid
        # bare label: search all non-point objects
        cands = self.obj_by_label.get(label, [])
        if not cands:
            if label in self.point_by_label:
                raise ValueError(
                    f"type mismatch: '{label}' is a Point, not an object")
            raise ValueError(f"undefined object reference: '{label}'")
        if len(cands) > 1:
            kinds = [n.type.value for n in self.nodes if n.id in cands]
            raise ValueError(
                f"ambiguous object reference '{label}' matches {kinds}; "
                f"use an explicit ObjCall e.g. Circle({label})"
            )
        return cands[0]

    def _resolve_arg(self, arg: tuple) -> str:
        if arg[0] == "point":
            return self._resolve_point(arg[1])
        return self._resolve_obj(arg[1], arg[2])

    def _node(self, nid: str) -> Node:
        for n in self.nodes:
            if n.id == nid:
                return n
        raise AssertionError(f"node {nid} not found")  # pragma: no cover

    # ----- type checks -----
    @staticmethod
    def _is_point(n: Node) -> bool:
        return n.type == NodeType.POINT

    @staticmethod
    def _is_lineobj(n: Node) -> bool:
        return n.type in (NodeType.LINE, NodeType.SEGMENT, NodeType.RAY)

    @staticmethod
    def _is_curve(n: Node) -> bool:
        return n.type in (NodeType.CIRCLE, NodeType.ARC, NodeType.ELLIPSE)

    @staticmethod
    def _is_circle_like(n: Node) -> bool:
        return n.type in (NodeType.CIRCLE, NodeType.ARC)

    def _expect(self, nid: str, pred, label: str, rel: str, pos: str):
        n = self._node(nid)
        if not pred(n):
            raise ValueError(
                f"type mismatch in {rel}: {pos} argument '{n.label}' "
                f"is {n.type.value}, expected {label}"
            )

    # ----- relations -----
    def _build_relations(self):
        for rel in self.ast.relations:
            self._build_one_relation(rel)

    def _build_one_relation(self, rel: ASTRelation):
        kind = rel.kind
        ids = [self._resolve_arg(a) for a in rel.args]

        if kind == "On":
            self._expect(ids[0], self._is_point, "Point", "On", "1st")
            self._expect(ids[1], self._is_curve, "Curve", "On", "2nd")
            self._add_edge(ids[0], ids[1], RelType.ON)
        elif kind == "Collinear":
            for i, nid in enumerate(ids):
                self._expect(nid, self._is_point, "Point", "Collinear", f"#{i + 1}")
            if len(ids) < 2:
                raise ValueError("Collinear requires at least 2 points")
            self._add_edge(ids[0], ids[1], RelType.COLLINEAR,
                           attrs={"points": list(ids)})
        elif kind == "Intersect":
            self._add_edge(ids[0], ids[1], RelType.INTERSECT)
        elif kind == "Tangent":
            # Tangent(LineObj|Curve, Curve[, at=Point])
            self._expect(ids[0], lambda n: self._is_lineobj(n) or self._is_curve(n),
                         "LineObj|Curve", "Tangent", "1st")
            self._expect(ids[1], self._is_curve, "Curve", "Tangent", "2nd")
            attrs: dict[str, Any] = dict(rel.attrs)
            if "tangent_point" in attrs:
                attrs["tangent_point"] = self._resolve_point(attrs["tangent_point"])
            self._add_edge(ids[0], ids[1], RelType.TANGENT, attrs=attrs)
        elif kind == "Parallel":
            self._expect(ids[0], self._is_lineobj, "LineObj", "Parallel", "1st")
            self._expect(ids[1], self._is_lineobj, "LineObj", "Parallel", "2nd")
            self._add_edge(ids[0], ids[1], RelType.PARALLEL)
        elif kind == "Perpendicular":
            self._expect(ids[0], self._is_lineobj, "LineObj", "Perpendicular", "1st")
            self._expect(ids[1], self._is_lineobj, "LineObj", "Perpendicular", "2nd")
            self._add_edge(ids[0], ids[1], RelType.PERPENDICULAR)
        elif kind == "Equal":
            self._add_edge(ids[0], ids[1], RelType.EQUAL)
        elif kind == "Inside":
            self._expect(ids[0], self._is_point, "Point", "Inside", "1st")
            self._expect(ids[1], lambda n: self._is_curve(n) or n.type == NodeType.POLYGON,
                         "Curve|Polygon", "Inside", "2nd")
            self._add_edge(ids[0], ids[1], RelType.INSIDE)
        elif kind == "Outside":
            self._expect(ids[0], self._is_point, "Point", "Outside", "1st")
            self._expect(ids[1], lambda n: self._is_curve(n) or n.type == NodeType.POLYGON,
                         "Curve|Polygon", "Outside", "2nd")
            self._add_edge(ids[0], ids[1], RelType.OUTSIDE)
        elif kind == "Concentric":
            self._expect(ids[0], self._is_circle_like, "Circle|Arc", "Concentric", "1st")
            self._expect(ids[1], self._is_circle_like, "Circle|Arc", "Concentric", "2nd")
            self._add_edge(ids[0], ids[1], RelType.CONCENTRIC)
        elif kind == "Inscribed":
            self._add_edge(ids[0], ids[1], RelType.INSCRIBED)
        elif kind == "Circumscribed":
            self._add_edge(ids[0], ids[1], RelType.CIRCUMSCRIBED)
        elif kind == "Similar":
            self._add_edge(ids[0], ids[1], RelType.SIMILAR)
        elif kind == "Congruent":
            self._add_edge(ids[0], ids[1], RelType.CONGRUENT)
        elif kind == "Center":
            self._expect(ids[0], self._is_point, "Point", "Center", "1st")
            self._expect(ids[1], lambda n: self._is_curve(n) or self._is_circle_like(n),
                         "Curve", "Center", "2nd")
            self._add_edge(ids[0], ids[1], RelType.CENTER)
        elif kind == "TangentPoint":
            self._expect(ids[0], self._is_point, "Point", "TangentPoint", "1st")
            self._expect(ids[1], self._is_curve, "Curve", "TangentPoint", "2nd")
            self._add_edge(ids[0], ids[1], RelType.TANGENT_POINT)
        elif kind == "Angle":
            for i, nid in enumerate(ids):
                self._expect(nid, self._is_point, "Point", "Angle", f"#{i + 1}")
            if len(ids) != 3:
                raise ValueError(f"Angle requires 3 points, got {len(ids)}")
            self._add_edge(ids[1], ids[0], RelType.EQUAL, attrs={
                "dsl_kind": "Angle",
                "points": list(ids),
                "angle": float(rel.attrs.get("angle", 0.0)),
            })
        elif kind == "SumDist":
            for i, nid in enumerate(ids):
                self._expect(nid, self._is_point, "Point", "SumDist", f"#{i + 1}")
            self._add_edge(ids[0], ids[1], RelType.EQUAL, attrs={
                "dsl_kind": "SumDist",
                "points": list(ids),
                "expr": str(rel.attrs.get("expr", "")),
            })
        else:  # pragma: no cover
            raise ValueError(f"unsupported relation kind: {kind}")

    def _add_edge(self, src: str, dst: str, rel: RelType,
                  attrs: dict[str, Any] | None = None,
                  verified: VerifyState = VerifyState.TRUE):
        self.edges.append(Edge(
            src=src, dst=dst, rel=rel, verified=verified,
            confidence=1.0, attrs=attrs or {},
        ))


# --------------------------------------------------------------------------- #
# Uncertain-comment extraction
# --------------------------------------------------------------------------- #
_UNCERTAIN_RE = re.compile(r"^\s*#\s*uncertain\s*:\s*(.+?)\s*$", re.IGNORECASE)


def _split_uncertain(text: str) -> tuple[str, list[str]]:
    """Pull ``# uncertain: <rel>`` lines out of the text, returning the
    cleaned text and the list of relation-expression strings."""
    kept: list[str] = []
    uncertain: list[str] = []
    for line in text.splitlines():
        m = _UNCERTAIN_RE.match(line)
        if m:
            uncertain.append(m.group(1).strip())
        else:
            kept.append(line)
    return "\n".join(kept), uncertain


def _parse_relation_expr(rel_text: str) -> ASTRelation:
    """Parse a single relation expression by wrapping it in a Relations section."""
    wrapped = f"Relations:\n  - {rel_text}"
    prog = _ASTBuilder().transform(_parser().parse(wrapped))
    if not prog.relations:
        raise ValueError(f"failed to parse uncertain relation: {rel_text}")
    return prog.relations[0]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def parse(text: str) -> ASTProgram:
    """Parse DSL text into an :class:`ASTProgram` (no semantic checks)."""
    try:
        tree = _parser().parse(text)
    except UnexpectedInput as exc:
        raise ValueError(f"DSL syntax error: {exc}") from exc
    return _ASTBuilder().transform(tree)


def from_dsl(text: str) -> GeometryGraph:
    """Parse DSL text into a :class:`GeometryGraph` with semantic checks.

    Raises ``ValueError`` on syntax errors, undefined references, or type
    mismatches.
    """
    cleaned, uncertain_texts = _split_uncertain(text)
    ast = parse(cleaned)
    for utext in uncertain_texts:
        ast.relations.append(_parse_relation_expr(utext))

    builder = _GraphBuilder(ast)
    graph = builder.build()

    # mark uncertain relations
    n_uncertain = len(uncertain_texts)
    if n_uncertain:
        for edge in graph.edges[-n_uncertain:]:
            edge.verified = VerifyState.UNCERTAIN
    return graph
