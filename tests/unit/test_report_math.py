"""Unit tests for the v2 math-rendering engine in geometry_agent.report.

Covers the user-facing correctness rules:
  - negative fraction minus sign goes in front of the whole fraction
  - parentheses: never dropped when needed, never added when redundant
  - superscripts / subscripts always correct (including merged ²³ / ₁₂)
  - every math symbol maps to valid LaTeX
"""

from __future__ import annotations

from geometry_agent.report import _convert_math_segment, _format_inline


# --------------------------------------------------------------------------- #
# Negative fractions: minus sign in front of the whole fraction
# --------------------------------------------------------------------------- #
def test_negative_fraction_minus_in_front():
    assert _convert_math_segment("-3/4") == r"-\frac{3}{4}"
    assert _convert_math_segment("x=-3/4") == r"x=-\frac{3}{4}"
    assert _convert_math_segment("F(0, -3/4)") == r"F(0, -\frac{3}{4})"
    assert _convert_math_segment("x=-1/2, y=3/4") == r"x=-\frac{1}{2}, y=\frac{3}{4}"


def test_negative_fraction_denominator_minus():
    assert _convert_math_segment("3/-2") == r"-\frac{3}{2}"


def test_negative_fraction_minus_cancels():
    assert _convert_math_segment("(-1)/(-2)") == r"\frac{1}{2}"


def test_negative_fraction_with_sqrt_and_parens():
    assert _convert_math_segment("AB=(-1+√5)/2") == r"AB=-\frac{1+\sqrt{5}}{2}"
    assert _convert_math_segment("-(x+1)/2") == r"-\frac{x+1}{2}"
    assert _convert_math_segment("x=(2√5)/(-3)") == r"x=-\frac{2\sqrt{5}}{3}"


# --------------------------------------------------------------------------- #
# Parentheses policy
# --------------------------------------------------------------------------- #
def test_redundant_parens_stripped_in_fraction():
    assert _convert_math_segment("(a+b)/(c+d)") == r"\frac{a+b}{c+d}"
    assert _convert_math_segment("(x+1)/x") == r"\frac{x+1}{x}"


def test_needed_parens_kept():
    # exponent needs parens
    assert _convert_math_segment("(x-1)^2/4") == r"\frac{(x-1)^{2}}{4}"
    # adjacent groups are not damaged
    assert _convert_math_segment("(a+b)(c+d)/2") == r"\frac{(a+b)(c+d)}{2}"
    assert _convert_math_segment("(x+1)(x-1)/4") == r"\frac{(x+1)(x-1)}{4}"
    # nested parens are not stripped (safe conservative rule)
    assert _convert_math_segment("((a+b))/c") == r"\frac{((a+b))}{c}"


# --------------------------------------------------------------------------- #
# Superscripts / subscripts
# --------------------------------------------------------------------------- #
def test_superscript_unicode_mapping():
    assert _convert_math_segment("BD²=9") == r"BD^{2}=9"
    assert _convert_math_segment("x¹") == r"x^{1}"   # ¹ was previously unmapped
    assert _convert_math_segment("x⁴+y⁵") == r"x^{4}+y^{5}"


def test_consecutive_superscripts_merged():
    # x²³ must become x^{23}, never the invalid x^2^3
    assert _convert_math_segment("x²³") == r"x^{23}"
    assert _convert_math_segment("x^2^3") == r"x^{23}"


def test_consecutive_subscripts_merged():
    assert _convert_math_segment("x₁₂") == r"x_{12}"
    assert _convert_math_segment("x_1_2") == r"x_{12}"


def test_units_rendered_upright():
    assert _convert_math_segment("cm²") == r"\mathrm{cm}^{2}"
    assert _convert_math_segment("面积=3cm²") == r"面积=3\mathrm{cm}^{2}"


def test_ascii_superscripts_in_fraction():
    assert _convert_math_segment("x^2/4 + y^2/3 = 1") == \
        r"\frac{x^{2}}{4} + \frac{y^{2}}{3} = 1"


# --------------------------------------------------------------------------- #
# Symbol coverage — every Unicode math symbol must map to LaTeX
# --------------------------------------------------------------------------- #
def test_symbols_map_to_latex():
    cases = {
        "α+β": r"\alpha +\beta",
        "x∝y": r"x\propto y",
        "a±b": r"a\pm b",
        "A⊂B": r"A\subset B",
        "x∉A": r"x\notin A",
        "p⇒q": r"p\Rightarrow q",
        "∠A⊥BC": r"\angle A\perp BC",
        "⊙O": r"\odot O",
        "S△ABC": r"S_{\triangle ABC}",
        "∟ABC": r"\lrcorner ABC",
        "θ=30°": r"\theta =30^{\circ}",
        "ε>0": r"\varepsilon >0",
    }
    for raw, expected in cases.items():
        assert _convert_math_segment(raw) == expected, f"{raw!r} -> {_convert_math_segment(raw)}"


def test_arc_symbol_with_letters():
    assert _convert_math_segment("⌒AB=60°") == r"\overset{\frown}{AB}=60^{\circ}"


def test_inverse_trig_notation():
    assert _convert_math_segment("sin⁻¹x") == r"\sin^{-1}x"


def test_fullwidth_parens_normalized():
    assert _convert_math_segment("（1，2）") == r"(1,2)"


def test_sqrt_with_parens_and_fraction():
    assert _convert_math_segment("√(x²+y²)") == r"\sqrt{x^{2}+y^{2}}"
    assert _convert_math_segment("2√5/3") == r"\frac{2\sqrt{5}}{3}"
    assert _convert_math_segment("1/(2√5)") == r"\frac{1}{2\sqrt{5}}"


# --------------------------------------------------------------------------- #
# Inline formatting end-to-end (mixed Chinese + math)
# --------------------------------------------------------------------------- #
def test_format_inline_mixed_text():
    out = _format_inline("求证：直线 BC 恒过定点 F(0, -3/4)，且 ∠BAC=90°。")
    assert r"$BC$" in out
    assert r"F(0, -\frac{3}{4})" in out
    assert r"$\angle BAC=90^{\circ}$" in out


def test_format_inline_negative_fraction_in_text():
    out = _format_inline("斜率 k = -1/2")
    assert r"k = -\frac{1}{2}" in out


def test_format_inline_keeps_chinese_text_mode():
    out = _format_inline("因为 AB 平行 CD，所以 ∠A=∠B")
    assert "因为" in out
    assert "平行" in out
    assert r"$\angle A=\angle B$" in out
