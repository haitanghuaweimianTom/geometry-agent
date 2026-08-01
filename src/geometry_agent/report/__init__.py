"""Render a complete solution report (problem + diagram + solution) to LaTeX/PDF.

Supports two modes:
  - Single question: ``solution_to_latex(problem, solution, graph, title)``
  - Multi-sub-question (one big problem with parts (1)(2)(3)):
    ``multi_question_to_latex(problem, sub_questions, graph, title)``

Typography follows formal mathematical writing conventions (cf. amsart style):
  - Chinese text stays in text mode; only genuine math expressions enter ``$...$``.
  - Proof derivations use ``align*`` for aligned multi-step equations.
  - ``amsthm`` proof environments for proof-type questions.
  - ``\displaystyle`` for readable fractions and large operators.

Public API: solution_to_latex, multi_question_to_latex.
"""

from __future__ import annotations

import re
from typing import Any

from ..types import GeometryGraph, ProofStep, Solution, SolveResponse
from ..human_loop.tikz_render import graph_to_tikz


# =====================================================================================
# Text helpers
# =====================================================================================
def _tex_escape(s: str) -> str:
    if s is None:
        return ""
    out = []
    for ch in str(s):
        if ch == "\\":
            out.append(r"\textbackslash{}")
        elif ch in "%&$#_{}":
            out.append("\\" + ch)
        elif ch == "^":
            out.append(r"\textasciicircum{}")
        elif ch == "~":
            out.append(r"\textasciitilde{}")
        else:
            out.append(ch)
    return "".join(out)


# =====================================================================================
# Chinese-ize: replace English tool/relation names with Chinese terms
# =====================================================================================
_EN_TO_CN = [
    # Longer phrases first so they are replaced before shorter fragments
    ("passes through a fixed point", "过定点"),
    ("passes through fixed point", "过定点"),
    ("passes through the fixed point", "过定点"),
    ("fixed point", "定点"),
    ("Let me think", "思考"),
    ("from scratch", "从头开始"),
    ("key observation", "关键观察"),
    ("Problem Setup", "问题分析"),
    ("Step 1", "第1步"),
    ("Step 2", "第2步"),
    ("Step 3", "第3步"),
    ("Step 4", "第4步"),
    ("Step 5", "第5步"),
    ("Step 6", "第6步"),
    ("straight line", "直线"),
    ("Vieta", "韦达"),
    ("collinear", "共线"),
    ("equation", "方程"),
    ("midpoint", "中点"),
    ("slope", "斜率"),
    ("coordinates", "坐标"),
    ("coordinate", "坐标"),
    ("theorem", "定理"),
    ("Conclusion", "结论"),
    ("conclusion", "结论"),
    ("Prove", "证明"),
    ("prove", "证明"),
    ("Goal", "目标"),
    ("goal", "目标"),
    ("solve", "求解"),
    ("verify", "验证"),
    ("det_General", "行列式(一般情形)"),
    ("det_general", "行列式(一般情形)"),
    ("detGeneral", "行列式"),
    ("detgeneral", "行列式"),
    ("det(", "行列式("),
    ("execute_code", "代码计算"),
    ("complex_method", "复数法"),
    ("coordinate_method", "坐标法"),
    ("projective_method", "射影法"),
    ("search", "检索"),
    ("reflect", "反思"),
    ("graph_query", "图查询"),
    ("Perpendicular", "垂直"),
    ("Parallel", "平行"),
    ("Collinear", "共线"),
    ("Intersect", "相交"),
    ("Tangent", "相切"),
    ("Concentric", "同心"),
    ("Inscribed", "内接"),
    ("Circumscribed", "外接"),
    ("Congruent", "全等"),
    ("Similar", "相似"),
    ("TangentPoint", "切点"),
    ("SameArc", "同弧"),
    ("Center", "圆心"),
    ("= true", "成立"),
    ("= false", "不成立"),
    ("True", "成立"),
    ("False", "不成立"),
    ("sympy", "符号计算"),
    ("z3", "约束求解"),
    ("approx", "约等于"),
    ("Segment", "线段"),
    ("Line", "直线"),
    ("line", "直线"),
    ("Ray", "射线"),
    ("Circle", "圆"),
    ("Point", "点"),
    ("Polygon", "多边形"),
    ("Arc", "弧"),
    ("Ellipse", "椭圆"),
    ("ellipse", "椭圆"),
]


