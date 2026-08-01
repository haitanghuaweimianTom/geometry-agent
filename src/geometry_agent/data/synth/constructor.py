"""GeometryConstructor: builds PrimitiveSet + GT GeometryGraph from a spec.

Given a :class:`ConstructSpec` (raw geometry description produced by a template),
the constructor:

1. Builds a :class:`PrimitiveSet` with proper IDs / labels.
2. Builds the node set of a :class:`GeometryGraph`.
3. **Auto-derives every relation** via analytic geometry (point-on-line,
   point-on-circle, tangent, perpendicular, parallel, center, intersect,
   collinear, inscribed, ...). All derived edges are ``verified=true`` -- this
   is the ground truth (design/09 §4.4).
4. Serializes a DSL view via the existing ``to_dsl`` serializer.

Tolerance is tight (1e-6) because relationships are constructed analytically --
any drift indicates a bug in the template, not measurement noise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ...dsl.serializer import to_dsl
from ...graph.builder import GraphBuilder
from ...types import (
    Circle,
    Edge,
    Ellipse,
    GeometryGraph,
    Line,
    LineEquation,
    LineType,
    MetaData,
    Point,
    PointSource,
    Polygon,
    PrimitiveSet,
    RelType,
    VerifyState,
)

TOL = 1e-6


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class _PtSpec:
    id: str
    label: str
    coords: tuple[float, float]


@dataclass
class _SegSpec:
    id: str
    label: str
    p1: str  # point id
    p2: str
    kind: str = "segment"  # segment | line | ray


@dataclass
class _CircSpec:
    id: str
    label: str
    center_id: str
    radius: float


@dataclass
class _EllSpec:
    id: str
    label: str
    center_id: str
    semi_major: float
    semi_minor: float
    rotation: float
    foci_ids: list[str] = field(default_factory=list)


@dataclass
class _PolySpec:
    id: str
    label: str
    vertex_ids: list[str]
    poly_type: str = "triangle"


@dataclass
class ConstructSpec:
    """Raw geometry description produced by a template, consumed by the constructor."""

    template_name: str
    answer: str
    points: list[_PtSpec]
    segments: list[_SegSpec] = field(default_factory=list)
    circles: list[_CircSpec] = field(default_factory=list)
    ellipses: list[_EllSpec] = field(default_factory=list)
    polygons: list[_PolySpec] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    image_size: tuple[int, int] = (400, 320)
    problem_text: str = ""


@dataclass
class ConstructedScene:
    """Output of :meth:`GeometryConstructor.construct`.

    The ``graph`` field is the ground-truth GeometryGraph: every edge has
    ``verified=true``.
    """

    template_name: str
    primitives: PrimitiveSet
    graph: GeometryGraph
    dsl: str
    answer: str
    params: dict[str, Any] = field(default_factory=dict)
    problem_text: str = ""


# --------------------------------------------------------------------------- #
# Analytic helpers
# --------------------------------------------------------------------------- #
def _dist(p: tuple[float, float], q: tuple[float, float]) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _line_eq(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float, float]:
    """Normalized line equation a*x + b*y + c = 0 with a^2 + b^2 = 1."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    n = math.hypot(dx, dy)
    if n < 1e-12:
        return 1.0, 0.0, -p1[0]
    a = dy / n
    b = -dx / n
    c = -(a * p1[0] + b * p1[1])
    return a, b, c


def _point_on_segment(p: tuple[float, float], e1: tuple[float, float], e2: tuple[float, float]) -> bool:
    return abs(_dist(p, e1) + _dist(p, e2) - _dist(e1, e2)) <= TOL


def _point_on_line(p: tuple[float, float], a: float, b: float, c: float) -> bool:
    return abs(a * p[0] + b * p[1] + c) <= TOL


def _point_on_circle(p: tuple[float, float], center: tuple[float, float], radius: float) -> bool:
    return abs(_dist(p, center) - radius) <= TOL


def _point_on_ellipse(p: tuple[float, float], center: tuple[float, float],
                      a: float, b: float, rotation: float) -> bool:
    dx = p[0] - center[0]
    dy = p[1] - center[1]
    cr, sr = math.cos(rotation), math.sin(rotation)
    xp = dx * cr + dy * sr
    yp = -dx * sr + dy * cr
    if a <= 0 or b <= 0:
        return False
    return abs((xp * xp) / (a * a) + (yp * yp) / (b * b) - 1.0) <= TOL


def _point_inside_ellipse(p: tuple[float, float], center: tuple[float, float],
                          a: float, b: float, rotation: float) -> bool:
    dx = p[0] - center[0]
    dy = p[1] - center[1]
    cr, sr = math.cos(rotation), math.sin(rotation)
    xp = dx * cr + dy * sr
    yp = -dx * sr + dy * cr
    if a <= 0 or b <= 0:
        return False
    return (xp * xp) / (a * a) + (yp * yp) / (b * b) < 1.0 - TOL


