"""HumanReviewer -- orchestrates the LaTeX preview & correction loop.

Three entry points:

* :meth:`HumanReviewer.review` -- non-interactive: render the PDF and return
  a :class:`ReviewResult` with ``approved=False`` and the PDF path, waiting
  for the caller to supply corrections.
* :meth:`HumanReviewer.review_with_corrections` -- non-interactive: apply a
  caller-supplied list of :class:`Correction`, regenerate the PDF, and
  return ``approved=True``.
* :meth:`HumanReviewer.review_interactive` -- CLI loop: render -> prompt ->
  parse -> apply -> re-render, until ``approve`` or ``max_rounds`` reached.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..config import HumanLoopConfig
from ..types import (
    Correction,
    CorrectionType,
    GeometryGraph,
    ReviewResult,
)
from .correction_parser import apply_corrections, parse_correction
from .pdf_compiler import compile_graph_pdf

logger = logging.getLogger(__name__)


class HumanReviewer:
    """Orchestrates the human-in-the-loop review cycle."""

    def __init__(self, config: HumanLoopConfig | None = None):
        self.config = config or HumanLoopConfig()

    def review(
        self,
        graph: GeometryGraph,
        problem_text: str,
        out_dir: str | None = None,
    ) -> ReviewResult:
        """Non-interactive: produce the PDF and return it for the caller to
        forward to a human. ``approved`` is False until corrections are
        applied via :meth:`review_with_corrections`."""
        out_dir = self._ensure_out_dir(out_dir)
        pdf_path = compile_graph_pdf(graph, problem_text,
                                     os.path.join(out_dir, "review.pdf"))
        if self.config.open_pdf:
            _open_pdf(pdf_path)
        return ReviewResult(
            approved=False,
            corrections=[],
            corrected_graph=graph,
            pdf_path=pdf_path,
            rounds=0,
        )

    def review_with_corrections(
        self,
        graph: GeometryGraph,
        problem_text: str,
        corrections: list[Correction],
        out_dir: str | None = None,
    ) -> ReviewResult:
        """Apply ``corrections`` to ``graph`` and regenerate the PDF.

        Returns a :class:`ReviewResult` with ``approved=True`` (the caller
        has already decided the correction round is complete)."""
        out_dir = self._ensure_out_dir(out_dir)
        # Ensure each correction has parsed actions: if a correction was
        # supplied with raw text but empty actions, parse it now.
        parsed: list[Correction] = []
        for c in corrections:
            if not c.actions and c.text:
                c = parse_correction(c.text, c.kind, graph)
            parsed.append(c)
        corrected = apply_corrections(graph, parsed)
        pdf_path = compile_graph_pdf(corrected, problem_text,
                                     os.path.join(out_dir, "review_corrected.pdf"))
        if self.config.open_pdf:
            _open_pdf(pdf_path)
        return ReviewResult(
            approved=True,
            corrections=parsed,
            corrected_graph=corrected,
            pdf_path=pdf_path,
            rounds=1,
        )

    def review_interactive(
        self,
        graph: GeometryGraph,
        problem_text: str,
        out_dir: str | None = None,
        input_stream: Any = None,
        output_stream: Any = None,
    ) -> ReviewResult:
        """CLI interactive loop. Renders a PDF, prints its path, reads user
        input (``approve`` to finish, or a correction -- prefix ``dsl:``
        for DSL mode), parses + applies, re-renders, until ``approve`` or
        ``max_rounds`` reached."""
        out_dir = self._ensure_out_dir(out_dir)
        inp = input_stream if input_stream is not None else sys.stdin
        out = output_stream if output_stream is not None else sys.stdout

        current = graph
        all_corrections: list[Correction] = []
        rounds = 0
        pdf_path = ""

        while rounds < self.config.max_rounds:
            rounds += 1
            fname = f"review_round{rounds}.pdf"
            pdf_path = compile_graph_pdf(current, problem_text,
                                         os.path.join(out_dir, fname))
            if self.config.open_pdf:
                _open_pdf(pdf_path)

            out.write(f"\n[轮次 {rounds}/{self.config.max_rounds}] PDF 已生成: {pdf_path}\n")
            out.write("请审阅后输入:\n")
            out.write("  - approve          确认无误,结束审阅\n")
            out.write("  - dsl: <DSL文本>   以 DSL 模式纠错 (首行带 dsl: 前缀)\n")
            out.write("  - <自然语言纠错>   例如: 删除 AB 垂直 CD\n")
            out.flush()

            line = inp.readline()
            if not line:
                out.write("输入结束,默认 approve。\n")
                out.flush()
                return ReviewResult(
                    approved=True,
                    corrections=all_corrections,
                    corrected_graph=current,
                    pdf_path=pdf_path,
                    rounds=rounds,
                )
            text = line.strip()
            if not text:
                continue

            if text.lower() in ("approve", "ok", "y", "yes", "确认", "通过"):
                return ReviewResult(
                    approved=True,
                    corrections=all_corrections,
                    corrected_graph=current,
                    pdf_path=pdf_path,
                    rounds=rounds,
                )

            mode = CorrectionType.DSL_EDIT if text.lower().startswith("dsl:") \
                else CorrectionType.NATURAL_LANGUAGE
            corr = parse_correction(text, mode, current)
            all_corrections.append(corr)
            current = apply_corrections(current, [corr])
            out.write(f"已应用纠错 (模式={mode.value}, 动作数={len(corr.actions)})。\n")
            out.flush()

        out.write(f"已达最大轮次 {self.config.max_rounds},结束审阅。\n")
        out.flush()
        return ReviewResult(
            approved=False,
            corrections=all_corrections,
            corrected_graph=current,
            pdf_path=pdf_path,
            rounds=rounds,
        )

    def _ensure_out_dir(self, override: str | None) -> str:
        d = override or self.config.out_dir
        Path(d).mkdir(parents=True, exist_ok=True)
        return d


def _open_pdf(pdf_path: str) -> None:
    """Best-effort open the PDF with the platform viewer."""
    try:
        if sys.platform.startswith("darwin"):
            subprocess.run(["open", pdf_path], check=False)
        elif os.name == "nt":
            os.startfile(pdf_path)  # type: ignore[attr-defined]
        else:
            for cmd in ("xdg-open", "gio"):
                if shutil.which(cmd):
                    subprocess.run([cmd, pdf_path], check=False)
                    break
    except Exception as exc:
        logger.warning("failed to open PDF %s: %s", pdf_path, exc)