def _to_chinese(text: str) -> str:
    if not text:
        return ""
    out = str(text)
    for en, cn in _EN_TO_CN:
        out = out.replace(en, cn)
    return out


# =====================================================================================
# Math segment detection and conversion
# =====================================================================================
# A "math segment" is a maximal run of characters that are clearly mathematical:
# letters (point names like AB, AC), digits, operators, geometry symbols.
# Spaces between math chars are also included so "BD² = 9·DE·DC" stays as one
# segment instead of being split into three.

_MATH_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
_MATH_OPS = set("+-=*/().,^√π·×÷±∓<>≤≥≠≈≅∽∝|[]{}_")
_MATH_GEO = set("∠⊥∥△→∵∴∈²³°∪∩⊂⊃∅∞")
# Greek letters used in geometry (θ, α, β, γ, φ, ω, λ, μ, etc.)
_MATH_GREEK = set("θαβγδεζηικμνξπρστυφχψωΘΑΒΓΔΛΣΦΨΩ")
# Unicode subscript characters (₁₂₃...) and superscript (⁴⁵...)
_MATH_SUB = set("₀₁₂₃₄₅₆₇₈₉")
_MATH_SUP = set("⁰¹²³⁴⁵⁶⁷⁸⁹")

# Single-char symbol → LaTeX command.  IMPORTANT: commands that end in a letter
# MUST have a trailing space so they don't merge with following letters
# (e.g. "\angle BAC" not "\angleBAC" which is an undefined command).
_SYM_TO_LATEX = {
    "∠": r"\angle ",
    "⊥": r"\perp ",
    "∥": r"\parallel ",
    "△": r"\triangle ",
    "·": r"\cdot ",
    "×": r"\times ",
    "≈": r"\approx ",
    "≅": r"\cong ",
    "∽": r"\sim ",
    "≤": r"\le ",
    "≥": r"\ge ",
    "≠": r"\neq ",
    "→": r"\to ",
    "∵": r"\because ",
    "∴": r"\therefore ",
    "∈": r"\in ",
    "²": "^2",
    "³": "^3",
    "√": r"\sqrt ",
    "π": r"\pi ",
    "°": r"^{\circ}",
    "∪": r"\cup ",
    "∩": r"\cap ",
    "∞": r"\infty ",
    # Greek letters
    "θ": r"\theta ",
    "α": r"\alpha ",
    "β": r"\beta ",
    "γ": r"\gamma ",
    "δ": r"\delta ",
    "φ": r"\varphi ",
    "ω": r"\omega ",
    "λ": r"\lambda ",
    "μ": r"\mu ",
    "Σ": r"\Sigma ",
    "Δ": r"\Delta ",
    # Unicode subscripts → _{n}
    "₀": "_{0}", "₁": "_{1}", "₂": "_{2}", "₃": "_{3}", "₄": "_{4}",
    "₅": "_{5}", "₆": "_{6}", "₇": "_{7}", "₈": "_{8}", "₉": "_{9}",
    # Unicode superscripts → ^{n}
    "⁰": "^{0}", "⁴": "^{4}", "⁵": "^{5}", "⁶": "^{6}", "⁷": "^{7}",
    "⁸": "^{8}", "⁹": "^{9}",
}


def _is_math_char(ch: str) -> bool:
    """Whether ``ch`` can appear inside a math segment."""
    return (ch in _MATH_CHARS or ch in _MATH_OPS or ch in _MATH_GEO
            or ch in _MATH_GREEK or ch in _MATH_SUB or ch in _MATH_SUP)


