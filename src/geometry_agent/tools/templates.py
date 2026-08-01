"""Reusable code-snippet templates for the LLM.

The reasoning agent can ask :func:`get_template` for a starting snippet
covering common geometry computations. Templates are deliberately short and
*executable as-is* inside :class:`CodeExecutor` — they only use names that
are pre-injected (``math``, ``np``, ``sp``, ``fractions``, ``decimal``,
``statistics``).

Keyword matching is fuzzy (substring on lowercased task text) so the LLM
does not need to phrase the request precisely.
"""

from __future__ import annotations

_TEMPLATES: dict[str, str] = {
    "解方程": (
        "# 解方程 / 方程组 (symbolic)\n"
        "import sympy as sp\n"
        "x, y = sp.symbols('x y')\n"
        "eqs = [sp.Eq(x + y, 5), sp.Eq(x - y, 1)]\n"
        "sol = sp.solve(eqs, [x, y])\n"
        "print('solution =', sol)\n"
    ),
    "solve_equation": (
        "# Solve a system of equations symbolically.\n"
        "import sympy as sp\n"
        "x, y = sp.symbols('x y')\n"
        "eqs = [sp.Eq(x + y, 5), sp.Eq(x - y, 1)]\n"
        "sol = sp.solve(eqs, [x, y])\n"
        "print('solution =', sol)\n"
    ),
    "求距离": (
        "# 求两点距离 (coordinate distance)\n"
        "import math\n"
        "A = (0.0, 0.0)\n"
        "B = (3.0, 4.0)\n"
        "d = math.hypot(B[0]-A[0], B[1]-A[1])\n"
        "print('distance =', d)\n"
    ),
    "distance": (
        "# Distance between two points.\n"
        "import math\n"
        "A = (0.0, 0.0)\n"
        "B = (3.0, 4.0)\n"
        "d = math.hypot(B[0]-A[0], B[1]-A[1])\n"
        "print('distance =', d)\n"
    ),
    "求角度": (
        "# 求夹角 (angle between two vectors, in degrees)\n"
        "import math\n"
        "u = (1.0, 0.0)\n"
        "v = (1.0, 1.0)\n"
        "dot = u[0]*v[0] + u[1]*v[1]\n"
        "nu = math.hypot(*u); nv = math.hypot(*v)\n"
        "angle_deg = math.degrees(math.acos(dot/(nu*nv)))\n"
        "print('angle_deg =', angle_deg)\n"
    ),
    "angle": (
        "# Angle between two vectors (degrees).\n"
        "import math\n"
        "u = (1.0, 0.0)\n"
        "v = (1.0, 1.0)\n"
        "dot = u[0]*v[0] + u[1]*v[1]\n"
        "nu = math.hypot(*u); nv = math.hypot(*v)\n"
        "angle_deg = math.degrees(math.acos(dot/(nu*nv)))\n"
        "print('angle_deg =', angle_deg)\n"
    ),
    "验证共线": (
        "# 验证三点共线 (collinearity via determinant)\n"
        "import sympy as sp\n"
        "A = sp.Point(0, 0)\n"
        "B = sp.Point(1, 1)\n"
        "C = sp.Point(2, 2)\n"
        "area = sp.Triangle(A, B, C).area\n"
        "print('collinear' if area == 0 else 'not collinear')\n"
    ),
    "collinear": (
        "# Collinearity check (triangle area == 0).\n"
        "import sympy as sp\n"
        "A = sp.Point(0, 0)\n"
        "B = sp.Point(1, 1)\n"
        "C = sp.Point(2, 2)\n"
        "area = sp.Triangle(A, B, C).area\n"
        "print('collinear' if area == 0 else 'not collinear')\n"
    ),
    "验证垂直": (
        "# 验证两线段垂直 (perpendicular via dot product == 0)\n"
        "import sympy as sp\n"
        "A, B = sp.Point(0,0), sp.Point(1,1)\n"
        "C, D = sp.Point(1,0), sp.Point(0,1)\n"
        "v1 = B - A\n"
        "v2 = D - C\n"
        "print('perpendicular' if v1.dot(v2) == 0 else 'not perpendicular')\n"
    ),
    "perpendicular": (
        "# Perpendicular check (dot product == 0).\n"
        "import sympy as sp\n"
        "A, B = sp.Point(0,0), sp.Point(1,1)\n"
        "C, D = sp.Point(1,0), sp.Point(0,1)\n"
        "v1 = B - A\n"
        "v2 = D - C\n"
        "print('perpendicular' if v1.dot(v2) == 0 else 'not perpendicular')\n"
    ),
    "复数法": (
        "# 复数法验证 (complex-number method)\n"
        "import sympy as sp\n"
        "# Place points as complex numbers; collinear iff (z1-z2)/(z1-z3)\n"
        "# is real (imag part == 0).\n"
        "z1 = sp.Rational(0)\n"
        "z2 = 1 + sp.I\n"
        "z3 = 2 + 2*sp.I\n"
        "ratio = (z1 - z2) / (z1 - z3)\n"
        "print('ratio =', sp.simplify(ratio))\n"
        "print('collinear' if sp.im(sp.simplify(ratio)) == 0 else 'not collinear')\n"
    ),
    "complex_method": (
        "# Complex-number method template.\n"
        "import sympy as sp\n"
        "z1 = sp.Rational(0)\n"
        "z2 = 1 + sp.I\n"
        "z3 = 2 + 2*sp.I\n"
        "ratio = (z1 - z2) / (z1 - z3)\n"
        "print('ratio =', sp.simplify(ratio))\n"
        "print('collinear' if sp.im(sp.simplify(ratio)) == 0 else 'not collinear')\n"
    ),
    "射影": (
        "# 射影法: 交比 (cross-ratio) of four collinear points parameterised\n"
        "# along the x-axis.\n"
        "import sympy as sp\n"
        "A, B, C, D = 0, 1, 2, 3\n"
        "cr = ((C-A)/(C-B)) / ((D-A)/(D-B))\n"
        "print('cross_ratio =', cr)\n"
    ),
    "cross_ratio": (
        "# Cross-ratio of four collinear points.\n"
        "import sympy as sp\n"
        "A, B, C, D = 0, 1, 2, 3\n"
        "cr = ((C-A)/(C-B)) / ((D-A)/(D-B))\n"
        "print('cross_ratio =', cr)\n"
    ),
}

# Ordered (keyword, template) list for fuzzy matching. Longest keywords first
# so that "复数法" wins over a generic "复数" substring match.
_ORDERED_KEYS = sorted(_TEMPLATES.keys(), key=len, reverse=True)


def get_template(task: str) -> str | None:
    """Return a code template for ``task`` or ``None`` if no match.

    Matching is case-insensitive substring on the task string. Both Chinese
    and English keywords are supported.
    """
    if not task:
        return None
    needle = task.lower()
    for key in _ORDERED_KEYS:
        if key.lower() in needle:
            return _TEMPLATES[key]
    return None


def all_templates() -> dict[str, str]:
    """Return a copy of the full template table (for introspection / docs)."""
    return dict(_TEMPLATES)


__all__ = ["get_template", "all_templates"]
