"""Render a complete solution report (problem + diagram + solution) to LaTeX/PDF.

Supports two modes:
  - Single question: ``solution_to_latex(problem, solution, graph, title)``
  - Multi-sub-question (one big problem with parts (1)(2)(3)):
    ``multi_question_to_latex(problem, sub_questions, graph, title)``

Typography follows formal mathematical writing conventions (cf. amsart style):
  - Chinese text stays in text mode; only genuine math expressions enter ``$...$``.
  - Proof derivations use ``align*`` for aligned multi-step equations.
  - ``amsthm`` proof environments for proof-type questions.
  - ``\\displaystyle`` for readable fractions and large operators.

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
# （ ） ， are included so full-width coordinates like （1，2） stay in one math segment
# − (U+2212) is the typographic minus sign common in Chinese exam text;
# \u0304 is the combining macron (p̄ for sample mean). Both must stay inside
# math segments so they convert cleanly instead of leaking into text mode.
_MATH_OPS = set("+-=*/().,^√π·×÷±∓<>≤≥≠≈≅∽∝|[]{}_（），∶−\u0304")
_MATH_GEO = set("∠⊥∥△→∵∴∈²³°∪∩⊂⊃∅∞⌒⊙□∟≡∉∀∃⇒⇔⋯…∼∘∂∑∏∫′∇")
# Greek letters used in geometry (θ, α, β, γ, φ, ω, λ, μ, etc.)
_MATH_GREEK = set("θαβγδεζηικλμνξοπρστυφχψωΘΑΒΓΔΛΣΦΨΩ")
# Unicode subscript characters: digits ₁₂₃..., letters ₙₖₓ..., operators ₊₋₌₍₎
_MATH_SUB = set("₀₁₂₃₄₅₆₇₈₉ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ₊₋₌₍₎")
# Unicode superscript characters: digits ⁰¹..., letters ᵃᵇᶜⁿ..., operators ⁺⁻⁼⁽⁾
_MATH_SUP = set("⁰¹²³⁴⁵⁶⁷⁸⁹⁻ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ⁺⁼⁽⁾")

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
    "≌": r"\cong ",
    "²": "^2",
    "³": "^3",
    "¹": "^1",
    "√": r"\sqrt ",
    "π": r"\pi ",
    "°": r"^{\circ}",
    "∪": r"\cup ",
    "∩": r"\cap ",
    "∞": r"\infty ",
    # ---- v2: added symbols (all must render correctly) ----
    "∝": r"\propto ",
    "±": r"\pm ",
    "∓": r"\mp ",
    "÷": r"\div ",
    "≡": r"\equiv ",
    "⊂": r"\subset ",
    "⊃": r"\supset ",
    "⊆": r"\subseteq ",
    "⊇": r"\supseteq ",
    "∉": r"\notin ",
    "∀": r"\forall ",
    "∃": r"\exists ",
    "⇒": r"\Rightarrow ",
    "⇔": r"\Leftrightarrow ",
    "←": r"\leftarrow ",
    "↔": r"\leftrightarrow ",
    "∇": r"\nabla ",
    "⊙": r"\odot ",
    "□": r"\square ",
    "∟": r"\lrcorner ",
    "⋯": r"\cdots ",
    "…": r"\ldots ",
    "∼": r"\sim ",
    "∘": r"\circ ",
    "∂": r"\partial ",
    "∑": r"\sum ",
    "∏": r"\prod ",
    "∫": r"\int ",
    "′": "'",
    "∅": r"\varnothing ",
    "⌒": r"\frown ",  # fallback; "⌒AB" is handled by the overset pre-pass below
    "⁻": "^{-}",  # ⁻¹ is handled by the pre-pass; lone ⁻ kept valid
    "−": "-",  # U+2212 typographic minus (common in Chinese exam text) → ASCII '-'
    # Greek letters (complete set)
    "ε": r"\varepsilon ",
    "η": r"\eta ",
    "ι": r"\iota ",
    "κ": r"\kappa ",
    "ν": r"\nu ",
    "ξ": r"\xi ",
    "ρ": r"\rho ",
    "σ": r"\sigma ",
    "τ": r"\tau ",
    "υ": r"\upsilon ",
    "χ": r"\chi ",
    "ψ": r"\psi ",
    "ζ": r"\zeta ",
    "Θ": r"\Theta ",
    "Γ": r"\Gamma ",
    "Π": r"\Pi ",
    "Υ": r"\Upsilon ",
    "Ψ": r"\Psi ",
    "Ω": r"\Omega ",
    "Λ": r"\Lambda ",
    "Ξ": r"\Xi ",
    "Φ": r"\Phi ",
    # original Greek letters kept for back-compat
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
    # Unicode superscripts → ^{n}  (¹ ² ³ come from the main maps above)
    "⁰": "^{0}", "⁴": "^{4}", "⁵": "^{5}", "⁶": "^{6}", "⁷": "^{7}",
    "⁸": "^{8}", "⁹": "^{9}",
}

# Unicode subscript LETTERS/operators → plain ASCII (merged into one _{} group
# by the run pre-pass, e.g. aₙ₊₁ → a_{n+1})
_SUB_TO_ASCII = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "ₐ": "a", "ₑ": "e", "ₕ": "h", "ᵢ": "i", "ⱼ": "j", "ₖ": "k",
    "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₒ": "o", "ₚ": "p", "ᵣ": "r",
    "ₛ": "s", "ₜ": "t", "ᵤ": "u", "ᵥ": "v", "ₓ": "x",
    "₊": "+", "₋": "-", "₌": "=", "₍": "(", "₎": ")",
}

# Unicode superscript LETTERS/operators → plain ASCII (merged into one ^{}
# group by the run pre-pass, e.g. 2ⁿ⁻¹ → 2^{n-1})
_SUP_TO_ASCII = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "ᵃ": "a", "ᵇ": "b", "ᶜ": "c", "ᵈ": "d", "ᵉ": "e", "ᶠ": "f",
    "ᵍ": "g", "ʰ": "h", "ⁱ": "i", "ʲ": "j", "ᵏ": "k", "ˡ": "l",
    "ᵐ": "m", "ⁿ": "n", "ᵒ": "o", "ᵖ": "p", "ʳ": "r", "ˢ": "s",
    "ᵗ": "t", "ᵘ": "u", "ᵛ": "v", "ʷ": "w", "ˣ": "x", "ʸ": "y",
    "ᶻ": "z",
    "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(", "⁾": ")",
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


def _fix_caret_parens(text: str) -> str:
    """Replace ``^(balanced expr)`` with ``^{balanced expr}``.

    LLMs often write ``e^(iπ)`` / ``q^(n-1)``; a bare ``^`` followed by
    ``(`` makes LaTeX raise the ``(`` as the superscript.  This scans for
    ``^`` followed by ``(`` and finds the matching close paren by depth
    counting (nested parens supported).
    """
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "^" and i + 1 < n and text[i + 1] == "(":
            depth = 1
            j = i + 2
            while j < n and depth > 0:
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                if depth == 0:
                    break
                j += 1
            if depth == 0 and j < n:
                result.append("^{" + text[i + 2 : j] + "}")
                i = j + 1
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


def _convert_math_segment(seg: str) -> str:
    """Convert a raw math segment (no Chinese) to LaTeX math-mode content.

    Handles symbol replacement, sqrt{} fixing, S△ABC → S_{\\triangle ABC},
    simple fractions a/b → \\frac{a}{b}, minus-sign placement for negative
    fractions, redundant-paren stripping, and cleanup of extra spaces.
    """
    out = seg
    # ---- Pre-pass: Unicode sub/superscript runs ----
    # aₙ₊₁ → a_{n+1}, 2ⁿ⁻¹ → 2^{n-1}, x₁x₂ → x_{1}x_{2}; consecutive
    # same-class glyphs merge into ONE braced group (never ^a^b, which is
    # invalid LaTeX).
    def _sub_run(m):
        return "_{" + "".join(_SUB_TO_ASCII[c] for c in m.group(0)) + "}"

    def _sup_run(m):
        return "^{" + "".join(_SUP_TO_ASCII[c] for c in m.group(0)) + "}"

    out = re.sub("[" + "".join(_SUB_TO_ASCII) + "]+", _sub_run, out)
    out = re.sub("[" + "".join(_SUP_TO_ASCII) + "]+", _sup_run, out)
    # p̄ → \bar{p}  (sample-mean notation)
    out = re.sub(r"([A-Za-z])\u0304", r"\\bar{\1}", out)
    # e^(iπ) → e^{i\pi}, q^(n-1) → q^{n-1}  (bare ^( with balanced parens)
    out = _fix_caret_parens(out)
    # ---- Pre-pass: multi-char Unicode idioms before single-char mapping ----
    out = re.sub(r"⁻¹", r"^{-1}", out)                    # sin⁻¹x
    out = re.sub(r"⌒\s*([A-Z]{1,4})", r"\\overset{\\frown}{\1}", out)  # ⌒AB
    out = out.replace("（", "(").replace("）", ")")         # full-width parens
    out = out.replace("，", ",").replace("∶", ":")         # full-width punct

    for sym, cmd in _SYM_TO_LATEX.items():
        out = out.replace(sym, cmd)
    # Units: cm² → \mathrm{cm}^2 (also dm/mm/km)
    out = re.sub(r"(?<![A-Za-z])(cm|dm|mm|km|min)\^\{?(\d+)\}?", r"\\mathrm{\1}^{\2}", out)
    # \sqrt followed by (expr) → \sqrt{expr}  (match BALANCED parens, support nesting)
    out = _fix_sqrt_parens(out)
    # \sqrt followed by digit/letter → \sqrt{...}
    out = re.sub(r"\\sqrt\s+(\d+)", r"\\sqrt{\1}", out)
    out = re.sub(r"\\sqrt\s+([A-Za-z])", r"\\sqrt{\1}", out)
    # ---- Leibniz derivative notation ----
    # d/d u d² = 0  →  \frac{\mathrm{d}(d^{2})}{\mathrm{d}u} = 0
    # d/dx (x²+y²) →  \frac{\mathrm{d}(x^{2}+y^{2})}{\mathrm{d}x}
    # d²/d u² f    →  \frac{\mathrm{d}^{2}(f)}{\mathrm{d}u^{2}}
    # Must run BEFORE fraction conversion, which would otherwise turn the
    # bare "d/d" into \frac{d}{d} and shred the notation into "dud²".
    _deriv_operand = r"((?:\([^()]*\)|[^=;,。])+?)"
    out = re.sub(
        r"\bd/d\s*([a-zA-Z])\s*" + _deriv_operand + r"(?=\s*[=;,。]|\s*$)",
        lambda m: f"\\frac{{\\mathrm{{d}}({m.group(2)})}}{{\\mathrm{{d}}{m.group(1)}}}",
        out,
    )
    out = re.sub(
        r"\bd\^\{?2\}?/d\s*([a-zA-Z])\^\{?2\}?\s*" + _deriv_operand + r"(?=\s*[=;,。]|\s*$)",
        lambda m: f"\\frac{{\\mathrm{{d}}^{{2}}({m.group(2)})}}{{\\mathrm{{d}}{m.group(1)}^{{2}}}}",
        out,
    )
    # ---- Partial derivative notation ----
    # ∂f/∂x → \frac{\partial f}{\partial x};  ∂²f/∂x∂y → \frac{\partial^{2} f}{\partial x \partial y}
    # Must run BEFORE fraction conversion: the bare "f/\partial" would
    # otherwise become \partial \frac{f}{\partial} x (shredded).
    out = re.sub(
        r"\\partial\s*([A-Za-z])\s*/\s*\\partial\s*([A-Za-z])",
        r"\\frac{\\partial \1}{\\partial \2}",
        out,
    )
    out = re.sub(
        r"\\partial\s*\^\{?2\}?\s*([A-Za-z])\s*/\s*\\partial\s*([A-Za-z])\\partial\s*([A-Za-z])",
        r"\\frac{\\partial^{2} \1}{\\partial \2 \\partial \3}",
        out,
    )
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
    for fn_name in ["cos", "sin", "tan", "cot", "sec", "csc", "ln", "log", "exp",
                    "lim", "max", "min", "arcsin", "arccos", "arctan",
                    "sinh", "cosh", "tanh", "coth", "sech", "csch", "cosec",
                    "arcsinh", "arccosh", "arctanh"]:
        out = re.sub(r"\b" + fn_name + r"(?![a-zA-Z])", r"\\" + fn_name + " ", out)
    # Compact glued forms: sinx → \sin x, 2sinxcosx → 2\sin x\cos x.
    # Multi-letter names run first so "sinh" wins over "sin h" ("cosec x"
    # over "\cos ec x"); the single-letter pass then fills chains like
    # "xsinx", "sinxcosx". English words (sine, sing, sinh, tangent, ...)
    # are excluded via per-name suffix blocks.
    _glue_block = {
        "sin": r"(?:e|g|h|k|gle)",
        "cos": r"(?:h|y)",
        "tan": r"(?:h|k|g|gent)",
        "cot": r"(?:h)",
        "sec": r"(?:h|t|ond)",
        "csc": r"(?:h)",
        "log": r"(?:s)",
        "exp": r"(?:ect)",
    }
    for fn_name in ["arcsinh", "arccosh", "arctanh",
                    "arcsin", "arccos", "arctan",
                    "sinh", "cosh", "tanh", "coth", "sech", "csch", "cosec"]:
        out = re.sub(
            r"(?<![A-Za-z\\])" + fn_name + r"(?=[a-zα-ω])",
            r"\\" + fn_name + " ",
            out,
        )
    for fn_name in ["sin", "cos", "tan", "cot", "sec", "csc", "ln", "log", "exp"]:
        block = _glue_block.get(fn_name, "")
        suffix = r"(?!" + block + r"\b)" if block else ""
        out = re.sub(
            r"(?<![\\])" + fn_name + r"(?=[a-zα-ω])" + suffix,
            r"\\" + fn_name + " ",
            out,
        )
    # sqrt(number) without braces → sqrt{number}
    out = re.sub(r"\\sqrt\s*(\d+)", r"\\sqrt{\1}", out)

    # ---- Superscript / subscript normalization ----
    # x^2 → x^{2}, x_1 → x_{1}  (braced form is robust), then merge
    # consecutive groups: x²³ → x^{23}, x₁₂ → x_{12}  (never x^2^3 which is invalid).
    out = re.sub(r"\^(\d+)", r"^{\1}", out)
    out = re.sub(r"_(\d+)", r"_{\1}", out)
    for _ in range(3):
        new = re.sub(r"\^\{(\d+)\}\^\{(\d+)\}", r"^{\1\2}", out)
        new = re.sub(r"_\{(\d+)\}_\{(\d+)\}", r"_{\1\2}", new)
        if new == out:
            break
        out = new

    # ---- Fraction conversion ----
    # Convert A/B patterns to \frac{A}{B} for various token types.
    # A "frac token" is one of (tried longest-first):
    #   N\sqrt{..}^d?          (e.g. 2\sqrt{5}, 2\sqrt{5}^2)
    #   \sqrt{..}^d?           (e.g. \sqrt{35})
    #   \command               (e.g. \pi, \alpha — mapped Greek/ops)
    #   \command x             (e.g. \sin x — glued func + single var)
    #   (balanced expr)^d?     (e.g. (x_{1}+x_{2}), (a+b)^2 — one level of nesting)
    #   letters^d              (e.g. x^2, AE^2)
    #   letters_{..}           (e.g. S_{1}, x_{1})
    #   letters\d*             (e.g. AB, CE, a, 2ab)
    #   -?digits               (e.g. 35, -5)
    _exp = r"(?:\^\{?\d+\}?)?"
    _paren = r"(?:\((?:[^()]|\([^()]*\))*\))+"
    # sqrt body may itself contain braced groups (a^{2}, x_{1}), so match
    # balanced braces at one nesting level instead of [^}]+ which truncates
    # the radicand at the first inner "}".
    _sqrt_body = r"(?:[^{}]|\{[^{}]*\})*"
    _frac_token = (
        r"(?:"
        + r"\d*\\sqrt\{" + _sqrt_body + r"\}" + _exp
        + r"|\\sqrt\{" + _sqrt_body + r"\}" + _exp
        + r"|\\[A-Za-z]+\s*[A-Za-z]" + _exp
        + r"|\\[A-Za-z]+" + _exp
        + r"|" + _paren + _exp
        + r"|[A-Za-z]{1,4}(?:\^\{?\d+\}?)"
        + r"|[A-Za-z]_\{[^}]+\}"
        + r"|[A-Za-z]{1,4}\d*"
        + r"|\d+[A-Za-z]{1,4}"
        + r"|-?\d+"
        + r")"
    )
    out = re.sub(
        r"(?<![_^a-zA-Z])(" + _frac_token + r")\s*/\s*(" + _frac_token + r")",
        r"\\frac{\1}{\2}",
        out,
    )
    # Strip redundant parens that wrap a whole fraction part — only when the
    # content has no parens of its own, so (a+b)(c+d) is never damaged.
    out = re.sub(r"\\frac\{\(([^()]*)\)\}\{\(([^()]*)\)\}", r"\\frac{\1}{\2}", out)
    out = re.sub(r"\\frac\{\(([^()]*)\)\}\{([^{}]*)\}", r"\\frac{\1}{\2}", out)
    out = re.sub(r"\\frac\{([^{}]*)\}\{\(([^()]*)\)\}", r"\\frac{\1}{\2}", out)
    # Move the minus of a negative fraction in front of the whole fraction:
    # \frac{-1}{2} → -\frac{1}{2},  \frac{3}{-2} → -\frac{3}{2}.
    _neg_frac = r"\\frac\{(-?(?:[^{}]|\{[^{}]*\})*)\}\{(-?(?:[^{}]|\{[^{}]*\})*)\}"
    for _ in range(3):
        def _fix_sign(m):
            num, den = m.group(1), m.group(2)
            neg_num, neg_den = num.startswith("-"), den.startswith("-")
            if neg_num:
                num = num[1:]
            if neg_den:
                den = den[1:]
            return ("-" if neg_num != neg_den else "") + f"\\frac{{{num}}}{{{den}}}"
        new = re.sub(_neg_frac, _fix_sign, out)
        if new == out:
            break
        out = new
    # After sign extraction, \frac{-(x+1)}{2} → -\frac{x+1}{2}
    out = re.sub(r"\\frac\{\(([^()]*)\)\}\{([^{}]*)\}", r"\\frac{\1}{\2}", out)

    # Collapse multiple spaces inside math
    out = re.sub(r"  +", " ", out)
    # Remove spaces right after ^ or _ (e.g. "^ 2" → "^2")
    out = re.sub(r"\^\s+", "^", out)
    out = re.sub(r"_\s+", "_", out)
    # Clean up space before ^{\circ}
    out = re.sub(r"\s+\^", "^", out)
    # Remove space between \theta and following content if it's an operator
    out = re.sub(r"(\\theta\s+)\s", r"\1", out)
    # ---- Matrix notation: [[a,b],[c,d]] → pmatrix ----
    # LLMs write plain-text matrices; runs LAST so cells keep their already
    # converted \frac/\sqrt content.
    def _to_pmatrix(m):
        inner = m.group(1)
        rows = [r.strip() for r in inner.split("],[")]
        body = r" \\ ".join(" & ".join(c.strip() for c in r.split(",")) for r in rows)
        return r"\begin{pmatrix}" + body + r"\end{pmatrix}"

    out = re.sub(r"\[\[(.*?)\]\]", _to_pmatrix, out)
    # Dangling _ / ^ (followed by CJK, space or end — not letter/digit/brace)
    # are invalid LaTeX sub/superscripts; escape so "01_初中" text compiles.
    out = re.sub(r"(?<!\\)_" + r"(?![A-Za-z0-9{\\])", r"\\_", out)
    out = re.sub(r"(?<!\\)\^" + r"(?![A-Za-z0-9{\\])", r"\\textasciicircum{}", out)
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


def _verification_badge(status: str) -> str:
    """Return a LaTeX badge for the given verification_status value."""
    s = (status or "unknown").lower()
    if s == "true":
        return r"{\color{verifiedgreen}\checkmark}"
    if s == "false":
        return r"{\color{verifiedred}\ding{55}}"
    if s == "uncertain":
        return r"{\color{verifiedorange}\textbf{!}}"
    return r"{\color{gray}$\cdot$}"


def _verification_summary_line(proof: list[ProofStep]) -> list[str]:
    """Render a Chinese verification statistics line for the report header."""
    counts = {"true": 0, "false": 0, "uncertain": 0, "unknown": 0}
    for st in proof:
        s = (getattr(st, "verification_status", None) or "unknown").lower()
        if s in counts:
            counts[s] += 1
        else:
            # Back-compat: fall back to bool verified
            if getattr(st, "verified", False):
                counts["true"] += 1
            else:
                counts["unknown"] += 1
    return [
        r"\noindent\small 验证统计: "
        f"{counts['true']} 步已证 "
        r"{\color{verifiedgreen}\checkmark}, "
        f"{counts['uncertain']} 步存疑 "
        r"{\color{verifiedorange}\textbf{!}}, "
        f"{counts['false']} 步错误 "
        r"{\color{verifiedred}\ding{55}}, "
        f"{counts['unknown']} 步未验证."
    ]


def _proof_block(proof: list[ProofStep]) -> list[str]:
    """Render proof steps in formal style.

    Each step is a numbered item. The statement is rendered inline (mixed
    text+math). The reason follows on the next line in smaller italic text.
    A small verification badge (✓/✗/!/·) is shown next to each step based on
    the step's ``verification_status`` (back-compat with legacy bool
    ``verified`` field).
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
    # Statistics line
    lines += _verification_summary_line(
        [st for st, _ in clean_steps] if clean_steps else proof
    )
    lines.append("")
    if not clean_steps:
        lines.append(r"\textit{（未生成解答步骤）}")
        return lines
    # 使用圈号 ①②③ 作为步骤编号（小题用括号 (1)(2) 加以区分）
    lines.append(
        r"\begin{enumerate}[label={\small\textcircled{\arabic*}}, leftmargin=2.8em, itemsep=8pt, topsep=4pt]"
    )
    for st, cleaned in clean_steps:
        badge = _verification_badge(getattr(st, "verification_status", None))
        stmt = _format_inline(cleaned)
        reason = _format_inline(_clean_statement(st.reason)) if st.reason else ""
        vr = _format_inline(_clean_statement(getattr(st, "verifier_reason", "") or ""))
        lines.append(rf"\item {badge}\enspace {stmt}")
        if reason:
            lines.append(
                rf"\par\noindent\hspace*{{1.4em}}{{\small\textit{{理由：}}{reason}}}"
            )
        if vr and vr != reason:
            color = "verifiedred" if (getattr(st, "verification_status", None) == "false") else (
                "verifiedorange" if (getattr(st, "verification_status", None) == "uncertain") else "gray"
            )
            lines.append(
                rf"\par\noindent\hspace*{{1.4em}}{{\small\textcolor{{{color}}}{{\textit{{验证说明：}}{vr}}}}}"
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
        r"\usepackage{pifont}",
        r"\definecolor{verifiedgreen}{RGB}{0,128,0}",
        r"\definecolor{verifiedred}{RGB}{200,0,0}",
        r"\definecolor{verifiedorange}{RGB}{220,120,0}",
        r"\usepackage{tikz}",
        r"\usepackage{amsmath, amssymb, amsthm}",
        r"\usepackage{booktabs}",
        r"\usepackage{setspace}",
        r"\usepackage{enumitem}",
        r"\usepackage{tcolorbox}",
        r"\tcbuselibrary{skins}",
        r"\usepackage{titlesec}",
        r"\titleformat{\section}{\Large\bfseries}{}{0em}{}",
        r"\titlespacing*{\section}{0pt}{1.4em}{0.7em}",
        r"\usepackage{fancyhdr}",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        r"\fancyfoot[C]{\small 第 \thepage\ 页}",
        r"\renewcommand{\headrulewidth}{0pt}",
        r"\allowdisplaybreaks",
        r"\usepackage[colorlinks=true, linkcolor=blue!50!black, urlcolor=blue!60!black, bookmarksnumbered=true]{hyperref}",
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
    y_up: bool = False,
    axes: bool = False,
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
        tikz = graph_to_tikz(graph, y_up=y_up, axes=axes)
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
    if reasoning_summary or reasoning_trace:
        lines += _reasoning_appendix(reasoning_summary, reasoning_trace, key_equations)

    lines += ["", r"\end{document}"]
    return "\n".join(lines) + "\n"


def _reasoning_appendix(
    reasoning_summary: str,
    reasoning_trace: list[str],
    key_equations: list[str] | None = None,  # noqa: ARG001 - no longer rendered
) -> list[str]:
    """Render a '解题思路' appendix.

    The section is written by the LLM itself (in its final JSON):
    ``summary`` → 解题思路 (the model's own reasoning narrative).

    Falls back to ``reasoning_trace`` entries only when ``summary`` is empty
    (legacy / fallback path). Tool-call outputs are never dumped here.
    """
    lines = [
        r"\section*{五、解题思路}",
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

    return lines


# =====================================================================================
# Multi-sub-question mode (one big problem, parts (1)(2)(3), single PDF)
# =====================================================================================
def multi_question_to_latex(
    problem_text: str,
    sub_questions: list[dict],
    graph: GeometryGraph | None = None,
    title: str = "几何题解答报告",
    y_up: bool = False,
    axes: bool = False,
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
        tikz = graph_to_tikz(graph, y_up=y_up, axes=axes)
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
    if all_summary or all_trace:
        lines += _reasoning_appendix(
            "；".join(all_summary), all_trace, all_key_eqs,
        )

    lines += ["", r"\end{document}"]
    return "\n".join(lines) + "\n"


__all__ = ["solution_to_latex", "multi_question_to_latex"]