def _fix_sqrt_parens(text: str) -> str:
    r"""Replace ``\sqrt(balanced expr)`` with ``\sqrt{balanced expr}``.

    The simple regex ``\(([^)]*)\)`` fails on nested parens such as
    ``\sqrt(x^2+(y-1/2)^2)``.  This helper scans for ``\sqrt`` followed by
    ``(`` and finds the matching close paren by counting depth.
    """
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        # Look for \sqrt (possibly with trailing space) followed by (
        if text[i] == "\\" and text[i + 1 : i + 5] == "sqrt":
            # Find optional spaces then '('
            k = i + 5
            while k < n and text[k] == " ":
                k += 1
            if k < n and text[k] == "(":
                # Find matching close paren
                depth = 1
                j = k + 1
                while j < n and depth > 0:
                    if text[j] == "(":
                        depth += 1
                    elif text[j] == ")":
                        depth -= 1
                    if depth == 0:
                        break
                    j += 1
                if depth == 0 and j < n:
                    inner = text[k + 1 : j]
                    result.append(r"\sqrt{" + inner + "}")
                    i = j + 1
                    continue
            # Fallback: copy \sqrt as-is
            result.append(text[i : i + 5])
            i += 5
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def _convert_math_segment(seg: str) -> str:
    """Convert a raw math segment (no Chinese) to LaTeX math-mode content.

    Handles symbol replacement, sqrt{} fixing, S△ABC → S_{\\triangle ABC},
    simple fractions a/b → \\frac{a}{b}, and cleanup of extra spaces.
    """
    out = seg
    for sym, cmd in _SYM_TO_LATEX.items():
        out = out.replace(sym, cmd)
    # \sqrt followed by (expr) → \sqrt{expr}  (match BALANCED parens, support nesting)
    out = _fix_sqrt_parens(out)
    # \sqrt followed by digit/letter → \sqrt{...}
    out = re.sub(r"\\sqrt\s+(\d+)", r"\\sqrt{\1}", out)
    out = re.sub(r"\\sqrt\s+([A-Za-z])", r"\\sqrt{\1}", out)
    # S△ABC → S_{\triangle ABC}  (also S_\triangle without space)
    out = re.sub(r"S\\triangle\s*([A-Z]+)", r"S_{\\triangle \1}", out)
    # Coordinate subscripts: xM → x_M, yN → y_N, xA → x_A etc.
    # Pattern: x or y followed by a single uppercase letter (point name),
    # but NOT followed by another letter (to avoid breaking xMax etc.)
    # Also avoid matching when preceded by \ (already a command) or _ (already subscript)
    out = re.sub(r"(?<![_\\a-zA-Z])([xy])([A-Z])(?![a-zA-Z])", r"\1_\2", out)
    # Numbered variables: x1 → x_1, x2 → x_2, y1 → y_1 (in math contexts)
    # Note: no digit lookbehind so consecutive x1x2 → x_{1}x_{2}
    out = re.sub(r"(?<![_\\a-zA-Z])([xy])(\d{1,2})(?![0-9])", r"\1_{\2}", out)
    # Protect underscores inside multi-letter identifiers (det_General, max_val)
    # so they render as a literal "_" instead of subscripting the next char.
    # Single-letter subscripts (x_M, y_N) are kept as real subscripts.
    out = re.sub(r"(?<=[A-Za-z]{2})_(?=[A-Za-z])", r"\\_", out)
    # Math function names: cos, sin, tan, ln, log, exp → \cos, \sin, ...
    for fn_name in ["cos", "sin", "tan", "cot", "sec", "csc",
                    "ln", "log", "exp", "lim", "max", "min", "arcsin", "arccos", "arctan"]:
        out = re.sub(r"\b" + fn_name + r"(?![a-zA-Z])", r"\\" + fn_name + " ", out)
    # sqrt(number) without braces → sqrt{number}
    out = re.sub(r"\\sqrt\s*(\d+)", r"\\sqrt{\1}", out)

    # ---- Fraction conversion ----
    # Convert A/B patterns to \frac{A}{B} for various token types.
    # A "frac token" is one of (tried longest-first):
    #   N\sqrt{..}\^?digit?   (e.g. 2\sqrt{5}, 2\sqrt{5}^2)
    #   \sqrt{..}\^?digit?    (e.g. \sqrt{35})
    #   (expr)                (e.g. (\sqrt{5}) or (x_{1}+x_{2}))
    #   letters\^digit        (e.g. x^2, AE^2)
    #   letters_\{..\}        (e.g. S_{1}, x_{1})
    #   letters\d*            (e.g. AB, CE, a, 2ab — but leading digit only if followed by letter)
    #   -?digits              (e.g. 35, -5)
    _frac_token = (
        r"(?:"
        r"\d*\\sqrt\{[^}]+\}(?:\^\d+)?"   # 2\sqrt{5}, \sqrt{35}^2
        r"|\\sqrt\{[^}]+\}(?:\^\d+)?"      # \sqrt{35}
        r"|\([^)]*\)"                       # (expr)
        r"|[A-Za-z]{1,4}(?:\^\d+)"         # x^2, AE^2
        r"|[A-Za-z]_\{[^}]+\}"             # S_{1}, x_{1}
        r"|[A-Za-z]{1,4}\d*"               # AB, CE, a
        r"|-?\d+"                           # 35, -5
        r")"
    )
    out = re.sub(
        r"(?<![_^a-zA-Z])(" + _frac_token + r")\s*/\s*(" + _frac_token + r")",
        r"\\frac{\1}{\2}",
        out,
    )
    # Collapse multiple spaces inside math
    out = re.sub(r"  +", " ", out)
    # Remove spaces right after ^ or _ (e.g. "^ 2" → "^2")
    out = re.sub(r"\^\s+", "^", out)
    out = re.sub(r"_\s+", "_", out)
    # Clean up space before ^{\circ}
    out = re.sub(r"\s+\^", "^", out)
    # Remove space between \theta and following content if it's an operator
    out = re.sub(r"(\\theta\s+)\s", r"\1", out)
    return out.strip()


