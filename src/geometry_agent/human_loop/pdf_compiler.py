"""Compile a LaTeX string (or GeometryGraph) to PDF with ``xelatex``.

Handles Chinese fonts via the ctexart preamble (Noto Serif/Sans/Mono CJK SC).
Two compile passes are run so that longtable / references stabilise.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..types import GeometryGraph
from .latex_render import graph_to_latex

_KNOWN_ERROR_HINTS = [
    (re.compile(r"Undefined control sequence"), "文本/公式中包含未知的 LaTeX 命令"),
    (re.compile(r"Missing \$ inserted"), "数学模式标记 ($) 缺失或错位"),
    (re.compile(r"Missing \{ inserted|Extra \}"), "花括号不配对"),
    (re.compile(r"Not a letter|Missing \\endcsname"), "命令名书写错误"),
    (re.compile(r"Fatal error|Emergency stop"), "xelatex 严重错误中止"),
    (re.compile(r"font|Font", re.IGNORECASE), "中文字体加载失败 (请安装 texlive-lang-chinese)"),
]

_ERR_LINE = re.compile(r"^(?:!|.*\.tex:\d+:)")

_TIMEOUT_SEC = 120


class PDFCompileError(RuntimeError):
    """Raised when xelatex fails to produce a PDF."""


def _find_xelatex() -> str:
    exe = shutil.which("xelatex")
    if not exe:
        raise PDFCompileError("xelatex not found on PATH; install TeX Live (xelatex).")
    return exe


def unique_pdf_path(out_path: str) -> str:
    """Return ``out_path``, or ``name_1.pdf`` / ``name_2.pdf`` … if it exists."""
    out_path = str(out_path)
    p = Path(out_path)
    if not p.exists():
        return out_path
    stem, suffix = p.stem, p.suffix or ".pdf"
    for i in range(1, 1000):
        cand = p.with_name(f"{stem}_{i}{suffix}")
        if not cand.exists():
            return str(cand)
    return str(p.with_name(f"{stem}_{999}{suffix}"))


def _run_xelatex(build_dir: Path, halt_on_error: bool) -> subprocess.CompletedProcess:
    cmd = [str(_find_xelatex()), "-interaction=nonstopmode",
           "-no-shell-escape", "-file-line-error"]
    if halt_on_error:
        cmd.append("-halt-on-error")
    cmd.append("doc.tex")
    return subprocess.run(cmd, cwd=str(build_dir), capture_output=True,
                          text=True, timeout=_TIMEOUT_SEC)


def compile_pdf(latex: str, out_path: str, unique: bool = False) -> str:
    """Compile ``latex`` source to PDF at ``out_path``.

    Writes a temp ``.tex`` file, runs ``xelatex`` twice in a temp build
    directory, and copies the resulting PDF to ``out_path``. Returns the
    absolute PDF path. Raises :class:`PDFCompileError` on failure. When
    ``unique`` is true an existing target is never overwritten (a
    ``name_1.pdf`` / ``name_2.pdf`` variant is chosen instead).
    """
    out_path = str(out_path)
    if not out_path.lower().endswith(".pdf"):
        out_path = out_path + ".pdf"
    if unique:
        out_path = unique_pdf_path(out_path)
    out_pdf = Path(out_path).resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    build_dir = Path(tempfile.mkdtemp(prefix="ga_latex_"))
    tex_path = build_dir / "doc.tex"

    try:
        tex_path.write_text(latex, encoding="utf-8")

        last_err = ""
        for _ in range(2):
            try:
                proc = _run_xelatex(build_dir, halt_on_error=True)
            except subprocess.TimeoutExpired:
                raise PDFCompileError(f"xelatex 编译超时 (>{_TIMEOUT_SEC}s).")
            if proc.returncode != 0:
                last_err = _extract_error(build_dir, proc)
                proc2 = _run_xelatex(build_dir, halt_on_error=False)
                if (build_dir / "doc.pdf").exists():
                    break
                last_err = _extract_error(build_dir, proc2)
                break

        if not (build_dir / "doc.pdf").exists():
            fixed = _rescue_sanitize(latex)
            if fixed != latex:
                tex_path.write_text(fixed, encoding="utf-8")
                proc3 = _run_xelatex(build_dir, halt_on_error=False)
                if (build_dir / "doc.pdf").exists():
                    shutil.copyfile(build_dir / "doc.pdf", out_pdf)
                    return str(out_pdf)
                last_err = _extract_error(build_dir, proc3)

        built_pdf = build_dir / "doc.pdf"
        if not built_pdf.exists():
            raise PDFCompileError(last_err or "xelatex produced no PDF (unknown reason).")
        shutil.copyfile(built_pdf, out_pdf)
        return str(out_pdf)
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def _extract_error(build_dir: Path, proc: subprocess.CompletedProcess) -> str:
    log_path = build_dir / "doc.log"
    log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
    lines = (log_text or proc.stdout or proc.stderr).splitlines()
    if not lines:
        return "xelatex failed (no log captured)."
    hint = next((msg for pat, msg in _KNOWN_ERROR_HINTS if pat.search(log_text or "")), "")
    err_idx = [i for i, ln in enumerate(lines) if _ERR_LINE.match(ln)]
    if err_idx:
        start = err_idx[0]
        snippet = "\n".join(lines[start:start + 8])
        return f"{hint}: {snippet}" if hint else snippet
    for marker in ("Fatal error", "Emergency stop", "Error:"):
        for i, ln in enumerate(lines):
            if marker in ln:
                snippet = "\n".join(lines[max(0, i - 2):i + 6])
                return f"{hint}: {snippet}" if hint else snippet
    tail = "\n".join(lines[-25:])
    return f"{hint}: {tail}" if hint else tail


def _rescue_sanitize(latex: str) -> str:
    """Structurally repair LaTeX that xelatex refused: ensure the document
    environment is present and braces are balanced. Content is never altered
    (unknown commands are intentionally left to fail loudly)."""
    body = latex
    if r"\begin{document}" not in body:
        for i, ln in enumerate(body.splitlines(keepends=True)):
            if ln.lstrip().startswith(r"\documentclass"):
                body = body[:i] + r"\begin{document}" + "\n" + body[i:]
                break
        if r"\begin{document}" not in body:
            body = r"\begin{document}" + "\n" + body
    if r"\end{document}" not in body:
        body = body.rstrip() + "\n" + r"\end{document}" + "\n"
    opens = closes = 0
    i = 0
    while i < len(body):
        if body[i] == "\\":
            i += 2
            continue
        if body[i] == "{":
            opens += 1
        elif body[i] == "}":
            closes += 1
        i += 1
    if opens > closes:
        body = body.rstrip() + "}" * (opens - closes) + "\n"
    return body


def compile_graph_pdf(
    graph: GeometryGraph,
    problem_text: str,
    out_path: str,
    y_up: bool = False,
    axes: bool = False,
) -> str:
    """Convenience: render ``graph`` to LaTeX and compile to PDF."""
    latex = graph_to_latex(graph, problem_text=problem_text, y_up=y_up, axes=axes)
    return compile_pdf(latex, out_path)


def solution_to_pdf(
    problem_text: str,
    solution,
    graph: GeometryGraph | None = None,
    out_path: str = "solution_report.pdf",
    title: str = "几何题解答报告",
    y_up: bool = False,
    axes: bool = False,
) -> str:
    """Render a full solution report (problem + diagram + solution) to PDF."""
    from ..report import solution_to_latex
    latex = solution_to_latex(problem_text, solution, graph, title, y_up=y_up, axes=axes)
    return compile_pdf(latex, out_path, unique=True)


def multi_question_to_pdf(
    problem_text: str,
    sub_questions: list[dict],
    graph: GeometryGraph | None = None,
    out_path: str = "solution_report.pdf",
    title: str = "几何题解答报告",
    y_up: bool = False,
    axes: bool = False,
) -> str:
    """Render a multi-sub-question problem as a single PDF report."""
    from ..report import multi_question_to_latex
    latex = multi_question_to_latex(problem_text, sub_questions, graph, title, y_up=y_up, axes=axes)
    return compile_pdf(latex, out_path, unique=True)
