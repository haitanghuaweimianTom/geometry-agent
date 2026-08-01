"""Core data contracts (Pydantic schemas) shared across all modules.

This module is the single source of truth for data shapes flowing through the
pipeline: PrimitiveSet -> GeometryGraph -> RelationCandidate -> VerifyResult ->
ProofPlan -> Solution. All modules MUST import from here to guarantee interface
compatibility (see design/03-Geometry-Graph.md, design/00-Overview.md §2.5).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# =====================================================================================
# Geometry primitives (perception layer output)
# =====================================================================================

class PointSource(str, Enum):
    CORNER = "corner"
    ENDPOINT = "endpoint"
    INTERSECTION = "intersection"
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class Point(BaseModel):
    id: str
    label: Optional[str] = None
    coords: tuple[float, float]
    confidence: float = 1.0
    source: PointSource = PointSource.CORNER
    subpixel: bool = True


class LineType(str, Enum):
    LINE = "line"
    SEGMENT = "segment"
    RAY = "ray"


class LineEquation(BaseModel):
    """Line in the form a*x + b*y + c = 0, with a^2 + b^2 = 1."""
    a: float
    b: float
    c: float


class Line(BaseModel):
    id: str
    type: LineType = LineType.SEGMENT
    label: Optional[str] = None
    endpoints: Optional[list[tuple[float, float]]] = None  # None for infinite lines
    equation: Optional[LineEquation] = None
    length: Optional[float] = None
    confidence: float = 1.0


class Circle(BaseModel):
    id: str
    label: Optional[str] = None
    center: tuple[float, float]
    radius: float
    fit_residual: float = 0.0
    coverage: float = 1.0  # 1.0 = full circle, <1.0 = arc
    arc_range: Optional[list[float]] = None  # [start_angle, end_angle] in radians
    confidence: float = 1.0


class Ellipse(BaseModel):
    id: str
    label: Optional[str] = None
    center: tuple[float, float]
    semi_major: float
    semi_minor: float
    rotation: float  # radians, major axis angle vs x-axis
    foci: list[tuple[float, float]] = Field(default_factory=list)
    eccentricity: float = 0.0
    fit_residual: float = 0.0
    confidence: float = 1.0


class Polygon(BaseModel):
    id: str
    label: Optional[str] = None
    vertices: list[tuple[float, float]]
    poly_type: Optional[str] = None  # triangle / quadrilateral / ...
    confidence: float = 1.0


class MarkType(str, Enum):
    RIGHT_ANGLE = "right_angle"
    EQUAL = "equal"
    PARALLEL = "parallel"
    ANGLE = "angle"


class Mark(BaseModel):
    id: str
    type: MarkType
    vertex: Optional[str] = None  # node id this mark attaches to
    related: list[str] = Field(default_factory=list)  # related node ids
    angle_value: Optional[float] = None  # degrees, for ANGLE marks with a number
    count: Optional[int] = None  # tick count for EQUAL marks
    confidence: float = 1.0


class MetaData(BaseModel):
    image_size: tuple[int, int] = (0, 0)
    deskew_angle: float = 0.0
    scale_px_per_cm: float = 12.0
    warnings: list[str] = Field(default_factory=list)


class PrimitiveSet(BaseModel):
    """Output of GeometryParser, input to GraphBuilder."""
    points: list[Point] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)
    circles: list[Circle] = Field(default_factory=list)
    ellipses: list[Ellipse] = Field(default_factory=list)
    polygons: list[Polygon] = Field(default_factory=list)
    marks: list[Mark] = Field(default_factory=list)
    metadata: MetaData = Field(default_factory=MetaData)


# =====================================================================================
# Geometry Graph (structuring layer)
# =====================================================================================

class NodeType(str, Enum):
    POINT = "Point"
    LINE = "Line"
    SEGMENT = "Segment"
    RAY = "Ray"
    CIRCLE = "Circle"
    ARC = "Arc"
    ELLIPSE = "Ellipse"
    POLYGON = "Polygon"


class RelType(str, Enum):
    ON = "On"
    CENTER = "Center"
    COLLINEAR = "Collinear"
    INTERSECT = "Intersect"
    TANGENT = "Tangent"
    PARALLEL = "Parallel"
    PERPENDICULAR = "Perpendicular"
    EQUAL = "Equal"
    INSIDE = "Inside"
    OUTSIDE = "Outside"
    CONCENTRIC = "Concentric"
    TANGENT_POINT = "TangentPoint"
    INSCRIBED = "Inscribed"
    CIRCUMSCRIBED = "Circumscribed"
    SAME_ARC = "SameArc"
    SIMILAR = "Similar"
    CONGRUENT = "Congruent"


class VerifyState(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNCERTAIN = "uncertain"
    PENDING = "pending"


class Node(BaseModel):
    id: str
    type: NodeType
    label: Optional[str] = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    src: str
    dst: str
    rel: RelType
    confidence: float = 1.0
    verified: VerifyState = VerifyState.PENDING
    evidence: Optional[str] = None
    source: str = "detected"  # detected / mark / derived / hypothesis
    attrs: dict[str, Any] = Field(default_factory=dict)


class GraphMetaData(BaseModel):
    image_size: tuple[int, int] = (0, 0)
    scale_px_per_cm: float = 12.0
    version: str = "1.0"


class GoalSpec(BaseModel):
    kind: Literal["Prove", "Solve", "Find"] = "Prove"
    statement: str = ""


class GeometryGraph(BaseModel):
    """Central data structure: Geometry World Model."""
    graph_version: str = "1.0"
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    metadata: GraphMetaData = Field(default_factory=GraphMetaData)
    goal: Optional[GoalSpec] = None


# =====================================================================================
# Relation extraction candidates (structurer -> verifier)
# =====================================================================================

class RelationCandidate(BaseModel):
    src: str
    dst: str
    rel: RelType
    evidence: str = ""
    confidence: float = 1.0
    attrs: dict[str, Any] = Field(default_factory=dict)
    agent: str = ""  # which agent proposed it


# =====================================================================================
# Verification result
# =====================================================================================

class VerifyResult(BaseModel):
    verified: VerifyState
    evidence: str = ""
    measured: dict[str, float] = Field(default_factory=dict)
    attrs: dict[str, Any] = Field(default_factory=dict)


# =====================================================================================
# Reasoning / solving layer
# =====================================================================================

class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Optional[Any] = None


class ProofStep(BaseModel):
    step: int
    statement: str
    reason: str = ""
    verified: bool = False
    tool_call: Optional[ToolCall] = None


class ProofPlan(BaseModel):
    """LLM Reasoning Agent output."""
    plan: list[ProofStep] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    goal: Optional[GoalSpec] = None
    reasoning_trace: list[str] = Field(default_factory=list)
    summary: str = ""  # LLM-decided 解题思路 (Chinese, written by the model itself)
    key_equations: list[str] = Field(default_factory=list)  # LLM-decided 关键算式


class Solution(BaseModel):
    """Final output of the pipeline."""
    answer: str = ""
    proof: list[ProofStep] = Field(default_factory=list)
    confidence: float = 0.0
    verified: bool = False
    geometry_graph: Optional[GeometryGraph] = None
    verification_log: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_path: str = ""
    reflection_count: int = 0
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning_trace: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""  # LLM-decided 解题思路 for the PDF appendix
    key_equations: list[str] = Field(default_factory=list)  # LLM-decided 关键算式


class Theorem(BaseModel):
    """A geometry theorem in the database (see design/08 §3)."""
    id: str
    name: str
    premise: list[str] = Field(default_factory=list)
    conclusion: str = ""
    condition: str = ""
    category: str = ""
    reference: str = ""


# =====================================================================================
# Pipeline request / response
# =====================================================================================

class GradeLevel(str, Enum):
    """Student grade level: controls knowledge scope and prompt guidance.

    学科-学段兼容矩阵:
      - 平面几何:    初中 / 高中 / 竞赛
      - 解析几何:         高中 / 竞赛  (初中无圆锥曲线)
      - 立体几何:         高中          (仅高中)
      - 函数导数:         高中 / 竞赛
    工具集不变, 只是知识检索范围与提示词不同.
    """
    JUNIOR = "junior"            # 初中: 仅用初中课内方法
    SENIOR = "senior"            # 高中: 高中课内方法 + 向量法/坐标法
    COMPETITION = "competition"  # 竞赛: 课内 + 高等几何 + 竞赛方法


class SolveRequest(BaseModel):
    image_path: str = ""
    problem_text: str
    grade: GradeLevel = GradeLevel.SENIOR  # junior / senior / competition
    metadata: dict[str, Any] = Field(default_factory=dict)


class SolveResponse(BaseModel):
    answer: str
    confidence: float
    proof: list[ProofStep]
    verified: bool
    verification_log: list[dict[str, Any]] = Field(default_factory=list)


# =====================================================================================
# Human-in-the-loop review / correction
# =====================================================================================

class CorrectionType(str, Enum):
    NATURAL_LANGUAGE = "natural_language"  # free text, LLM parses
    DSL_EDIT = "dsl_edit"                   # structured add/remove of objects/relations
    SKIP = "skip"                           # user approved, no changes


class Correction(BaseModel):
    """A single user correction to the parsed geometry."""
    kind: CorrectionType
    text: str = ""                       # natural language description or DSL snippet
    actions: list[dict[str, Any]] = Field(default_factory=list)  # parsed actions


class ReviewResult(BaseModel):
    """Outcome of the human review checkpoint."""
    approved: bool                       # user approved the parsed geometry
    corrections: list[Correction] = Field(default_factory=list)
    corrected_graph: Optional[GeometryGraph] = None
    pdf_path: Optional[str] = None
    rounds: int = 0


# =====================================================================================
# Knowledge base (local curated + on-demand web retrieval)
# =====================================================================================

class SubjectType(str, Enum):
    PLANE_GEOMETRY = "plane_geometry"              # 平面几何
    TRIANGLE_SOLVING = "triangle_solving"          # 解三角形
    ANALYTIC_GEOMETRY = "analytic_geometry"        # 解析几何 (含圆锥曲线)
    SOLID_GEOMETRY = "solid_geometry"              # 立体几何
    FUNCTION_DERIVATIVE = "function_derivative"    # 函数与导数


class MethodPriority(int, Enum):
    IN_CLASS = 1       # 初高中课内方法 (最优先)
    ADVANCED = 2       # 高等几何: 射影/仿射/复数法等
    MACHINE = 3        # 几何机器证明/符号机器求解


class KnowledgeEntry(BaseModel):
    """A knowledge point / theorem / method in the local curated KB."""
    id: str
    subject: SubjectType
    title: str
    content: str                         # markdown body
    method_priority: MethodPriority = MethodPriority.IN_CLASS
    tags: list[str] = Field(default_factory=list)
    applies_to: list[str] = Field(default_factory=list)  # problem patterns
    source: str = "curated"              # curated / web
    grade: GradeLevel = GradeLevel.SENIOR  # junior / senior / both


class MethodEntry(BaseModel):
    """A problem-solving method with priority and applicability."""
    id: str
    subject: SubjectType
    name: str
    priority: MethodPriority
    description: str
    steps: list[str] = Field(default_factory=list)
    applicable_when: list[str] = Field(default_factory=list)
    example: str = ""
    grade: GradeLevel = GradeLevel.SENIOR  # junior / senior


class RetrievedKnowledge(BaseModel):
    """Knowledge retrieved for a specific problem."""
    topic: SubjectType
    entries: list[KnowledgeEntry] = Field(default_factory=list)
    methods: list[MethodEntry] = Field(default_factory=list)
    from_web: bool = False


# =====================================================================================
# Code execution tool
# =====================================================================================

class CodeResult(BaseModel):
    """Result of executing a Python code snippet for computation."""
    success: bool
    output: str = ""
    error: str = ""
    value: Optional[Any] = None          # the final computed value if any
    code: str = ""
