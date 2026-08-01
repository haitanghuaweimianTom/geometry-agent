"""Geometry DSL package (design/06).

Public API:
    from_dsl(text)   -> GeometryGraph
    to_dsl(graph, config=None) -> str
"""

from __future__ import annotations

from ..config import DSLConfig
from ..types import GeometryGraph
from .parser import from_dsl, parse
from .serializer import to_dsl

__all__ = ["from_dsl", "to_dsl", "parse", "DSLConfig", "GeometryGraph"]
