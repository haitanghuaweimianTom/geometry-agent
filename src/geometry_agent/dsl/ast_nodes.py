"""Intermediate AST for the Geometry DSL (design/06 §7).

The lark parser produces a concrete tree; a Transformer converts it into the
dataclasses defined here. A second pass (in parser.py) turns the AST into a
``GeometryGraph`` while performing semantic checks (reference integrity, type
consistency).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# A reference argument carried by relations. Either a point label or a typed
# object label ("Segment", "AB"). Kept as plain tuples so the AST is easy to
# build from a lark Transformer.
PointArg = tuple[Literal["point"], str]
ObjArg = tuple[Literal["obj"], str, str]  # ("obj", type_keyword, label)
Arg = PointArg | ObjArg


@dataclass
class ASTObject:
    """An object declaration, e.g. ``Point(A): [180.0, 84.5]``."""

    kind: str  # Point / Segment / Line / Ray / Circle / Arc / Ellipse / Polygon / Triangle
    label: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class ASTRelation:
    """A relation declaration, e.g. ``Tangent(Segment(AB), Circle(O), at=A)``."""

    kind: str  # On / Tangent / Perpendicular / Angle / ...
    args: list[Arg] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class ASTGoal:
    kind: str  # Prove / Solve / Find
    statement: str


@dataclass
class ASTProgram:
    objects: list[ASTObject] = field(default_factory=list)
    relations: list[ASTRelation] = field(default_factory=list)
    goal: ASTGoal | None = None
