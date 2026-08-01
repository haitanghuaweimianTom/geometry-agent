"""Compile a LaTeX string (or GeometryGraph) to PDF with ``xelatex``.

Handles Chinese fonts via the ctexart preamble (Noto Serif/Sans/Mono CJK SC).
Two compile passes are run so that longtable / references stabilise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..types import GeometryGraph
from .latex_render import graph_to_latex


class PDFCompileError(RuntimeError):
    """Raised when xelatex fails to produce a PDF."""


def _find_xelatex() -> str:
    exe = shutil.which("xelatex")
    if not exe:
        raise PDFCompileError("xelatex not found on PATH; install TeX Live (xelatex).")
    return exe


def compile_pdf(latex: str, out_path: str) -> str:
    """Compile ``latex`` source to PDF at ``out_path``.

    Writes a temp ``.tex`` file, runs ``xelatex`` twice in a temp build
    directory, and copies the resulting PDF to ``out_path``. Returns the
    absolute PDF path. Raises :class:`PDFCompileError` on failure.
    """
    out_path = str(out_path)
    if not out_path.lower().endswith(".pdf"):
        out_path = out_path + ".pdf"
    out_pdf = Path(out_path).resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    exe = _find_xelatex()
    build_dir = Path(tempfile.mkdtemp(prefix="ga_latex_"))
    tex_path = build_dir / "doc.tex"

    try:
        tex_path.write_text(latex, encoding="utf-8")

        last_err = ""
        for _ in range(2):
            proc = subprocess.run(
                [exe, "-interaction=nonstopmode", "-halt-on-error",
                 "-no-shell-escape", "doc.tex"],
                cwd=str(build_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            log_path = build_dir / "doc.log"
            log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
            if proc.returncode != 0:
                last_err = _extract_error(log_text, proc.stdout + proc.stderr)
                # retry once without -halt-on-error to capture more context
                proc2 = subprocess.run(
                    [exe, "-interaction=nonstopmode", "-no-shell-escape", "doc.tex"],
                    cwd=str(build_dir), capture_output=True, text=True, timeout=120,
                )
                if (build_dir / "doc.pdf").exists():
                    break
                log_path = build_dir / "doc.log"
                log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
                last_err = _extract_error(log_text, proc2.stdout + proc2.stderr)
                break

        built_pdf = build_dir / "doc.pdf"
        if not built_pdf.exists():
            raise PDFCompileError(last_err or "xelatex produced no PDF (unknown reason).")
        shutil.copyfile(built_pdf, out_pdf)
        return str(out_pdf)
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def _extract_error(log_text: str, std: str) -> str:
    if not log_text and not std:
        return "xelatex failed (no log captured)."
    lines = log_text.splitlines() or std.splitlines()
    err_idx = [i for i, ln in enumerate(lines) if ln.startswith("!")]
    if err_idx:
        start = err_idx[0]
        snippet = "\n".join(lines[start:start + 8])
        return snippet
    for marker in ("Fatal error", "Emergency stop", "Error:"):
        for i, ln in enumerate(lines):
            if marker in ln:
                return "\n".join(lines[max(0, i - 2):i + 6])
    tail = "\n".join(lines[-25:]) if lines else std[-800:]
    return tail


def compile_graph_pdf(graph: GeometryGraph, problem_text: str, out_path: str) -> str:
    """Convenience: render ``graph`` to LaTeX and compile to PDF."""
    latex = graph_to_latex(graph, problem_text=problem_text)
    return compile_pdf(latex, out_path)


def solution_to_pdf(
    problem_text: str,
    solution,
    graph: GeometryGraph | None = None,
    out_path: str = "solution_report.pdf",
    title: str = "几何题解答报告",
) -> str:
    """Render a full solution report (problem + diagram + solution) to PDF."""
    from ..report import solution_to_latex
    latex = solution_to_latex(problem_text, solution, graph, title)
    return compile_pdf(latex, out_path)


def multi_question_to_pdf(
    problem_text: str,
    sub_questions: list[dict],
    graph: GeometryGraph | None = None,
    out_path: str = "solution_report.pdf",
    title: str = "几何题解答报告",
) -> str:
    """Render a multi-sub-question problem as a single PDF report."""
    from ..report import multi_question_to_latex
    latex = multi_question_to_latex(problem_text, sub_questions, graph, title)
    return compile_pdf(latex, out_path)
