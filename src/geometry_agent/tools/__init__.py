"""Safe code execution + geometry machine-proof tooling (design/08).

This package provides:

* ``CodeExecutor`` — sandboxed Python execution with a whitelisted namespace
  (math / numpy / sympy / fractions / decimal / statistics), builtins
  whitelist, stdout capture, and ``signal.alarm``-based timeout.
* Geometry prover hooks — ``complex_method`` / ``coordinate_method`` /
  ``projective_method`` — used as ADVANCED-priority tools by the reasoning
  agent.
* ``registry`` — OpenAI function-calling schema list and a name->callable
  dispatcher map that merges the existing verify/solve/search tools with the
  new code-execution and geometry-prover tools.
* ``templates`` — code snippet templates the LLM can reuse.
"""

from __future__ import annotations

from geometry_agent.tools.code_executor import CodeExecutor
from geometry_agent.tools.geometry_prover import (
    complex_method,
    coordinate_method,
    projective_method,
)
from geometry_agent.tools.registry import get_tool_dispatchers, get_tool_schemas
from geometry_agent.tools.templates import get_template

__all__ = [
    "CodeExecutor",
    "complex_method",
    "coordinate_method",
    "projective_method",
    "get_tool_schemas",
    "get_tool_dispatchers",
    "get_template",
]
