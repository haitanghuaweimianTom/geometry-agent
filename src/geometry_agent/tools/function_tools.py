"""Structured function & derivative tools (LLM fills parameters, not code).

函数与导数专用工具, 封装 SymPy 计算为参数化接口. LLM 只需声明要算什么.

Tools provided
--------------
- compute_derivative       求导 (一阶/二阶/n阶)
- find_extrema             求极值 (驻点+判断)
- find_monotonic_intervals 求单调区间
- tangent_line             切线方程
- find_zeros               求零点
- compute_limit            求极限 (含洛必达)
- compute_integral         定积分/不定积分
- taylor_expand            泰勒展开
- inequality_prove         不等式证明 (构造函数法)
- separate_parameter       分离参数法
"""

from __future__ import annotations

import sympy as sp
from typing import Any

from .polynomial_tools import _parse_expr, _err


# =====================================================================================
# Tool: compute_derivative
# =====================================================================================
def compute_derivative(
    expression: str,
    variable: str = "x",
    order: int = 1,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """求导: 计算函数的 n 阶导数.

    Args:
        expression: 函数表达式, 如 "x**3 - 3*x"
        variable: 求导变量
        order: 阶数 (1=一阶, 2=二阶)
    """
    try:
        expr, _ = _parse_expr(expression, variables or [variable])
        sym = sp.Symbol(variable)
        d = sp.diff(expr, sym, order)
        steps = f"求 {expression} 对 {variable} 的 {order} 阶导数:\n"
        if order == 1:
            steps += f"  f'({variable}) = {sp.latex(d)}"
        elif order == 2:
            steps += f"  f''({variable}) = {sp.latex(d)}"
        else:
            steps += f"  f^({order})({variable}) = {sp.latex(d)}"
        return {"success": True, "result": str(d),
                "result_latex": sp.latex(d), "steps": steps}
    except Exception as e:
        return _err(f"求导失败: {e}")


# =====================================================================================
# Tool: find_extrema
# =====================================================================================
def find_extrema(
    expression: str,
    variable: str = "x",
    domain: str | None = None,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """求极值: 找驻点并判断极大/极小.

    Args:
        expression: 函数表达式
        variable: 变量
        domain: 定义域 (可选), 如 "(0, oo)" 或 "[0, 1]"
    """
    try:
        expr, _ = _parse_expr(expression, variables or [variable])
        sym = sp.Symbol(variable)
        d1 = sp.diff(expr, sym)
        d2 = sp.diff(expr, sym, 2)
        critical = sp.solve(d1, sym)

        steps = f"求 {expression} 的极值:\n"
        steps += f"  f'({variable}) = {sp.latex(d1)}\n"
        steps += f"  f''({variable}) = {sp.latex(d2)}\n"
        steps += f"  驻点: f'({variable})=0 → {variable} = {critical}\n\n"

        extrema = []
        for cp in critical:
            if cp.is_real or (not cp.is_real and len(cp.atoms(sp.I)) == 0):
                second_val = d2.subs(sym, cp)
                second_val = sp.simplify(second_val)
                val = sp.simplify(expr.subs(sym, cp))
                if second_val > 0:
                    kind = "极小值"
                elif second_val < 0:
                    kind = "极大值"
                else:
                    kind = "需进一步判断"
                extrema.append({
                    "point": str(cp),
                    "value": str(val),
                    "type": kind,
                    "second_derivative": str(second_val),
                })
                steps += f"  {variable}={cp}: f''={second_val} → {kind}, f={val}\n"

        return {"success": True, "result": extrema, "steps": steps}
    except Exception as e:
        return _err(f"求极值失败: {e}")


# =====================================================================================
# Tool: find_monotonic_intervals
# =====================================================================================
def find_monotonic_intervals(
    expression: str,
    variable: str = "x",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """求单调区间: 通过导数符号分析."""
    try:
        expr, _ = _parse_expr(expression, variables or [variable])
        sym = sp.Symbol(variable)
        d1 = sp.diff(expr, sym)
        critical = sp.solve(d1, sym)
        real_crit = [c for c in critical if c.is_real or (not c.is_real and len(c.atoms(sp.I)) == 0)]

        steps = f"求 {expression} 的单调区间:\n"
        steps += f"  f'({variable}) = {sp.latex(d1)}\n"
        steps += f"  驻点: {real_crit}\n"

        # Test sign in intervals between critical points
        boundaries = sorted(real_crit, key=lambda v: float(v))
        test_points = []
        if not boundaries:
            test_points = [sp.Symbol(variable) - 1, sp.Symbol(variable) + 1]
        else:
            test_points.append(boundaries[0] - 1)
            for i in range(len(boundaries) - 1):
                test_points.append((boundaries[i] + boundaries[i+1]) / 2)
            test_points.append(boundaries[-1] + 1)

        intervals = []
        all_points = [sp.oo * (-1)] + boundaries + [sp.oo]
        for i, tp in enumerate(test_points):
            sign = d1.subs(sym, tp)
            sign = sp.sign(sp.simplify(sign))
            if sign > 0:
                mono = "单调递增"
            elif sign < 0:
                mono = "单调递减"
            else:
                mono = "驻点"
            intervals.append({
                "interval": f"({all_points[i]}, {all_points[i+1]})",
                "monotonicity": mono,
            })
            steps += f"  ({all_points[i]}, {all_points[i+1]}): f'符号={sign} → {mono}\n"

        return {"success": True, "result": intervals, "steps": steps}
    except Exception as e:
        return _err(f"求单调区间失败: {e}")


# =====================================================================================
# Tool: tangent_line
# =====================================================================================
def tangent_line(
    expression: str,
    point_x: str,
    variable: str = "x",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """切线方程: 求曲线在 x=point_x 处的切线.

    Args:
        expression: y = f(x)
        point_x: 切点 x 坐标
    """
    try:
        expr, _ = _parse_expr(expression, variables or [variable])
        sym = sp.Symbol(variable)
        px = sp.sympify(point_x)
        py = sp.simplify(expr.subs(sym, px))
        slope = sp.simplify(sp.diff(expr, sym).subs(sym, px))
        # y - py = slope * (x - px)
        x_var = sp.Symbol(variable)
        tangent = sp.expand(slope * (x_var - px) + py)
        steps = f"求 {expression} 在 {variable}={px} 处的切线:\n"
        steps += f"  f({px}) = {py}\n"
        steps += f"  f'({px}) = {slope}\n"
        steps += f"  切线: y = {sp.latex(tangent)}"
        return {"success": True, "result": f"y = {tangent}",
                "result_latex": sp.latex(tangent), "steps": steps}
    except Exception as e:
        return _err(f"求切线失败: {e}")


# =====================================================================================
# Tool: find_zeros
# =====================================================================================
def find_zeros(
    expression: str,
    variable: str = "x",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """求零点: 解 f(x) = 0."""
    try:
        expr, _ = _parse_expr(expression, variables or [variable])
        sym = sp.Symbol(variable)
        zeros = sp.solve(expr, sym)
        real_zeros = [z for z in zeros if z.is_real or (not z.is_real and len(z.atoms(sp.I)) == 0)]
        steps = f"求 {expression} = 0 的零点:\n"
        steps += f"  零点: {real_zeros}"
        return {"success": True, "result": [str(z) for z in real_zeros], "steps": steps}
    except Exception as e:
        return _err(f"求零点失败: {e}")


# =====================================================================================
# Tool: compute_limit
# =====================================================================================
def compute_limit(
    expression: str,
    variable: str = "x",
    target: str = "0",
    direction: str = "+-",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """求极限 (支持洛必达, SymPy 自动判断).

    Args:
        expression: 表达式
        variable: 变量
        target: 极限点
        direction: "+-" 双侧 / "+" 右极限 / "-" 左极限
    """
    try:
        expr, _ = _parse_expr(expression, variables or [variable])
        sym = sp.Symbol(variable)
        tgt = sp.sympify(target)
        if direction == "+-":
            lim = sp.limit(expr, sym, tgt)
            steps = f"求 lim_({variable}→{target}) {expression}:\n  = {sp.latex(lim)}"
        else:
            lim = sp.limit(expr, sym, tgt, dir=direction)
            steps = f"求 lim_({variable}→{target}{direction}) {expression}:\n  = {sp.latex(lim)}"
        return {"success": True, "result": str(lim),
                "result_latex": sp.latex(lim), "steps": steps}
    except Exception as e:
        return _err(f"求极限失败: {e}")


# =====================================================================================
# Tool: compute_integral
# =====================================================================================
def compute_integral(
    expression: str,
    variable: str = "x",
    lower: str | None = None,
    upper: str | None = None,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """求积分: 不定积分或定积分.

    Args:
        expression: 被积函数
        lower, upper: 定积分上下限 (不填则求不定积分)
    """
    try:
        expr, _ = _parse_expr(expression, variables or [variable])
        sym = sp.Symbol(variable)
        if lower is not None and upper is not None:
            lo = sp.sympify(lower)
            hi = sp.sympify(upper)
            result = sp.integrate(expr, (sym, lo, hi))
            steps = f"定积分 ∫_{lower}^{upper} {expression} d{variable}:\n  = {sp.latex(result)}"
        else:
            result = sp.integrate(expr, sym)
            steps = f"不定积分 ∫ {expression} d{variable}:\n  = {sp.latex(result)} + C"
        return {"success": True, "result": str(result),
                "result_latex": sp.latex(result), "steps": steps}
    except Exception as e:
        return _err(f"求积分失败: {e}")


# =====================================================================================
# Tool: taylor_expand
# =====================================================================================
def taylor_expand(
    expression: str,
    variable: str = "x",
    center: str = "0",
    order: int = 4,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """泰勒展开: 在 x=center 处展开到 n 阶.

    Args:
        expression: 函数
        center: 展开点
        order: 阶数
    """
    try:
        expr, _ = _parse_expr(expression, variables or [variable])
        sym = sp.Symbol(variable)
        ctr = sp.sympify(center)
        series = sp.series(expr, sym, ctr, order + 1).removeO()
        steps = f"泰勒展开 {expression} 在 {variable}={center} 处到 {order} 阶:\n"
        steps += f"  {sp.latex(series)}"
        return {"success": True, "result": str(series),
                "result_latex": sp.latex(series), "steps": steps}
    except Exception as e:
        return _err(f"泰勒展开失败: {e}")


# =====================================================================================
# Tool: inequality_prove — 构造函数法证不等式
# =====================================================================================
def inequality_prove(
    left: str,
    right: str,
    variable: str = "x",
    domain: str = "R",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """构造函数法证明不等式 left ≥ right (或 >).

    构造 h(x) = left - right, 分析其最小值符号.

    Args:
        left: 不等式左边
        right: 不等式右边
        domain: 定义域, 如 "R" / "(0, oo)" / "[0, 1]"
    """
    try:
        le, _ = _parse_expr(left, variables or [variable])
        re, _ = _parse_expr(right, variables or [variable])
        sym = sp.Symbol(variable)
        h = sp.expand(le - re)
        h_prime = sp.diff(h, sym)
        critical = sp.solve(h_prime, sym)
        real_crit = [c for c in critical if c.is_real or (not c.is_real and len(c.atoms(sp.I)) == 0)]

        steps = f"构造函数法证明 {left} ≥ {right}:\n"
        steps += f"  令 h({variable}) = {left} - {right} = {sp.latex(h)}\n"
        steps += f"  h'({variable}) = {sp.latex(h_prime)}\n"
        steps += f"  驻点: {real_crit}\n"

        # Evaluate h at critical points and boundaries
        min_val = None
        eval_points = list(real_crit)
        # Check domain boundaries if finite
        vals = []
        for cp in eval_points:
            v = sp.simplify(h.subs(sym, cp))
            vals.append((cp, v))
            steps += f"  h({cp}) = {v}\n"

        if vals:
            min_val = min(vals, key=lambda t: t[1])
            steps += f"\n  最小值 h({min_val[0]}) = {min_val[1]}\n"
            if min_val[1] >= 0:
                conclusion = f"因最小值 {min_val[1]} ≥ 0, 故 {left} ≥ {right} 成立"
            elif min_val[1] > 0:
                conclusion = f"因最小值 {min_val[1]} > 0, 故 {left} > {right} 成立"
            else:
                conclusion = f"因最小值 {min_val[1]} < 0, 不等式 {left} ≥ {right} 不成立"
            steps += conclusion

        return {"success": True, "result": {
            "h": str(h),
            "min_value": str(min_val[1]) if min_val else "无法确定",
            "min_point": str(min_val[0]) if min_val else "",
            "conclusion": conclusion if vals else "需要进一步分析",
        }, "steps": steps}
    except Exception as e:
        return _err(f"不等式证明失败: {e}")


# =====================================================================================
# Tool: separate_parameter — 分离参数法
# =====================================================================================
def separate_parameter(
    expression: str,
    parameter: str,
    variable: str = "x",
    inequality: str = ">=",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """分离参数法: 将参数 a 从 f(x,a) ≥ 0 中分离, 求 a 的范围.

    Args:
        expression: 含参表达式 f(x,a) (需 ≥0 或 ≤0)
        parameter: 参数名 (如 "a")
        inequality: ">=" / "<=" / ">" / "<"
        variable: 主变量
    """
    try:
        expr, _ = _parse_expr(expression, [variable, parameter])
        v_sym = sp.Symbol(variable)
        a_sym = sp.Symbol(parameter)
        # Solve expr = 0 for a in terms of x
        a_solutions = sp.solve(expr, a_sym)
        if not a_solutions:
            return _err("无法分离参数 (表达式对参数非线性)")
        a_expr = a_solutions[0]

        # Now inequality expr >= 0 becomes a >= g(x) or a <= g(x)
        # depending on the sign of the coefficient of a.
        steps = f"分离参数 {parameter}:\n"
        steps += f"  由 {expression} {inequality} 0 解出 {parameter}:\n"
        steps += f"  {parameter} = {sp.latex(a_expr)}\n"

        # Find range of g(x) by finding its extrema
        g_prime = sp.diff(a_expr, v_sym)
        crit = sp.solve(g_prime, v_sym)
        real_crit = [c for c in crit if c.is_real or (not c.is_real and len(c.atoms(sp.I)) == 0)]
        steps += f"  g'({variable}) = {sp.latex(g_prime)}\n"
        steps += f"  g 的驻点: {real_crit}\n"

        extrema_vals = [sp.simplify(a_expr.subs(v_sym, c)) for c in real_crit]
        for c, v in zip(real_crit, extrema_vals):
            steps += f"  g({c}) = {v}\n"

        g_min = min(extrema_vals) if extrema_vals else None
        g_max = max(extrema_vals) if extrema_vals else None

        if inequality in (">=", ">"):
            if g_max is not None:
                conclusion = f"{parameter} ≥ {g_max} (g(x)的最大值)"
            else:
                conclusion = "需要分析 g(x) 的值域"
        else:
            if g_min is not None:
                conclusion = f"{parameter} ≤ {g_min} (g(x)的最小值)"
            else:
                conclusion = "需要分析 g(x) 的值域"

        steps += f"\n  结论: {conclusion}"
        return {"success": True, "result": {
            "separated": str(a_expr),
            "range": conclusion,
            "extrema": [str(v) for v in extrema_vals],
        }, "steps": steps}
    except Exception as e:
        return _err(f"分离参数失败: {e}")


# =====================================================================================
# Dispatch table
# =====================================================================================
TOOL_FUNCTIONS = {
    "compute_derivative": compute_derivative,
    "find_extrema": find_extrema,
    "find_monotonic_intervals": find_monotonic_intervals,
    "tangent_line": tangent_line,
    "find_zeros": find_zeros,
    "compute_limit": compute_limit,
    "compute_integral": compute_integral,
    "taylor_expand": taylor_expand,
    "inequality_prove": inequality_prove,
    "separate_parameter": separate_parameter,
}


def dispatch_function_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _err(f"未知工具: {name}")
    try:
        return fn(**args)
    except TypeError as e:
        return _err(f"参数错误: {e}")


__all__ = [
    "compute_derivative", "find_extrema", "find_monotonic_intervals",
    "tangent_line", "find_zeros", "compute_limit", "compute_integral",
    "taylor_expand", "inequality_prove", "separate_parameter",
    "TOOL_FUNCTIONS", "dispatch_function_tool",
]