def _format_inline(text: str) -> str:
    """Format a mixed Chinese+math string for inline LaTeX.

    Chinese text stays in text mode (escaped); maximal runs of math
    characters (including spaces between math chars) are wrapped in
    ``$...$`` with symbol conversion.
    """
    if not text:
        return ""
    s = _to_chinese(str(text))
    # Protect pre-formatted LaTeX commands from re-processing.
    # Convert "向量XY" to \overrightarrow{XY} as a protected math token.
    placeholders: list[str] = []
    def _stash(m):
        placeholders.append(r"\overrightarrow{" + m.group(1) + "}")
        return f"\x00{len(placeholders)-1}\x00"
    s = re.sub(r"向量\s*([A-Z]{1,6})", _stash, s)
    n = len(s)
    segments: list[tuple[bool, str]] = []
    i = 0
    while i < n:
        # Check for a placeholder \x00N\x00
        if s[i] == "\x00":
            j = s.find("\x00", i + 1)
            if j != -1:
                segments.append(("placeholder", s[i : j + 1]))
                i = j + 1
                continue
        if _is_math_char(s[i]):
            j = i
            while j < n:
                if _is_math_char(s[j]):
                    j += 1
                elif s[j] == " " and j + 1 < n and _is_math_char(s[j + 1]):
                    j += 1
                else:
                    break
            segments.append((True, s[i:j]))
            i = j
        else:
            j = i
            while j < n and not _is_math_char(s[j]) and s[j] != "\x00":
                j += 1
            segments.append((False, s[i:j]))
            i = j

    parts: list[str] = []
    for seg in segments:
        if seg[0] == "placeholder":
            idx = int(seg[1].strip("\x00"))
            parts.append(f"${placeholders[idx]}$")
        elif seg[0] is True:
            converted = _convert_math_segment(seg[1])
            if converted:
                parts.append(f"${converted}$")
        else:
            parts.append(_tex_escape(seg[1]))
    return "".join(parts)


def _format_math_display(text: str) -> str:
    """Format a pure math expression for display mode ``$$...$$``.

    Used when a statement is expected to be a standalone equation.
    """
    if not text:
        return ""
    s = _to_chinese(str(text))
    converted = _convert_math_segment(s)
    return f"$$\\displaystyle {converted}$$"


# =====================================================================================
# Proof block — formal numbered steps with aligned derivations
# =====================================================================================
def _is_raw_llm_garbage(text: str) -> bool:
    """Detect if a proof step is raw LLM prose rather than a clean statement.

    Catches:
    - English-heavy text (LLM thinking out loud in English)
    - "Let me analyze" / "We have" / "From the given" patterns
    - Very long text (>200 chars) that's likely a full paragraph
    - Text with "raw LLM output" as reason
    """
    if not text:
        return True
    s = str(text).strip()
    if not s:
        return True
    # JSON plan leaks
    if s.startswith("{") and '"plan"' in s:
        return True
    if s.startswith('{"step"'):
        return True
    # English thinking-out-loud patterns
    en_starts = ("Let me", "Let us", "We have", "We need", "We can", "We set",
                 "From the given", "From this", "I will", "I need",
                 "First,", "Now,", "So ", "This means",
                 "Note that", "Given that", "By the", "Since ", "Thus ",
                 "Therefore ", "Hence ", "Using ", "Applying ", "We get",
                 "We know", "We see", "Let's", "I'll", "I have")
    if any(s.startswith(p) for p in en_starts):
        return True
    # Count English words vs Chinese chars — if mostly English, it's garbage
    en_words = len(re.findall(r"[a-zA-Z]{2,}", s))
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", s))
    if en_words > 5 and cn_chars < 3 and len(s) > 50:
        return True
    # Too long = probably a paragraph, not a step
    if len(s) > 250:
        return True
    return False


