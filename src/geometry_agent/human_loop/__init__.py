"""Human-in-the-loop LaTeX preview & correction module (design/03 §6).

Renders a GeometryGraph to a Chinese-language LaTeX PDF for user review,
parses user corrections (natural language or DSL), applies them to the graph,
and loops until the user approves. No figure is redrawn -- the PDF is pure
text/table layout (ctexart + xelatex).
"""

from __future__ import annotations

from .correction_parser import apply_corrections, parse_correction
from .latex_render import graph_to_latex
from .pdf_compiler import compile_graph_pdf, compile_pdf
from .reviewer import HumanReviewer

__all__ = [
    "graph_to_latex",
    "compile_pdf",
    "compile_graph_pdf",
    "parse_correction",
    "apply_corrections",
    "HumanReviewer",
]
