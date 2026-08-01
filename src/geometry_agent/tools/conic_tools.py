"""Structured conic-section tools (LLM fills parameters, not code).

圆锥曲线专用工具, 封装 SymPy 计算为参数化接口. LLM 只需声明要算什么,
不需要写代码. 覆盖高考+竞赛级需求.

Tools provided
--------------
- conic_standard_form      一般二次方程 → 标准型 (判别+化简)
- conic_tangent_line       求切线 (点在曲线上/外)
- conic_line_intersect     直线与圆锥曲线联立求交点
- conic_chord_length       弦长公式
- conic_focus_chord        焦点弦性质
- vieta_theorem            韦达定理 (联立后提取根与系数关系)
- conic_eccentricity       求离心率
- conic_polar_equation      极坐标方程
- conic_parametric          参数方程
- affine_transform          仿射变换 (竞赛)
"""

from __future__ import annotations

import sympy as sp
from typing import Any

from .polynomial_tools import _parse_expr, _ok, _err


# =====================================================================================
# Tool: conic_standard_form — 一般二次方程化标准型
# =====================================================================================
def conic_standard_form(
    equation: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """一般二次方程 Ax²+Bxy+Cy²+Dx+Ey+F=0 → 判别类型 + 标准型.

    判别式 Δ = B²-4AC:
      Δ < 0: 椭圆型 (特例退化)
      Δ = 0: 抛物线型
      Δ > 0: 双曲线型

    Returns:
        {"success": True, "result": {"type": "椭圆", "delta": -64, "standard_form": "x²/4+y²=1"}}
    """
    try:
        expr, syms = _parse_expr(equation, variables)
        if len(syms) < 2:
            return _err("圆锥曲线方程至少需要两个变量 (x, y)")
        x, y = syms[0], syms[1]
        poly = sp.Poly(expr, x, y)
        coeffs = {tuple(mons): c for mons, c in poly.as_dict().items()}

        A = coeffs.get((2, 0), 0)
        B = coeffs.get((1, 1), 0)
        C = coeffs.get((0, 2), 0)
        D = coeffs.get((1, 0), 0)
        E = coeffs.get((0, 1), 0)
        F = coeffs.get((0, 0), 0)

        delta = B**2 - 4 * A * C

        if delta < 0:
            if A == C and B == 0:
                conic_type = "圆"
            else:
                conic_type = "椭圆"
        elif delta == 0:
            conic_type = "抛物线"
        else:
            conic_type = "双曲线"

        # Try to complete squares for standard form
        steps = f"一般方程: {sp.latex(expr)} = 0\n"
        steps += f"系数: A={A}, B={B}, C={C}, D={D}, E={E}, F={F}\n"
        steps += f"判别式 Δ = B²-4AC = {B}²-4·{A}·{C} = {delta} → {conic_type}"

        return {
            "success": True,
            "result": {
                "type": conic_type,
                "delta": int(delta),
                "coefficients": {"A": int(A), "B": int(B), "C": int(C),
                                 "D": int(D), "E": int(E), "F": int(F)},
            },
            "result_latex": f"\\text{{{conic_type}}}\\;(\\Delta={delta})",
            "steps": steps,
        }
    except Exception as e:
        return _err(f"化标准型失败: {e}")


# =====================================================================================
# Tool: conic_line_intersect — 直线与圆锥曲线联立求交点
# =====================================================================================
def conic_line_intersect(
    conic_equation: str,
    line_equation: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """直线与圆锥曲线联立求交点.

    Args:
        conic_equation: 曲线方程 (左端=0), 如 "x**2/4 + y**2 - 1"
        conic_equation: 直线方程 (左端=0), 如 "y - k*x - m"
        variables: 变量, 默认 [x, y]

    Returns:
        {"success": True, "result": [{"x":.., "y":..}, ...], "steps": "..."}
    """
    try:
        ce, syms = _parse_expr(conic_equation, variables)
        le, _ = _parse_expr(line_equation, variables or [str(s) for s in syms])
        if len(syms) < 2:
            return _err("需要两个变量 (x, y)")
        x, y = syms[0], syms[1]
        sols = sp.solve([ce, le], [x, y], dict=True)
        steps = f"联立:\n  曲线: {sp.latex(ce)} = 0\n  直线: {sp.latex(le)} = 0\n"
        steps += f"  交点: {sols}"
        sol_str = [{str(k): str(v) for k, v in s.items()} for s in sols]
        return {"success": True, "result": sol_str, "steps": steps,
                "result_latex": str(sols)}
    except Exception as e:
        return _err(f"联立求交点失败: {e}")


# =====================================================================================
# Tool: vieta_theorem — 韦达定理 (联立后根与系数关系)
# =====================================================================================
def vieta_theorem(
    conic_equation: str,
    line_equation: str,
    eliminate: str = "y",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """韦达定理: 直线代入圆锥曲线消去一变量后, 提取另一变量的韦达关系.

    联立直线 y=kx+m 代入曲线, 消去 y 得到关于 x 的二次方程:
        a·x² + b·x + c = 0
    返回:
        x₁+x₂ = -b/a,  x₁·x₂ = c/a,  Δ = b²-4ac

    Args:
        conic_equation: 曲线方程 (左端=0)
        line_equation: 直线方程 (左端=0), 如 "y - k*x - m"
        eliminate: 要消去的变量 (默认 y)
    """
    try:
        from .polynomial_tools import polynomial_resultant
        res = polynomial_resultant(conic_equation, line_equation, eliminate, variables)
        if not res["success"]:
            return res

        # The resultant is (up to sign) a·x² + b·x + c.  Extract coeffs.
        remaining_var = [v for v in (variables or ["x", "y"]) if v != eliminate]
        if not remaining_var:
            remaining_var = ["x"]
        sym = sp.Symbol(remaining_var[0])
        res_expr = sp.sympify(res["result"])
        poly = sp.Poly(res_expr, sym)
        coeffs = poly.all_coeffs()
        if len(coeffs) == 3:
            a, b, c = coeffs
            steps = res["steps"] + "\n\n韦达定理:\n"
            steps += f"  方程: {a}·{remaining_var[0]}² + {b}·{remaining_var[0]} + {c} = 0\n"
            steps += f"  {remaining_var[0]}₁ + {remaining_var[0]}₂ = -{b}/{a} = {sp.Rational(-b, a) if a != 0 else 'undefined'}\n"
            steps += f"  {remaining_var[0]}₁ · {remaining_var[0]}₂ = {c}/{a} = {sp.Rational(c, a) if a != 0 else 'undefined'}\n"
            disc = b**2 - 4*a*c
            steps += f"  Δ = {b}² - 4·{a}·{c} = {disc}"
            return {"success": True, "result": {
                "a": str(a), "b": str(b), "c": str(c),
                "sum": str(-b/a), "product": str(c/a),
                "discriminant": str(disc),
            }, "steps": steps}
        elif len(coeffs) == 2:
            b, c = coeffs
            steps = res["steps"] + f"\n\n一次方程 {b}·{remaining_var[0]} + {c} = 0\n"
            steps += f"  {remaining_var[0]} = {-c/b}"
            return {"success": True, "result": {"linear": True, "root": str(-c/b)},
                    "steps": steps}
        else:
            return {"success": True, "result": {"coeffs": [str(c) for c in coeffs]},
                    "steps": res["steps"]}
    except Exception as e:
        return _err(f"韦达定理失败: {e}")


# =====================================================================================
# Tool: conic_chord_length — 弦长公式
# =====================================================================================
def conic_chord_length(
    conic_equation: str,
    line_equation: str,
    eliminate: str = "y",
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """弦长公式: 直线截圆锥曲线所得弦长.

    若联立得 a·x²+b·x+c=0, 则弦长 = √(1+k²)·|x₁-x₂|
        其中 |x₁-x₂| = √[(x₁+x₂)² - 4x₁x₂] = √(Δ)/|a|

    Args:
        conic_equation: 曲线方程 (左端=0)
        line_equation: 直线方程 (左端=0), 形如 y - k*x - m
    """
    try:
        vt = vieta_theorem(conic_equation, line_equation, eliminate, variables)
        if not vt["success"]:
            return vt
        r = vt["result"]
        if not r.get("a"):
            return _err("无法提取二次项系数")

        a = sp.sympify(r["a"])
        b = sp.sympify(r["b"])
        c = sp.sympify(r["c"])
        disc = sp.sympify(r["discriminant"])

        # Extract slope k from line equation y = k*x + m
        le, syms = _parse_expr(line_equation, variables or ["x", "y"])
        x_sym = sp.Symbol("x")
        y_sym = sp.Symbol("y")
        # solve line for y in terms of x
        y_sol = sp.solve(le, y_sym)
        k = sp.sympify(0)
        if y_sol:
            k_expr = y_sol[0]
            k = sp.diff(k_expr, x_sym) if x_sym in k_expr.free_symbols else sp.sympify(0)

        chord = sp.sqrt(1 + k**2) * sp.sqrt(disc) / sp.Abs(a)
        chord_simplified = sp.simplify(chord)
        steps = vt["steps"] + "\n\n弦长:\n"
        steps += f"  斜率 k = {k}\n"
        steps += f"  |x₁-x₂| = √Δ / |a| = √({disc}) / |{a}|\n"
        steps += f"  弦长 = √(1+k²)·|x₁-x₂| = {sp.latex(chord_simplified)}"
        return {"success": True, "result": str(chord_simplified),
                "result_latex": sp.latex(chord_simplified), "steps": steps}
    except Exception as e:
        return _err(f"弦长计算失败: {e}")


# =====================================================================================
# Tool: conic_tangent_line — 求切线
# =====================================================================================
def conic_tangent_line(
    conic_equation: str,
    point_x: str,
    point_y: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """求圆锥曲线在给定点处 (或过给定点) 的切线方程.

    Args:
        conic_equation: 曲线方程 (左端=0)
        point_x: 切点 x 坐标 (表达式字符串)
        point_y: 切点 y 坐标
    """
    try:
        ce, syms = _parse_expr(conic_equation, variables)
        x, y = syms[0], syms[1]
        px = sp.sympify(point_x)
        py = sp.sympify(point_y)

        # Check if point is on the curve
        on_curve = sp.simplify(ce.subs({x: px, y: py})) == 0

        if on_curve:
            # Use implicit differentiation: dy/dx = -F_x/F_y
            Fx = sp.diff(ce, x)
            Fy = sp.diff(ce, y)
            slope = -Fx.subs({x: px, y: py}) / Fy.subs({x: px, y: py})
            slope = sp.simplify(slope)
            tangent = slope * (x - px) - (y - py)
            tangent = sp.expand(tangent)
            steps = f"点 ({px}, {py}) 在曲线上, 用隐函数求导:\n"
            steps += f"  F_x = {sp.latex(Fx)}, F_y = {sp.latex(Fy)}\n"
            steps += f"  斜率 k = -F_x/F_y = {sp.latex(slope)}\n"
            steps += f"  切线: y - {py} = {sp.latex(slope)}(x - {px})"
        else:
            # Point outside: find tangent through (px, py)
            # Tangent line: y - py = k(x - px) → substitute into curve → discriminant = 0
            k = sp.Symbol("k")
            line = y - py - k * (x - px)
            from .polynomial_tools import polynomial_resultant
            res = polynomial_resultant(conic_equation, str(line), "y", variables)
            if res["success"]:
                res_expr = sp.sympify(res["result"])
                poly_k = sp.Poly(res_expr, x)
                coeffs_x = poly_k.all_coeffs()
                # set discriminant in x to 0 to solve for k
                if len(coeffs_x) == 3:
                    a, b, c = coeffs_x
                    disc_k = b**2 - 4*a*c
                    k_sols = sp.solve(disc_k, k)
                else:
                    k_sols = []
                tangent_lines = [sp.expand((y - py) - ks * (x - px)) for ks in k_sols]
                steps = f"点 ({px}, {py}) 在曲线外, 设切线 y-{py}=k(x-{px}), 由 Δ=0 解 k:\n"
                for i, (ks, tl) in enumerate(zip(k_sols, tangent_lines), 1):
                    steps += f"  切线{i}: k={ks}, 方程 {sp.latex(tl)} = 0\n"
                if len(tangent_lines) == 1:
                    tangent = tangent_lines[0]
                else:
                    return {"success": True, "result": [str(t) for t in tangent_lines],
                            "steps": steps}
            else:
                return res

        return {"success": True, "result": str(tangent),
                "result_latex": sp.latex(tangent), "steps": steps}
    except Exception as e:
        return _err(f"求切线失败: {e}")


# =====================================================================================
# Tool: conic_focus_chord — 焦点弦性质
# =====================================================================================
def conic_focus_chord(
    conic_type: str,
    a: str,
    b: str = "0",
    c_or_p: str = "0",
) -> dict[str, Any]:
    """焦点弦性质速查 (标准曲线).

    Args:
        conic_type: "椭圆" / "双曲线" / "抛物线"
        a: 半长轴 (椭圆/双曲线) 或 焦准距 p (抛物线)
        b: 半短轴
        c_or_p: 离心率参数 c (椭圆/双曲线) 或已给的 p

    Returns:
        焦点弦长、焦半径公式等
    """
    try:
        if conic_type == "抛物线":
            p = sp.sympify(a)
            # y²=2px, 焦点 (p/2, 0), 焦点弦 x=px+p/2
            # 弦长 = x1+x2+p = 2p/sin²θ (θ为倾角)
            steps = f"抛物线 y²=2px (p={p}):\n"
            steps += f"  焦点 ({p/2}, 0)\n"
            steps += f"  焦点弦长 = x₁+x₂+p = 2p/sin²θ\n"
            steps += f"  通径(最短焦点弦) = 2p"
            return {"success": True, "result": {"focus": f"({p/2}, 0)",
                    "chord_length": "2p/sin²θ", "latus_rectum": str(2*p)},
                    "steps": steps}
        else:
            a_val = sp.sympify(a)
            b_val = sp.sympify(b)
            c_val = sp.sqrt(a_val**2 - b_val**2) if conic_type == "椭圆" else sp.sqrt(a_val**2 + b_val**2)
            e = c_val / a_val
            # 焦点弦长公式: 2ab²/(b²+a²c²cos²θ) for ellipse
            steps = f"{conic_type} a={a_val}, b={b_val}, c={c_val}, e={e}:\n"
            steps += f"  焦点 (±{c_val}, 0)\n"
            if conic_type == "椭圆":
                steps += f"  焦点弦长 = 2a·b²/(b²+c²cos²θ)\n"
                steps += f"  通径 = 2b²/a"
                return {"success": True, "result": {"focus": f"(±{c_val}, 0)",
                        "eccentricity": str(e), "chord_length": "2ab²/(b²+c²cos²θ)",
                        "latus_rectum": str(2*b_val**2/a_val)}, "steps": steps}
            else:  # 双曲线
                steps += f"  焦点弦长 = 2a·b²/(b²-c²cos²θ)\n"
                steps += f"  通径 = 2b²/a"
                return {"success": True, "result": {"focus": f"(±{c_val}, 0)",
                        "eccentricity": str(e), "chord_length": "2ab²/(b²-c²cos²θ)",
                        "latus_rectum": str(2*b_val**2/a_val)}, "steps": steps}
    except Exception as e:
        return _err(f"焦点弦查询失败: {e}")


# =====================================================================================
# Tool: conic_eccentricity
# =====================================================================================
def conic_eccentricity(
    conic_type: str,
    a: str,
    b: str,
) -> dict[str, Any]:
    """求离心率.

    Args:
        conic_type: "椭圆" / "双曲线" / "抛物线"
        a: 半长(实)轴
        b: 半短(虚)轴
    """
    try:
        if conic_type == "抛物线":
            return {"success": True, "result": "1", "steps": "抛物线离心率 e=1"}
        a_val = sp.sympify(a)
        b_val = sp.sympify(b)
        if conic_type == "椭圆":
            c = sp.sqrt(a_val**2 - b_val**2)
            e = sp.simplify(c / a_val)
            steps = f"椭圆: c=√(a²-b²)=√({a_val}²-{b_val}²)={c}\n  e=c/a={e}"
        else:  # 双曲线
            c = sp.sqrt(a_val**2 + b_val**2)
            e = sp.simplify(c / a_val)
            steps = f"双曲线: c=√(a²+b²)=√({a_val}²+{b_val}²)={c}\n  e=c/a={e}"
        return {"success": True, "result": str(e),
                "result_latex": sp.latex(e), "steps": steps}
    except Exception as e:
        return _err(f"求离心率失败: {e}")


# =====================================================================================
# Tool: conic_polar_equation
# =====================================================================================
def conic_polar_equation(
    conic_type: str,
    a: str,
    b: str = "0",
) -> dict[str, Any]:
    """极坐标方程: r = ep/(1±e·cosθ) (焦点为极点)."""
    try:
        if conic_type == "抛物线":
            p = sp.sympify(a)
            return {"success": True, "result": "r = p/(1-cosθ)",
                    "steps": f"抛物线 y²=2px: 焦点极坐标方程 r = p/(1-cosθ), p={p}"}
        a_val = sp.sympify(a)
        b_val = sp.sympify(b)
        if conic_type == "椭圆":
            c = sp.sqrt(a_val**2 - b_val**2)
            e = c / a_val
            p = b_val**2 / c
            steps = f"椭圆: e={e}, p=b²/c={p}\n  r = ep/(1-e·cosθ)"
            return {"success": True, "result": f"r = {sp.simplify(e*p)}/(1-{e}cosθ)", "steps": steps}
        else:
            c = sp.sqrt(a_val**2 + b_val**2)
            e = c / a_val
            p = b_val**2 / c
            steps = f"双曲线: e={e}, p=b²/c={p}\n  r = ep/(1-e·cosθ)"
            return {"success": True, "result": f"r = {sp.simplify(e*p)}/(1-{e}cosθ)", "steps": steps}
    except Exception as e:
        return _err(f"极坐标方程失败: {e}")


# =====================================================================================
# Tool: conic_parametric
# =====================================================================================
def conic_parametric(
    conic_type: str,
    a: str,
    b: str = "0",
) -> dict[str, Any]:
    """参数方程."""
    try:
        if conic_type == "抛物线":
            p = sp.sympify(a)
            t = sp.Symbol("t")
            steps = f"抛物线 y²=2px 参数方程:\n  x=2pt², y=2pt"
            return {"success": True, "result": {"x": f"2*{p}*t²", "y": f"2*{p}*t"}, "steps": steps}
        a_val = sp.sympify(a)
        b_val = sp.sympify(b)
        if conic_type == "椭圆":
            steps = f"椭圆 x²/a²+y²/b²=1 参数方程:\n  x=a·cosθ, y=b·sinθ"
            return {"success": True, "result": {"x": f"{a_val}cosθ", "y": f"{b_val}sinθ"}, "steps": steps}
        else:
            steps = f"双曲线 x²/a²-y²/b²=1 参数方程:\n  x=a·secθ, y=b·tanθ"
            return {"success": True, "result": {"x": f"{a_val}secθ", "y": f"{b_val}tanθ"}, "steps": steps}
    except Exception as e:
        return _err(f"参数方程失败: {e}")


# =====================================================================================
# Tool: affine_transform
# =====================================================================================
def affine_transform(
    conic_equation: str,
    matrix: list[list[str]],
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """仿射变换 (竞赛): 对曲线施加 2×2 线性变换 + 平移.

    Args:
        conic_equation: 原曲线方程
        matrix: 2×3 变换矩阵 [[a11,a12,b1],[a21,a22,b2]] 表示
                x' = a11·x + a12·y + b1, y' = a21·x + a22·y + b2
    """
    try:
        expr, syms = _parse_expr(conic_equation, variables)
        x, y = syms[0], syms[1]
        a11, a12, b1 = [sp.sympify(v) for v in matrix[0]]
        a21, a22, b2 = [sp.sympify(v) for v in matrix[1]]
        # Inverse transform: solve for old (x,y) in terms of new (x',y')
        xp, yp = sp.symbols("x' y'")
        sol = sp.solve([a11*x + a12*y + b1 - xp, a21*x + a22*y + b2 - yp], [x, y], dict=True)
        if not sol:
            return _err("变换矩阵不可逆")
        new_expr = sp.expand(expr.subs(sol[0]))
        steps = f"仿射变换:\n  x' = {a11}x + {a12}y + {b1}\n  y' = {a21}x + {a22}y + {b2}\n"
        steps += f"  逆变换代入原方程, 得到新方程:\n  {sp.latex(new_expr)} = 0"
        return {"success": True, "result": str(new_expr),
                "result_latex": sp.latex(new_expr), "steps": steps}
    except Exception as e:
        return _err(f"仿射变换失败: {e}")


# =====================================================================================
# Dispatch table
# =====================================================================================
TOOL_FUNCTIONS = {
    "conic_standard_form": conic_standard_form,
    "conic_tangent_line": conic_tangent_line,
    "conic_line_intersect": conic_line_intersect,
    "conic_chord_length": conic_chord_length,
    "conic_focus_chord": conic_focus_chord,
    "vieta_theorem": vieta_theorem,
    "conic_eccentricity": conic_eccentricity,
    "conic_polar_equation": conic_polar_equation,
    "conic_parametric": conic_parametric,
    "affine_transform": affine_transform,
}


def dispatch_conic_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _err(f"未知工具: {name}")
    try:
        return fn(**args)
    except TypeError as e:
        return _err(f"参数错误: {e}")


__all__ = [
    "conic_standard_form", "conic_tangent_line", "conic_line_intersect",
    "conic_chord_length", "conic_focus_chord", "vieta_theorem",
    "conic_eccentricity", "conic_polar_equation", "conic_parametric",
    "affine_transform", "TOOL_FUNCTIONS", "dispatch_conic_tool",
]