def _clean_statement(text: str) -> str:
    """Clean a proof step statement: remove raw JSON leaks and artifacts."""
    if not text:
        return ""
    s = str(text).strip()
    # Remove JSON plan leaks
    if s.startswith("{") and '"plan"' in s:
        return ""
    if s.startswith('{"step"'):
        return ""
    # Remove markdown code fence artifacts
    s = re.sub(r"```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```", "", s)
    # Remove "verified":true/false artifacts
    s = re.sub(r'"verified"?\s*:\s*(true|false)', "", s)
    # Truncate at first raw JSON marker
    s = re.sub(r'\{"step".*$', "", s)
    return s.strip()


def _proof_block(proof: list[ProofStep]) -> list[str]:
    """Render proof steps in formal style.

    Each step is a numbered item. The statement is rendered inline (mixed
    text+math). The reason follows on the next line in smaller italic text.
    No verification marks (per user request).
    """
    lines: list[str] = []
    # Filter out empty/JSON-leak/raw-LLM-prose steps
    clean_steps = []
    for st in proof:
        cleaned = _clean_statement(st.statement)
        if cleaned and not _is_raw_llm_garbage(cleaned):
            # Also filter out steps whose reason is "raw LLM output"
            reason = _clean_statement(st.reason) if st.reason else ""
            if reason == "raw LLM output" and _is_raw_llm_garbage(cleaned):
                continue
            clean_steps.append((st, cleaned))
    if not clean_steps:
        lines.append(r"\textit{（未生成解答步骤）}")
        return lines
    # 使用圈号 ①②③ 作为步骤编号（小题用括号 (1)(2) 加以区分）
    lines.append(
        r"\begin{enumerate}[label={\small\textcircled{\arabic*}}, leftmargin=2.8em, itemsep=8pt, topsep=4pt]"
    )
    for st, cleaned in clean_steps:
        stmt = _format_inline(cleaned)
        reason = _format_inline(_clean_statement(st.reason)) if st.reason else ""
        lines.append(rf"\item {stmt}")
        if reason:
            lines.append(
                rf"\par\noindent\hspace*{{1.4em}}{{\small\textit{{理由：}}{reason}}}"
            )
    lines.append(r"\end{enumerate}")
    return lines


# =====================================================================================
# Preamble — formal exam-paper style (inspired by amsart)
# =====================================================================================
def _preamble(title: str) -> list[str]:
    return [
        r"\documentclass[UTF8, a4paper, 11pt]{ctexart}",
        r"\setCJKmainfont{Noto Serif CJK SC}",
        r"\setCJKsansfont{Noto Sans CJK SC}",
        r"\setCJKmonofont{Noto Sans Mono CJK SC}[Scale=0.85]",
        r"\usepackage{geometry}",
        r"\geometry{a4paper, margin=2.2cm}",
        r"\usepackage{xcolor}",
        r"\usepackage{tikz}",
        r"\usepackage{amsmath, amssymb, amsthm}",
        r"\usepackage{booktabs}",
        r"\usepackage{setspace}",
        r"\usepackage{enumitem}",
        r"\usepackage{tcolorbox}",
        r"\tcbuselibrary{skins}",
        r"\onehalfspacing",
        r"\setlength{\parskip}{4pt}",
        r"\setlength{\parindent}{2em}",
        # theorem environments
        r"\newtheorem{proposition}{命题}",
        r"\newtheorem{lemma}{引理}",
        r"\newtheorem{corollary}{推论}",
        # title style — formal, with rule
        r"\renewcommand{\maketitle}{%",
        r"  \begin{center}",
        r"    {\LARGE\bfseries ",
        "      " + _tex_escape(title),
        r"    }",
        r"  \end{center}",
        r"  \vspace{-0.4em}",
        r"  \hrule height 0.8pt",
        r"  \vspace{1.2em}",
        r"}",
        r"\date{}",
        # answer box style
        r"\newtcolorbox{answerbox}{colback=blue!4, colframe=blue!40!black, boxrule=0.6pt, arc=2pt, left=10pt, right=10pt, top=5pt, bottom=5pt}",
        r"\newtcolorbox{infobox}{colback=gray!6, colframe=gray!50, boxrule=0.4pt, arc=1pt, left=8pt, right=8pt, top=4pt, bottom=4pt}",
    ]


