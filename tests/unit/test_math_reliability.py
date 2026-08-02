"""Permanent reliability regression suite: junior high -> university.

Every case is asserted against its EXACT converted LaTeX output.
Exact-string assertions catch structural damage (e.g. the old
"\partial \\frac{f}{\\partial} x" shredding of ∂f/∂x) that a
Unicode-leftover scan cannot.
"""

from geometry_agent.report import _convert_math_segment, _format_inline


CASES: list[tuple[str, str]] = [
    ('1/2 + 1/3 = 5/6', '\\frac{1}{2} + \\frac{1}{3} = \\frac{5}{6}'),
    ('x = (-b±√(b²-4ac))/(2a)', 'x = \\frac{-b\\pm \\sqrt{b^{2}-4ac}}{2a}'),
    ('a/b = c/d', '\\frac{a}{b} = \\frac{c}{d}'),
    ('2/3 × 3/4 = 1/2', '\\frac{2}{3} \\times \\frac{3}{4} = \\frac{1}{2}'),
    ('x² = 9，x = ±3', 'x^{2} = 9,x = \\pm 3'),
    ('√18 = 3√2', '\\sqrt{18} = 3\\sqrt{2}'),
    ('√(a²+b²)', '\\sqrt{a^{2}+b^{2}}'),
    ('1/√2 = √2/2', '\\frac{1}{\\sqrt{2}} = \\frac{\\sqrt{2}}{2}'),
    ('∠A + ∠B + ∠C = 180°', '\\angle A + \\angle B + \\angle C = 180^{\\circ}'),
    ('∠A = 90°', '\\angle A = 90^{\\circ}'),
    ('tanA = 3/4', 'tanA = \\frac{3}{4}'),
    ('sin30° = 1/2', '\\sin 30^{\\circ} = \\frac{1}{2}'),
    ('cos60° = 1/2', '\\cos 60^{\\circ} = \\frac{1}{2}'),
    ('S△ABC = 1/2 × AB × AC', 'S_{\\triangle ABC} = \\frac{1}{2} \\times AB \\times AC'),
    ('S△ABC/S△DEF = (AB/DE)²', '\\frac{S_{\\triangle ABC}}{S_{\\triangle DEF}} = (\\frac{AB}{DE})^{2}'),
    ('AB² + AC² = BC²', 'AB^{2} + AC^{2} = BC^{2}'),
    ('AB = √(AC² + BC²)', 'AB = \\sqrt{AC^{2} + BC^{2}}'),
    ('△ABC ≌ △DEF', '\\triangle ABC \\cong \\triangle DEF'),
    ('△ABC ∽ △DEF', '\\triangle ABC \\sim \\triangle DEF'),
    ('AB // CD', 'AB // CD'),
    ('AB ⊥ CD', 'AB \\perp CD'),
    ('弧AB = 弧CD', '弧AB = 弧CD'),
    ('⌒AB = ⌒CD', '\\overset{\\frown}{AB} = \\overset{\\frown}{CD}'),
    ('πr²', '\\pi r^{2}'),
    ('2πr', '2\\pi r'),
    ('4/3πr³', '\\frac{4}{3}\\pi r^{3}'),
    ('S = πr²', 'S = \\pi r^{2}'),
    ('V = 1/3πr²h', 'V = \\frac{1}{3}\\pi r^{2}h'),
    ('百分比 30%', '百分比 30%'),
    ('a:b = 2:3', 'a:b = 2:3'),
    ('3x + 2y = 12', '3x + 2y = 12'),
    ('x = 2/3 y', 'x = \\frac{2}{3} y'),
    ('f(x) = x² + 2x + 1 = (x+1)²', 'f(x) = x^{2} + 2x + 1 = (x+1)^{2}'),
    ('y = sin(x + π/6)', 'y = \\sin (x + \\frac{\\pi}{6})'),
    ('sin²x + cos²x = 1', '\\sin^{2}x + \\cos^{2}x = 1'),
    ('sin2α = 2sinαcosα', '\\sin 2\\alpha = 2sin\\alpha \\cos \\alpha'),
    ('tan(α + β) = (tanα + tanβ)/(1 - tanαtanβ)', '\\tan (\\alpha + \\beta ) = \\frac{\\tan \\alpha + \\tan \\beta }{1 - \\tan \\alpha \\tan \\beta }'),
    ('y = log₂(x+1)', 'y = \\log _{2}(x+1)'),
    ('y = ln x', 'y = \\ln x'),
    ('e^x > 0', 'e^x > 0'),
    ('2^x = 8', '2^x = 8'),
    ('a_n = a₁ + (n-1)d', 'a_n = a_{1} + (n-1)d'),
    ('S_n = n(a₁ + a_n)/2', 'S_n = n(a_{1} + a_n)/2'),
    ('a_n = a₁q^(n-1)', 'a_n = a_{1}q^{n-1}'),
    ('S_n = a₁(1-q^n)/(1-q)', 'S_n = a_{1}\\frac{1-q^n}{1-q}'),
    ('x² - 5x + 6 < 0', 'x^{2} - 5x + 6 < 0'),
    ('a + b ≥ 2√(ab)', 'a + b \\ge 2\\sqrt{ab}'),
    ('|x - 3| < 2', '|x - 3| < 2'),
    ('→a · →b = |→a||→b|cosθ', '\\to a \\cdot \\to b = |\\to a||\\to b|\\cos \\theta'),
    ('→AB = →OB - →OA', '\\to AB = \\to OB - \\to OA'),
    ('a∥b', 'a\\parallel b'),
    ('d = |Ax₀ + By₀ + C|/√(A²+B²)', 'd = |Ax_{0} + By_{0} + C|/\\sqrt{A^{2}+B^{2}}'),
    ('k = (y₂ - y₁)/(x₂ - x₁)', 'k = \\frac{y_{2} - y_{1}}{x_{2} - x_{1}}'),
    ('y = kx + b', 'y = kx + b'),
    ('x²/a² + y²/b² = 1', '\\frac{x^{2}}{a^{2}} + \\frac{y^{2}}{b^{2}} = 1'),
    ('y² = 2px', 'y^{2} = 2px'),
    ('x² + y² = r²', 'x^{2} + y^{2} = r^{2}'),
    ('(x-a)² + (y-b)² = r²', '(x-a)^{2} + (y-b)^{2} = r^{2}'),
    ('C(n, 2) = n(n-1)/2', 'C(n, 2) = n(n-1)/2'),
    ('P(A|B) = P(AB)/P(B)', 'P(A|B) = P(AB)/P(B)'),
    ('P(A∪B) = P(A) + P(B) - P(A∩B)', 'P(A\\cup B) = P(A) + P(B) - P(A\\cap B)'),
    ("f'(x) = 2x", "f'(x) = 2x"),
    ('d/dx (x²) = 2x', '\\frac{\\mathrm{d}((x^{2}))}{\\mathrm{d}x} = 2x'),
    ('dy/dx = 2x', '\\frac{dy}{dx} = 2x'),
    ('d²y/dx² = 2', 'd^{2}\\frac{y}{dx^{2}} = 2'),
    ('lim_{x→0} sinx/x = 1', '\\lim _{x\\to 0} \\frac{\\sin x}{x} = 1'),
    ('lim_{n→∞} (1 + 1/n)^n = e', '\\lim _{n\\to \\infty } (1 + \\frac{1}{n})^n = e'),
    ('∫x²dx = x³/3 + C', '\\int x^{2}dx = \\frac{x^{3}}{3} + C'),
    ('∫₀¹ x²dx = 1/3', '\\int _{0}^{1} x^{2}dx = \\frac{1}{3}'),
    ('∫(1/x)dx = ln|x| + C', '\\int (\\frac{1}{x})dx = \\ln |x| + C'),
    ('∫∫_D f(x,y)dxdy', '\\int \\int _D f(x,y)dxdy'),
    ('Σ_{i=1}^n i = n(n+1)/2', '\\Sigma _{i=1}^n i = n(n+1)/2'),
    ('Σ_{i=1}^n i² = n(n+1)(2n+1)/6', '\\Sigma _{i=1}^n i^{2} = n(n+1)\\frac{2n+1}{6}'),
    ('|A| = ad - bc', '|A| = ad - bc'),
    ('det(A) ≠ 0', 'det(A) \\neq 0'),
    ('A⁻¹ = (1/|A|)A*', 'A^{-1} = (1/|A|)A*'),
    ('∂f/∂x', '\\frac{\\partial f}{\\partial x}'),
    ('∂²f/∂x∂y', '\\frac{\\partial^{2} f}{\\partial x \\partial y}'),
    ("f'(x) = lim_{h→0} (f(x+h) - f(x))/h", "f'(x) = \\lim _{h\\to 0} \\frac{(f(x+h) - f(x))}{h}"),
    ('e^(iπ) + 1 = 0', 'e^{i\\pi } + 1 = 0'),
    ('∇f = (∂f/∂x, ∂f/∂y)', '\\nabla f = (\\frac{\\partial f}{\\partial x}, \\frac{\\partial f}{\\partial y})'),
    ('Γ(n+1) = n!', '\\Gamma (n+1) = n!'),
    ('C(n, k) = n!/(k!(n-k)!)', 'C(n, k) = n!/(k!(n-k)!)'),
    ('A = {x | x² < 4}', 'A = {x | x^{2} < 4}'),
    ('A ∩ B = ∅', 'A \\cap B = \\varnothing'),
    ('x ∈ R', 'x \\in R'),
    ('α + β = γ', '\\alpha + \\beta = \\gamma'),
    ('ω = 2π/T', '\\omega = 2\\frac{\\pi}{T}'),
    ('λ = c/f', '\\lambda = \\frac{c}{f}'),
    ('μ = 3.5', '\\mu = 3.5'),
    ('σ² = E[(X-μ)²]', '\\sigma^{2} = E[(X-\\mu )^{2}]'),
    # Unicode letter/digit sub-superscript runs (from real exams)
    ('aₙ = 2ⁿ⁻¹', 'a_{n} = 2^{n-1}'),
    ('Sₙ = 2ⁿ − 1', 'S_{n} = 2^{n} - 1'),
    ('bₖ₋₁ = bₖ − 2k', 'b_{k-1} = b_{k} - 2k'),
    ('aₙ₊₁ = aₙ + d', 'a_{n+1} = a_{n} + d'),
    ('Tₙ = (2n−1)·3ⁿ + 1', 'T_{n} = (2n-1)\\cdot 3^{n} + 1'),
    ('x₁x₂ < 1', 'x_{1}x_{2} < 1'),
    ('x₁² + y₁² = r²', 'x_{1}^{2} + y_{1}^{2} = r^{2}'),
    ('q^(n-1) = aₙ/a₁', 'q^{n-1} = \\frac{a_{n}}{a_{1}}'),
    # U+2212 minus, combining macron, matrix notation
    ('A = [[1,2],[3,4]]', 'A = \\begin{pmatrix}1 & 2 \\\\ 3 & 4\\end{pmatrix}'),
    ('A⁻¹ = [[1,−1],[−1,2]]', 'A^{-1} = \\begin{pmatrix}1 & -1 \\\\ -1 & 2\\end{pmatrix}'),
    ('p̄ = 0.5', '\\bar{p} = 0.5'),
]


