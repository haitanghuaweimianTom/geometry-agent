"""General-purpose symbolic algebra tools for the reasoning loop.

These tools sit between the polynomial/conic/function specialists and the
free-form ``execute_code``: they cover the everyday operations the LLM needs
when solving mixed geometry/algebra problems (equation solving, identity
verification, coordinate formulas, matrices).

Each tool takes structured string arguments (never raw code), returns a
JSON-serializable dict with ``success`` / ``result`` / ``steps``, and mirrors
the conventions of :mod:`geometry_agent.tools.polynomial_tools`.
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp

from .polynomial_tools import _parse_expr, _err


def _pt(s: str) -> tuple[sp.Symbol, sp.Symbol]:
    """Parse a 'x,y' / 'x1,y1' / '[x, y]' / '（x，y）' point string."""
    s = s.strip().replace("（", "(").replace("）", ")").strip("()[]")
    parts = [p.strip() for p in re.split(r"[,，\s]+", s) if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"无法解析点坐标: {s!r} (需要 x,y 或 [x, y])")
    return sp.sympify(parts[0]), sp.sympify(parts[1])


# =====================================================================================
# Tool: solve_equation — 解方程 (任意类型)
# =====================================================================================
def solve_equation(
    equation: str,
    variable: str = "x",
    domain: str = "R",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """解方程 (多项式/三角/指数/对数等任意类型).

    Args:
        equation: 方程左端 = 0, 如 "x**2 - 4" 或 "sin(x) - 1/2"
        variable: 未知量
        domain: "R" 实数 / "(0, oo)" 开区间 / "[a, b]" 闭区间 (可选过滤)
        variables: 其他符号 (可选, 自动推断)

    Returns:
        {"success": True, "result": [解列表], "steps": "..."}
    """
    try:
        expr, _ = _parse_expr(equation, variables or [variable])
        sym = sp.Symbol(variable)
        sols = sp.solve(sp.Eq(expr, 0), sym)
        steps = f"解方程 {equation} = 0:\n"
        if not sols:
            steps += "  无解或 SymPy 无法解析求解"
            return {"success": True, "result": [], "steps": steps}

        filtered = []
        for s in sols:
            real = s.is_real
            if real is None:
                real = s.atoms(sp.I) == set()
            if domain in ("R", ""):
                if real:
                    filtered.append(s)
            else:
                # numeric range filter like (0, oo) / [0, 1]
                try:
                    v = float(s)
                    if _in_domain(v, domain):
                        filtered.append(s)
                except (TypeError, ValueError):
                    filtered.append(s)
        steps += "  解: " + ", ".join(str(s) for s in filtered)
        return {"success": True, "result": [str(s) for s in filtered],
                "result_latex": sp.latex(list(filtered)), "steps": steps}
    except Exception as e:
        return _err(f"解方程失败: {e}")


def _in_domain(v: float, domain: str) -> bool:
    d = domain.replace(" ", "")
    lo, hi = None, None
    lo_open = hi_open = True
    if d.startswith("("):
        lo_open = True
    elif d.startswith("["):
        lo_open = False
    if d.endswith(")"):
        hi_open = True
    elif d.endswith("]"):
        hi_open = False
    inner = d.strip("()[]")
    if "," in inner:
        a, b = inner.split(",")
        if a not in ("-oo", "-inf", ""):
            lo = float(a)
        if b not in ("oo", "inf", "+oo", ""):
            hi = float(b)
    ok = True
    if lo is not None:
        ok = ok and (v > lo if lo_open else v >= lo)
    if hi is not None:
        ok = ok and (v < hi if hi_open else v <= hi)
    return ok


# =====================================================================================
# Tool: solve_inequality — 解不等式
# =====================================================================================
def solve_inequality(
    inequality: str,
    variable: str = "x",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """解一元不等式, 返回解集区间.

    Args:
        inequality: 不等式字符串, 如 "x**2 - 4 > 0" 或 "x**2 - 4*x + 3 <= 0"
        variable: 变量名

    Returns:
        {"success": True, "result": ["(-oo, -2) U (2, oo)"], "steps": "..."}
    """
    try:
        expr, _ = _parse_expr(inequality, variables or [variable])
        sym = sp.Symbol(variable)
        if not isinstance(expr, sp.core.relational.Relational):
            raise ValueError("不等式中缺少关系符号 (>, <, >=, <=)")
        sol = sp.solve_univariate_inequality(expr, sym, relational=False)
        steps = f"解不等式 {inequality}:\n  解集 = {sol}"
        return {"success": True, "result": str(sol), "steps": steps,
                "result_latex": sp.latex(sol)}
    except Exception as e:
        return _err(f"解不等式失败: {e}")


# =====================================================================================
# Tool: verify_identity — 符号验证恒等式 (推理的关键校验)
# =====================================================================================
def verify_identity(
    left: str,
    right: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """符号验证等式 left = right 是否恒成立 (化简差值为 0).

    推理链中的关键安全网: 任何一步"化简得"都能用本工具确认,
    无需写代码. 失败时给出差值表达式便于排查.

    Args:
        left: 等式左边, 如 "(x+1)**2"
        right: 等式右边, 如 "x**2 + 2*x + 1"

    Returns:
        {"success": True, "result": true/false, "difference": 差值, "steps": "..."}
    """
    try:
        le, syms1 = _parse_expr(left, variables)
        re_, syms2 = _parse_expr(right, variables)
        diff = sp.simplify(le - re_)
        steps = f"验证恒等式 {left} = {right}:\n"
        steps += f"  左-右 = {sp.latex(diff)}\n"
        if diff == 0:
            steps += "  差值为 0 → 恒等式成立 ✓"
            return {"success": True, "result": True, "difference": "0",
                    "result_latex": "\\text{TRUE}", "steps": steps}
        # 差值非 0: 再尝试数值抽查 (排除化简失败导致的误判)
        numerics = []
        free = sorted(diff.free_symbols, key=str)
        if free:
            import random
            rng = random.Random(42)
            for _ in range(5):
                subs = {s: rng.randint(1, 5) for s in free}
                try:
                    v = float(diff.subs(subs))
                    if abs(v) > 1e-9:
                        numerics.append(v)
                except (TypeError, ValueError):
                    pass
        if numerics:
            steps += "  数值抽查发现差值非零 → 等式不成立 ✗"
            return {"success": True, "result": False, "difference": str(diff),
                    "steps": steps}
        steps += "  符号化简差值无法归零 (可能恒成立但 SymPy 未化简, 请用 execute_code 进一步确认)"
        return {"success": True, "result": None, "difference": str(diff),
                "steps": steps}
    except Exception as e:
        return _err(f"验证恒等式失败: {e}")


# =====================================================================================
# Tool: rationalize — 分母有理化
# =====================================================================================
def rationalize(expression: str, variables: list[str] | None = None) -> dict[str, Any]:
    """分母有理化: 把 1/(√2+1) 化为 √2-1 形式."""
    try:
        expr, _ = _parse_expr(expression, variables)
        r = sp.radsimp(expr)
        steps = f"有理化 {expression}:\n  = {sp.latex(r)}"
        return {"success": True, "result": str(r),
                "result_latex": sp.latex(r), "steps": steps}
    except Exception as e:
        return _err(f"有理化失败: {e}")


# =====================================================================================
# Tool: simplify_trig — 三角化简
# =====================================================================================
def simplify_trig(expression: str, variables: list[str] | None = None) -> dict[str, Any]:
    """三角恒等变换化简, 如 sin(x)**2 + cos(x)**2 → 1."""
    try:
        expr, _ = _parse_expr(expression, variables)
        r = sp.trigsimp(expr)
        steps = f"三角化简 {expression}:\n  = {sp.latex(r)}"
        return {"success": True, "result": str(r),
                "result_latex": sp.latex(r), "steps": steps}
    except Exception as e:
        return _err(f"三角化简失败: {e}")


# =====================================================================================
# Coordinate tools — 解析几何基础
# =====================================================================================
def distance_two_points(point1: str, point2: str) -> dict[str, Any]:
    """两点间距离 (精确值): d = √[(x1-x2)² + (y1-y2)²].

    Args:
        point1: "x1,y1" 或 "[x1, y1]"
        point2: "x2,y2"

    Returns:
        {"success": True, "result": "2*sqrt(5)", "steps": "..."}
    """
    try:
        x1, y1 = _pt(point1)
        x2, y2 = _pt(point2)
        d = sp.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
        d = sp.simplify(d)
        steps = f"距离公式 d = √(({x1}-{x2})² + ({y1}-{y2})²):\n"
        steps += f"  = √(({sp.simplify(x1-x2)})² + ({sp.simplify(y1-y2)})²)\n"
        steps += f"  = {sp.latex(d)}"
        return {"success": True, "result": str(d),
                "result_latex": sp.latex(d), "steps": steps}
    except Exception as e:
        return _err(f"距离计算失败: {e}")


def midpoint_formula(point1: str, point2: str) -> dict[str, Any]:
    """中点坐标: ((x1+x2)/2, (y1+y2)/2)."""
    try:
        x1, y1 = _pt(point1)
        x2, y2 = _pt(point2)
        mx, my = sp.simplify((x1 + x2) / 2), sp.simplify((y1 + y2) / 2)
        steps = f"中点公式 M = (({x1}+{x2})/2, ({y1}+{y2})/2) = ({mx}, {my})"
        return {"success": True, "result": f"({mx}, {my})",
                "result_latex": sp.latex((mx, my)), "steps": steps}
    except Exception as e:
        return _err(f"中点计算失败: {e}")


def line_equation(point1: str, point2: str) -> dict[str, Any]:
    """过两点的直线方程 (一般式 Ax+By+C=0)."""
    try:
        x1, y1 = _pt(point1)
        x2, y2 = _pt(point2)
        x, y = sp.symbols("x y")
        # 行列式: (y1-y2)x + (x2-x1)y + (x1*y2 - x2*y1) = 0
        A = sp.simplify(y1 - y2)
        B = sp.simplify(x2 - x1)
        C = sp.simplify(x1 * y2 - x2 * y1)
        line = sp.simplify(A * x + B * y + C)
        steps = f"过 ({x1}, {y1}) 和 ({x2}, {y2}) 的直线:\n"
        steps += f"  A = y₁-y₂ = {A}, B = x₂-x₁ = {B}, C = x₁y₂-x₂y₁ = {C}\n"
        steps += f"  方程: {sp.latex(line)} = 0"
        return {"success": True, "result": f"{line} = 0",
                "result_latex": sp.latex(line), "steps": steps}
    except Exception as e:
        return _err(f"直线方程失败: {e}")


def collinear_check(point1: str, point2: str, point3: str) -> dict[str, Any]:
    """三点共线判定: 行列式 (叉积) = 0 则共线."""
    try:
        x1, y1 = _pt(point1)
        x2, y2 = _pt(point2)
        x3, y3 = _pt(point3)
        det = sp.simplify((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1))
        steps = f"共线判定 (叉积 = 0):\n"
        steps += f"  (x₂-x₁)(y₃-y₁) - (y₂-y₁)(x₃-x₁)\n"
        steps += f"  = ({x2}-{x1})({y3}-{y1}) - ({y2}-{y1})({x3}-{x1})\n"
        steps += f"  = {det}\n"
        if det == 0:
            steps += "  → 三点共线 ✓"
            return {"success": True, "result": True, "determinant": str(det), "steps": steps}
        steps += "  → 三点不共线 ✗"
        return {"success": True, "result": False, "determinant": str(det), "steps": steps}
    except Exception as e:
        return _err(f"共线判定失败: {e}")


def angle_between_lines(slope1: str, slope2: str) -> dict[str, Any]:
    """两直线夹角 (tan θ = |(k2-k1)/(1+k1·k2)|), 返回 tan 值与角度 (若为特殊角).

    Args:
        slope1: 直线1斜率, 如 "1/2"
        slope2: 直线2斜率, 如 "-2"
    """
    try:
        k1 = sp.sympify(slope1)
        k2 = sp.sympify(slope2)
        tan_theta = sp.Abs(sp.simplify((k2 - k1) / (1 + k1 * k2)))
        steps = f"夹角公式 tan θ = |(k₂-k₁)/(1+k₁k₂)|:\n"
        steps += f"  = |({k2}-{k1})/(1+{k1}·{k2})| = {sp.latex(tan_theta)}\n"
        theta = None
        try:
            angle_deg = float(sp.atan(tan_theta) * 180 / sp.pi)
            theta = f"{angle_deg:.1f}°"
            steps += f"  θ ≈ {theta}"
        except (TypeError, ValueError):
            pass
        return {"success": True, "result": {"tan_theta": str(tan_theta), "angle": theta},
                "result_latex": sp.latex(tan_theta), "steps": steps}
    except Exception as e:
        return _err(f"夹角计算失败: {e}")


# =====================================================================================
# Matrix tools — 行列式 / 逆矩阵 (解析几何行列式法)
# =====================================================================================
def matrix_det(matrix: list[list[str]]) -> dict[str, Any]:
    """方阵行列式 (精确值), 用于三点共线/面积/坐标变换验证.

    Args:
        matrix: 方阵, 如 [["a","b"],["c","d"]] 或 [["1","2","3"],["4","5","6"],["7","8","10"]]
    """
    try:
        m = sp.Matrix([[sp.sympify(v) for v in row] for row in matrix])
        if m.rows != m.cols:
            return _err("行列式仅对方阵定义")
        d = sp.simplify(m.det())
        steps = f"行列式 det({m.rows}×{m.cols}):\n"
        steps += f"  {sp.latex(m)} \n  = {sp.latex(d)}"
        return {"success": True, "result": str(d),
                "result_latex": sp.latex(d), "steps": steps}
    except Exception as e:
        return _err(f"行列式计算失败: {e}")


def matrix_inverse(matrix: list[list[str]]) -> dict[str, Any]:
    """方阵求逆 (精确值).

    Args:
        matrix: 方阵, 如 [["a","b"],["c","d"]]
    """
    try:
        m = sp.Matrix([[sp.sympify(v) for v in row] for row in matrix])
        if m.rows != m.cols:
            return _err("逆矩阵仅对方阵定义")
        det = sp.simplify(m.det())
        if det == 0:
            return _err("矩阵奇异 (行列式为 0), 不可逆")
        inv = sp.simplify(m.inv())
        steps = f"逆矩阵 ({m.rows}×{m.cols}):\n  {sp.latex(inv)}"
        return {"success": True, "result": [[str(v) for v in row] for row in inv.tolist()],
                "result_latex": sp.latex(inv), "steps": steps}
    except Exception as e:
        return _err(f"求逆失败: {e}")


# =====================================================================================
# Dispatch table
# =====================================================================================
TOOL_FUNCTIONS = {
    "solve_equation": solve_equation,
    "solve_inequality": solve_inequality,
    "verify_identity": verify_identity,
    "rationalize": rationalize,
    "simplify_trig": simplify_trig,
    "distance_two_points": distance_two_points,
    "midpoint_formula": midpoint_formula,
    "line_equation": line_equation,
    "collinear_check": collinear_check,
    "angle_between_lines": angle_between_lines,
    "matrix_det": matrix_det,
    "matrix_inverse": matrix_inverse,
}


def dispatch_algebra_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _err(f"未知工具: {name}")
    try:
        return fn(**args)
    except TypeError as e:
        return _err(f"参数错误: {e}")


__all__ = [
    "solve_equation", "solve_inequality", "verify_identity", "rationalize",
    "simplify_trig", "distance_two_points", "midpoint_formula", "line_equation",
    "collinear_check", "angle_between_lines", "matrix_det", "matrix_inverse",
    "TOOL_FUNCTIONS", "dispatch_algebra_tool",
]