def _sanitize_answer(answer: str) -> str:
    """Clean up an answer string for display.

    If the answer is empty or looks like a raw problem statement leak,
    return "（未解出）".  Proof conclusions may be long, so we allow up to
    500 characters (the table wraps long text via ``p{}`` column).
    """
    if not answer or not answer.strip():
        return "（未解出）"
    a = answer.strip()
    # Very long answers are likely leaked text; cap at 500 chars.
    if len(a) > 500:
        a = a[:500] + "…"
    # If it starts with problem-statement markers AND is short, it's leaked.
    if len(a) < 60 and any(a.startswith(m) for m in ("在", "已知", "如图", "过")):
        return "（未解出）"
    return a


def _answer_box(answer: str) -> list[str]:
    ans = _format_inline(_sanitize_answer(answer))
    return [
        r"\begin{answerbox}",
        r"\textbf{答案：}" + ans,
        r"\end{answerbox}",
    ]


# =====================================================================================
# Single-question mode
# =====================================================================================
def solution_to_latex(
    problem_text: str,
    solution: Solution | SolveResponse,
    graph: GeometryGraph | None = None,
    title: str = "几何题解答报告",
) -> str:
    proof = getattr(solution, "proof", [])
    answer = getattr(solution, "answer", "")
    confidence = getattr(solution, "confidence", 0.0)
    verified = getattr(solution, "verified", False)

    lines = _preamble(title)
    lines += [r"\begin{document}", r"\maketitle"]

    # ---- 题目 ----
    lines.append(r"\section*{一、题目}")
    lines.append(_format_inline(problem_text))
    lines.append("")

    # ---- 几何图形 ----
    if graph is not None:
        tikz = graph_to_tikz(graph)
        if tikz:
            lines.append(r"\section*{二、几何图形}")
            lines.append(tikz)
            lines.append("")

    # ---- 解答 ----
    lines.append(r"\section*{三、解答}")
    lines += _proof_block(proof)
    lines.append("")

    # ---- 答案 ----
    lines.append(r"\section*{四、答案}")
    lines += _answer_box(answer)

    # ---- 解题思路与关键算式附录 ----
    reasoning_summary = getattr(solution, "reasoning_summary", "") or ""
    reasoning_trace = getattr(solution, "reasoning_trace", [])
    key_equations = getattr(solution, "key_equations", []) or []
    if reasoning_summary or reasoning_trace or key_equations:
        lines += _reasoning_appendix(reasoning_summary, reasoning_trace, key_equations)

    lines += ["", r"\end{document}"]
    return "\n".join(lines) + "\n"


def _reasoning_appendix(
    reasoning_summary: str,
    reasoning_trace: list[str],
    key_equations: list[str],
) -> list[str]:
    """Render a '解题思路与关键算式' appendix.

    Both sections are written by the LLM itself (in its final JSON):
    1. ``summary`` → 解题思路 (the model's own reasoning narrative).
    2. ``key_equations`` → 关键算式 (the core formulas of the proof,
       chosen by the model — NOT scraped from tool output).

    Falls back to ``reasoning_trace`` entries only when ``summary`` is empty
    (legacy / fallback path). Tool-call outputs are never dumped here.
    """
    lines = [
        r"\section*{五、解题思路与关键算式}",
        "",
    ]

    # ---- Part 1: LLM-decided 解题思路 ----
    summary = (reasoning_summary or "").strip()
    if not summary:
        # Legacy fallback: use reasoning_trace entries, filtering meta-talk.
        _meta_skip = (
            "JSON", "json", "输出证明", "然后输出", "让我用", "让我最后",
            "求解工具", "工具调用", "调用工具", "进行验证", "开始验证",
        )
        for insight in reasoning_trace:
            if not insight or not insight.strip():
                continue
            pos = min((insight.find(m) for m in _meta_skip if m in insight),
                      default=-1)
            if pos >= 0:
                if pos <= 20 or pos < len(insight) // 2:
                    continue
                insight = insight[:pos].rstrip("；，。 ")
            if insight.strip():
                summary += insight.strip() + "。"
    summary = summary.strip("；，。 \t")

    if summary:
        lines.append(r"\subsection*{解题思路}")
        lines.append(r"\begin{quote}")
        lines.append(_format_inline(summary))
        lines.append(r"\end{quote}")
        lines.append("")

    # ---- Part 2: LLM-decided 关键算式 (no tool-output scraping) ----
    if key_equations:
        lines.append(r"\subsection*{关键算式}")
        lines.append(r"\begin{itemize}[leftmargin=2em, itemsep=4pt]")
        for eq in key_equations:
            eq = (eq or "").strip()
            if eq:
                lines.append(rf"\item {_format_inline(eq)}")
        lines.append(r"\end{itemize}")

    return lines