def test_reliability_corpus_exact_conversion():
    for inp, expected in CASES:
        assert _convert_math_segment(inp) == expected, inp


def test_reliability_corpus_no_unicode_leftovers():
    # belt-and-braces: even if expected strings drift, no raw Unicode
    # math symbols may leak into the LaTeX output.
    import re
    bad = re.compile(r'[√∠△∥≌∽⌒°±×÷≥≤≠→←∞∫∑∏∂∇∈∉∅∩∪²³¹⁰⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉αβγδεθλμσπωₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ₊₋₌₍₎ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ⁺⁼⁽⁾\u0304−]')
    for inp, out in CASES:
        assert not bad.search(out), (inp, out)


def test_reliability_corpus_no_double_backslash_frac():
    # pmatrix row separators legitimately emit "\\ "; a double backslash
    # glued to a command name means a shredded \frac.
    import re
    for inp, out in CASES:
        assert r'\\frac' not in out and re.search(r'\\\\(?! )', out) is None, (inp, out)


# --- Mixed Chinese+math segments (real-exam regressions) ---
#
# The pure-math CASES above run through _convert_math_segment directly, which
# handled ∇/λ all along.  The actual failures came from _format_inline's
# character-set splitter: ∇ was missing from _MATH_GEO and λ/ο from
# _MATH_GREEK, so in mixed text like "求梯度 ∇f" the symbol stayed in text
# mode and leaked raw Unicode into the PDF (rendered by the CJK font).
MIXED_CASES: list[str] = [
    '求梯度 ∇f，其中 f(x,y,z)=x²+y²+z²',
    '答案：λ₁=2，λ₂=3，A的特征值为 λ₁、λ₂',
    '设 θ∈(0,π/2)，tanθ=√3',
    'C为椭圆上一点，∠ACB=90°，S△ABC=2√3',
    '前n项和为Sₙ，Sₙ = 2ⁿ − 1，则 aₙ = 2ⁿ⁻¹',
]


def test_reliability_mixed_segments_no_unicode_leftovers():
    import re
    bad = re.compile(r'[√∠△∥≌∽⌒°±×÷≥≤≠→←∞∫∑∏∂∇∈∉∅∩∪²³¹⁰⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉αβγδεθλμσπωₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ₊₋₌₍₎ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ⁺⁼⁽⁾\u0304−]')
    for inp in MIXED_CASES:
        out = _format_inline(inp)
        assert not bad.search(out), (inp, out)


def test_reliability_mixed_segments_converted():
    # ∇ must land inside a math segment as \nabla, not linger as raw text.
    assert r'\nabla ' in _format_inline('求梯度 ∇f，其中 f(x,y,z)=x²+y²+z²')
    # λ must convert to \lambda in the answer text (λ₁ was the reported leak).
    assert r'\lambda ' in _format_inline('答案：λ₁=2，λ₂=3，A的特征值为 λ₁、λ₂')