def _foot_of_perpendicular(center: tuple[float, float], a: float, b: float, c: float) -> tuple[float, float]:
    # a^2 + b^2 = 1
    t = a * center[0] + b * center[1] + c
    return center[0] - a * t, center[1] - b * t


# --------------------------------------------------------------------------- #
# Constructor
# --------------------------------------------------------------------------- #
class GeometryConstructor:
    """Builds a :class:`ConstructedScene` (primitives + GT graph + DSL) from a spec."""

    def __init__(self, image_size: tuple[int, int] = (400, 320), tol: float = TOL):
        self.image_size = image_size
        self.tol = tol

    # ----- public API ----- #
    def construct(self, spec: ConstructSpec) -> ConstructedScene:
        primitives = self._build_primitives(spec)
        graph = GraphBuilder().build(primitives)
        self._annotate_segment_attrs(spec, graph)
        edges = self._derive_edges(spec, graph)
        graph.edges = edges
        dsl = to_dsl(graph)
        return ConstructedScene(
            template_name=spec.template_name,
            primitives=primitives,
            graph=graph,
            dsl=dsl,
            answer=spec.answer,
            params=dict(spec.params),
            problem_text=spec.problem_text,
        )

    # ----- primitives ----- #
    def _build_primitives(self, spec: ConstructSpec) -> PrimitiveSet:
        pts: list[Point] = []
        coord_by_id: dict[str, tuple[float, float]] = {}
        label_by_id: dict[str, str] = {}
        for p in spec.points:
            pts.append(
                Point(
                    id=p.id,
                    label=p.label,
                    coords=(float(p.coords[0]), float(p.coords[1])),
                    source=PointSource.EXPLICIT,
                )
            )
            coord_by_id[p.id] = (float(p.coords[0]), float(p.coords[1]))
            label_by_id[p.id] = p.label

        lines: list[Line] = []
        for s in spec.segments:
            p1 = coord_by_id[s.p1]
            p2 = coord_by_id[s.p2]
            a, b, c = _line_eq(p1, p2)
            length = _dist(p1, p2)
            ltype = {"segment": LineType.SEGMENT, "line": LineType.LINE, "ray": LineType.RAY}[s.kind]
            lines.append(
                Line(
                    id=s.id,
                    type=ltype,
                    label=s.label,
                    endpoints=[(p1[0], p1[1]), (p2[0], p2[1])],
                    equation=LineEquation(a=a, b=b, c=c),
                    length=length,
                )
            )

        circles: list[Circle] = []
        for c in spec.circles:
            center = coord_by_id[c.center_id]
            circles.append(
                Circle(
                    id=c.id,
                    label=c.label,
                    center=(center[0], center[1]),
                    radius=float(c.radius),
                )
            )

        ellipses: list[Ellipse] = []
        for e in spec.ellipses:
            center = coord_by_id[e.center_id]
            a, b = float(e.semi_major), float(e.semi_minor)
            c_focal = math.sqrt(max(0.0, a * a - b * b))
            if e.foci_ids:
                foci = [coord_by_id[fid] for fid in e.foci_ids]
            else:
                dx = math.cos(e.rotation) * c_focal
                dy = math.sin(e.rotation) * c_focal
                foci = [(center[0] + dx, center[1] + dy), (center[0] - dx, center[1] - dy)]
            ecc = c_focal / a if a > 0 else 0.0
            ellipses.append(
                Ellipse(
                    id=e.id,
                    label=e.label,
                    center=(center[0], center[1]),
                    semi_major=a,
                    semi_minor=b,
                    rotation=float(e.rotation),
                    foci=foci,
                    eccentricity=ecc,
                )
            )

        polygons: list[Polygon] = []
        for poly in spec.polygons:
            verts = [coord_by_id[vid] for vid in poly.vertex_ids]
            polygons.append(
                Polygon(
                    id=poly.id,
                    label=poly.label,
                    vertices=[(v[0], v[1]) for v in verts],
                    poly_type=poly.poly_type,
                )
            )

        meta = MetaData(image_size=spec.image_size, scale_px_per_cm=12.0)
        return PrimitiveSet(points=pts, lines=lines, circles=circles, ellipses=ellipses,
                            polygons=polygons, metadata=meta)

    # ----- segment node attrs (p1/p2 labels for DSL serializer) ----- #
    def _annotate_segment_attrs(self, spec: ConstructSpec, graph: GeometryGraph) -> None:
        label_by_id = {p.id: p.label for p in spec.points}
        seg_by_id = {s.id: s for s in spec.segments}
        poly_by_id = {p.id: p for p in spec.polygons}
        for node in graph.nodes:
            if node.id in seg_by_id:
                s = seg_by_id[node.id]
                node.attrs["p1"] = label_by_id.get(s.p1, s.p1)
                node.attrs["p2"] = label_by_id.get(s.p2, s.p2)
            elif node.id in poly_by_id:
                poly = poly_by_id[node.id]
                node.attrs["vertices_labels"] = [label_by_id.get(v, v) for v in poly.vertex_ids]
                node.attrs["dsl_kind"] = "Triangle" if poly.poly_type == "triangle" else "Polygon"

    # ----- edge derivation ----- #
    def _derive_edges(self, spec: ConstructSpec, graph: GeometryGraph) -> list[Edge]:
        edges: list[Edge] = []
        coord_by_id = {p.id: (float(p.coords[0]), float(p.coords[1])) for p in spec.points}
        label_by_id = {p.id: p.label for p in spec.points}

        seg_specs = {s.id: s for s in spec.segments}
        circ_specs = {c.id: c for c in spec.circles}
        ell_specs = {e.id: e for e in spec.ellipses}
        poly_specs = {p.id: p for p in spec.polygons}

        # symmetric relations: (src, dst) and (dst, src) treated as same edge
        symmetric_rels = {
            RelType.PARALLEL, RelType.PERPENDICULAR, RelType.INTERSECT,
            RelType.CONCENTRIC, RelType.TANGENT, RelType.COLLINEAR,
            RelType.EQUAL, RelType.SIMILAR, RelType.CONGRUENT,
        }
        seen: set[tuple[str, str, RelType]] = set()

        def add(src: str, dst: str, rel: RelType, **attrs: Any) -> None:
            if rel in symmetric_rels:
                key = (min(src, dst), max(src, dst), rel)
            else:
                key = (src, dst, rel)
            if key in seen:
                # merge attrs into the existing edge if any new attr provided
                if attrs:
                    for e in edges:
                        ekey = (min(e.src, e.dst), max(e.src, e.dst), e.rel) \
                            if e.rel in symmetric_rels else (e.src, e.dst, e.rel)
                        if ekey == key:
                            for k, v in attrs.items():
                                e.attrs.setdefault(k, v)
                            break
                return
            seen.add(key)
            edges.append(
                Edge(
                    src=src,
                    dst=dst,
                    rel=rel,
                    confidence=1.0,
                    verified=VerifyState.TRUE,
                    source="derived",
                    attrs=dict(attrs),
                )
            )

        # --- point-on-* relations ---------------------------------------- #
        for p in spec.points:
            pc = coord_by_id[p.id]
            # segments / lines
            for s in spec.segments:
                e1 = coord_by_id[s.p1]
                e2 = coord_by_id[s.p2]
                onGeom = _point_on_line(pc, *_line_eq(e1, e2))
                if not onGeom:
                    continue
                if s.kind == "segment":
                    if _point_on_segment(pc, e1, e2):
                        add(p.id, s.id, RelType.ON)
                else:
                    add(p.id, s.id, RelType.ON)
            # circles
            for c in spec.circles:
                center = coord_by_id[c.center_id]
                if _point_on_circle(pc, center, c.radius):
                    add(p.id, c.id, RelType.ON)
            # ellipses
            for e in spec.ellipses:
                center = coord_by_id[e.center_id]
                if _point_on_ellipse(pc, center, e.semi_major, e.semi_minor, e.rotation):
                    add(p.id, e.id, RelType.ON)
                elif _point_inside_ellipse(pc, center, e.semi_major, e.semi_minor, e.rotation):
                    add(p.id, e.id, RelType.INSIDE)
                else:
                    add(p.id, e.id, RelType.OUTSIDE)

        # --- center relations -------------------------------------------- #
        for c in spec.circles:
            add(c.center_id, c.id, RelType.CENTER)
        for e in spec.ellipses:
            add(e.center_id, e.id, RelType.CENTER)

        # --- tangent (line <-> circle) + perpendicular (radius vs tangent) #
        for s in spec.segments:
            e1 = coord_by_id[s.p1]
            e2 = coord_by_id[s.p2]
            a, b, c_eq = _line_eq(e1, e2)
            for circ in spec.circles:
                center = coord_by_id[circ.center_id]
                d = abs(a * center[0] + b * center[1] + c_eq)
                if abs(d - circ.radius) > self.tol:
                    continue
                # tangent; locate tangent point node
                foot = _foot_of_perpendicular(center, a, b, c_eq)
                tpid = self._find_point_id(spec, foot)
                attrs: dict[str, Any] = {}
                if tpid is not None:
                    attrs["tangent_point"] = tpid
                    add(tpid, circ.id, RelType.TANGENT_POINT)
                    # perpendicular: radius segment (center <-> tangent point) vs this line
                    rad_seg = self._find_segment(spec, circ.center_id, tpid)
                    if rad_seg is not None:
                        add(rad_seg, s.id, RelType.PERPENDICULAR)
                add(s.id, circ.id, RelType.TANGENT, **attrs)

        # --- parallel / perpendicular between segments ------------------- #
        for i in range(len(spec.segments)):
            for j in range(i + 1, len(spec.segments)):
                s1 = spec.segments[i]
                s2 = spec.segments[j]
                d1 = (coord_by_id[s1.p2][0] - coord_by_id[s1.p1][0],
                      coord_by_id[s1.p2][1] - coord_by_id[s1.p1][1])
                d2 = (coord_by_id[s2.p2][0] - coord_by_id[s2.p1][0],
                      coord_by_id[s2.p2][1] - coord_by_id[s2.p1][1])
                cross = d1[0] * d2[1] - d1[1] * d2[0]
                dot = d1[0] * d2[0] + d1[1] * d2[1]
                n1 = math.hypot(*d1)
                n2 = math.hypot(*d2)
                if n1 < self.tol or n2 < self.tol:
                    continue
                if abs(cross) / (n1 * n2) <= self.tol * 1e3:
                    add(s1.id, s2.id, RelType.PARALLEL)
                elif abs(dot) / (n1 * n2) <= self.tol * 1e3:
                    add(s1.id, s2.id, RelType.PERPENDICULAR)

        # --- circle-circle relations ------------------------------------- #
        for i in range(len(spec.circles)):
            for j in range(i + 1, len(spec.circles)):
                c1 = spec.circles[i]
                c2 = spec.circles[j]
                o1 = coord_by_id[c1.center_id]
                o2 = coord_by_id[c2.center_id]
                d = _dist(o1, o2)
                r1, r2 = c1.radius, c2.radius
                if abs(d - (r1 + r2)) <= self.tol:
                    add(c1.id, c2.id, RelType.TANGENT)
                elif abs(d - abs(r1 - r2)) <= self.tol:
                    add(c1.id, c2.id, RelType.TANGENT)
                elif abs(r1 - r2) - self.tol < d < r1 + r2 - self.tol:
                    add(c1.id, c2.id, RelType.INTERSECT)
                # concentric?
                if d <= self.tol:
                    add(c1.id, c2.id, RelType.CONCENTRIC)

        # --- collinear points (3+) -- one edge per maximal group --------- #
        pt_ids = [p.id for p in spec.points]
        collinear_groups: set[frozenset[str]] = set()
        for i in range(len(pt_ids)):
            for j in range(i + 1, len(pt_ids)):
                pa = coord_by_id[pt_ids[i]]
                pb = coord_by_id[pt_ids[j]]
                a, b, c_eq = _line_eq(pa, pb)
                group = {pt_ids[i], pt_ids[j]}
                for k in range(len(pt_ids)):
                    if k in (i, j):
                        continue
                    pk = coord_by_id[pt_ids[k]]
                    if _point_on_line(pk, a, b, c_eq):
                        group.add(pt_ids[k])
                if len(group) >= 3:
                    collinear_groups.add(frozenset(group))
        for grp in collinear_groups:
            ordered = sorted(grp)
            add(ordered[0], ordered[1], RelType.COLLINEAR, points=ordered)

        # --- polygon inscribed in circle --------------------------------- #
        for poly in spec.polygons:
            vert_coords = [coord_by_id[vid] for vid in poly.vertex_ids]
            for circ in spec.circles:
                center = coord_by_id[circ.center_id]
                if all(_point_on_circle(vc, center, circ.radius) for vc in vert_coords):
                    add(poly.id, circ.id, RelType.INSCRIBED)

        return edges

    # ----- small lookups ----- #
    def _find_point_id(self, spec: ConstructSpec, coords: tuple[float, float]) -> str | None:
        for p in spec.points:
            if _dist((p.coords[0], p.coords[1]), coords) <= self.tol * 1e3:
                return p.id
        return None

    def _find_segment(self, spec: ConstructSpec, pid_a: str, pid_b: str) -> str | None:
        for s in spec.segments:
            if {s.p1, s.p2} == {pid_a, pid_b}:
                return s.id
        return None


# --------------------------------------------------------------------------- #
# Top-level convenience
# --------------------------------------------------------------------------- #
def construct_scene(template: "TemplateBase", params: dict[str, Any]) -> ConstructedScene:
    """Construct a scene by delegating to ``template.construct(params)``.

    ``template`` must expose ``construct(params) -> ConstructedScene`` (see
    :mod:`geometry_agent.data.synth.templates`).
    """
    return template.construct(params)


# Avoid circular import at module load: TemplateBase is in templates.py
from .templates import TemplateBase  # noqa: E402  (placed last on purpose)