# =====================================================================================
# Multi-sub-question mode (one big problem, parts (1)(2)(3), single PDF)
# =====================================================================================
def multi_question_to_latex(
    problem_text: str,
    sub_questions: list[dict],
    graph: GeometryGraph | None = None,
    title: str = "几何题解答报告",
) -> str:
    lines = _preamble(title)
    lines += [r"\begin{document}", r"\maketitle"]

    # ---- 题目 ----
    lines.append(r"\section*{一、题目}")
    lines.append(_format_inline(problem_text))
    lines.append("")
    lines.append(
        r"\begin{enumerate}[label=\textbf{(\arabic*)}, leftmargin=2.6em, itemsep=4pt]"
    )
    for sq in sub_questions:
        qtext = sq.get("question", "")
        # Strip leading "(N)" label from question text to avoid double numbering
        qtext = re.sub(r"^\s*[\(（]\d+[\)）]\s*", "", qtext)
        lines.append(r"\item " + _format_inline(qtext))
    lines.append(r"\end{enumerate}")
    lines.append("")

    # ---- 几何图形 ----
    if graph is not None:
        tikz = graph_to_tikz(graph)
        if tikz:
            lines.append(r"\section*{二、几何图形}")
            lines.append(tikz)
            lines.append("")

    # ---- 解答 ----
    lines.append(r"\section*{三、解答}")
    all_conf = []
    all_verified = True
    total_steps = 0
    for idx, sq in enumerate(sub_questions):
        label = sq.get("label", f"({idx+1})")
        sol = sq.get("solution")
        proof = getattr(sol, "proof", []) if sol else []
        answer = getattr(sol, "answer", "") if sol else ""
        conf = getattr(sol, "confidence", 0.0) if sol else 0.0
        ver = getattr(sol, "verified", False) if sol else False
        all_conf.append(conf)
        all_verified = all_verified and ver
        total_steps += len(proof)

        qtext = sq.get("question", "")
        qtext = re.sub(r"^\s*[\(（]\d+[\)）]\s*", "", qtext)
        lines.append(rf"\subsection*{{{label} {_format_inline(qtext)}}}")
        lines += _proof_block(proof)
        lines += _answer_box(answer)
        lines.append(r"\vspace{10pt}")
    lines.append("")

    # ---- 最终答案汇总 ----
    lines.append(r"\section*{四、最终答案}")
    lines.append(r"\begin{center}")
    lines.append(r"\renewcommand{\arraystretch}{1.4}")
    lines.append(r"\begin{tabular}{@{}c p{0.78\textwidth}@{}}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{小题} & \textbf{答案} \\")
    lines.append(r"\midrule")
    for sq in sub_questions:
        label = sq.get("label", "")
        sol = sq.get("solution")
        answer = getattr(sol, "answer", "") if sol else ""
        ans = _format_inline(_sanitize_answer(answer))
        lines.append(rf"{label} & {ans} \\[2pt]")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{center}")

    # ---- 解题思路与关键算式附录 ----
    all_summary: list[str] = []
    all_trace: list[str] = []
    all_key_eqs: list[str] = []
    for idx, sq in enumerate(sub_questions):
        sol = sq.get("solution")
        if sol:
            sm = getattr(sol, "reasoning_summary", "") or ""
            if sm.strip():
                all_summary.append(f"【第{idx+1}问】{sm.strip()}")
            for t in getattr(sol, "reasoning_trace", []):
                all_trace.append(f"【第{idx+1}问】{t}")
            for eq in getattr(sol, "key_equations", []) or []:
                all_key_eqs.append(f"【第{idx+1}问】{eq}")
    if all_summary or all_trace or all_key_eqs:
        lines += _reasoning_appendix(
            "；".join(all_summary), all_trace, all_key_eqs,
        )

    lines += ["", r"\end{document}"]
    return "\n".join(lines) + "\n"


__all__ = ["solution_to_latex", "multi_question_to_latex"]
