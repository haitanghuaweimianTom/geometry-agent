"""Structured polynomial computation tools (LLM fills parameters, not code).

These tools wrap SymPy operations behind a parameterized interface so the LLM
does not need to write Python code. Each tool takes a structured argument
(expression string, variables, etc.) and returns a JSON-serializable dict with
``success``, ``result``, and ``steps`` (human-readable derivation).

This is the key reliability improvement over free-form ``execute_code``:
the LLM only needs to state *what* to compute, not *how* to code it.

Tools provided
--------------
- polynomial_factor        因式分解
- polynomial_expand        展开
- polynomial_simplify      化简
- polynomial_resultant     结式消元 (两条曲线联立消元命门)
- groebner_basis           Groebner 基 (多方程消元)
- solve_polynomial_system  解多项式方程组
- polynomial_divide        多项式除法 (带商与余式)
- polynomial_gcd           最大公因式
- collect_terms            按变量整理 (合并同类项)
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp


# =====================================================================================
# Internal helpers
# =====================================================================================
def _parse_expr(expr_str: str, variables: list[str] | None = None) -> tuple[sp.Expr, list[sp.Symbol]]:
    """Parse an expression string and infer/create the symbol list."""
    if not expr_str or not expr_str.strip():
        raise ValueError("表达式不能为空")
    # Determine variable names from the string if not given.
    if not variables:
        # Find all alphabetic tokens that look like variables (1-2 letters,
        # possibly with digits, excluding function names).
        found = re.findall(r"\b([a-zA-Z][a-zA-Z0-9]*)\b", expr_str)
        reserved = {"sin", "cos", "tan", "exp", "log", "ln", "sqrt", "pi",
                    "Abs", "Min", "Max", "Rational", "oo", "I"}
        names = sorted(set(f for f in found if f not in reserved))
    else:
        names = list(variables)
    symbols = [sp.Symbol(n) for n in names]
    local = {n: s for n, s in zip(names, symbols)}
    # Inject common constants/functions.
    local.update({"pi": sp.pi, "I": sp.I, "oo": sp.oo,
                  "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
                  "exp": sp.exp, "log": sp.log, "ln": sp.ln, "sqrt": sp.sqrt,
                  "Rational": sp.Rational, "Abs": sp.Abs})
    expr = sp.sympify(expr_str, locals=local, evaluate=True)
    return expr, symbols


def _ok(result: Any, steps: str = "") -> dict[str, Any]:
    return {"success": True, "result": str(result), "result_latex": sp.latex(result) if hasattr(result, "__iter__") is False else "",
            "steps": steps}


def _err(msg: str) -> dict[str, Any]:
    return {"success": False, "error": str(msg), "result": "", "steps": ""}


# =====================================================================================
# Tool: polynomial_factor
# =====================================================================================
def polynomial_factor(expression: str, variables: list[str] | None = None) -> dict[str, Any]:
    """因式分解: 将多项式分解为不可约因式的乘积.

    Args:
        expression: 多项式字符串, 如 "x**3 - 6*x**2 + 11*x - 6"
        variables: 变量名列表 (可选, 自动推断)

    Returns:
        {"success": True, "result": "(x-1)(x-2)(x-3)", "steps": "..."}
    """
    try:
        expr, syms = _parse_expr(expression, variables)
        factored = sp.factor(expr)
        steps = f"对 {expression} 因式分解:\n"
        steps += f"  原式 = {sp.latex(expr)}\n"
        steps += f"  分解 = {sp.latex(factored)}"
        return {"success": True, "result": str(factored),
                "result_latex": sp.latex(factored), "steps": steps}
    except Exception as e:
        return _err(f"因式分解失败: {e}")


# =====================================================================================
# Tool: polynomial_expand
# =====================================================================================
def polynomial_expand(expression: str, variables: list[str] | None = None) -> dict[str, Any]:
    """展开: 将乘积/幂展开为标准多项式形式.

    Args:
        expression: 表达式, 如 "(x-1)*(x-2)*(x-3)"
    """
    try:
        expr, _ = _parse_expr(expression, variables)
        expanded = sp.expand(expr)
        steps = f"展开 {expression}:\n  = {sp.latex(expanded)}"
        return {"success": True, "result": str(expanded),
                "result_latex": sp.latex(expanded), "steps": steps}
    except Exception as e:
        return _err(f"展开失败: {e}")


# =====================================================================================
# Tool: polynomial_simplify
# =====================================================================================
def polynomial_simplify(expression: str, variables: list[str] | None = None) -> dict[str, Any]:
    """化简: 将表达式化简为最简形式."""
    try:
        expr, _ = _parse_expr(expression, variables)
        simplified = sp.simplify(expr)
        steps = f"化简 {expression}:\n  = {sp.latex(simplified)}"
        return {"success": True, "result": str(simplified),
                "result_latex": sp.latex(simplified), "steps": steps}
    except Exception as e:
        return _err(f"化简失败: {e}")


# =====================================================================================
# Tool: polynomial_resultant — 结式消元 (圆锥曲线联立命门)
# =====================================================================================
def polynomial_resultant(
    expr1: str,
    expr2: str,
    eliminate: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """结式消元: 从两个多项式中消去指定变量, 得到一个不含该变量的多项式.

    圆锥曲线联立的核心: 把直线方程与曲线方程联立, 消去一个变量,
    得到关于另一变量的方程 (韦达定理的来源).

    Args:
        expr1: 第一个多项式 (方程左端, =0), 如 "y - k*x - m"
        expr2: 第二个多项式 (方程左端, =0), 如 "x**2/4 + y**2 - 1"
        eliminate: 要消去的变量名, 如 "y"
        variables: 全部变量 (可选)

    Returns:
        {"success": True, "result": "消元后的多项式", "steps": "..."}
    """
    try:
        e1, syms1 = _parse_expr(expr1, variables)
        e2, syms2 = _parse_expr(expr2, variables)
        all_vars = list(set(syms1 + syms2))
        elim_sym = sp.Symbol(eliminate)
        if elim_sym not in all_vars:
            all_vars.append(elim_sym)
        res = sp.resultant(e1, e2, elim_sym)
        steps = f"从两个方程消去 {eliminate}:\n"
        steps += f"  f₁ = {sp.latex(e1)} = 0\n"
        steps += f"  f₂ = {sp.latex(e2)} = 0\n"
        steps += f"  结式 Res(f₁, f₂, {eliminate}) = {sp.latex(res)}"
        return {"success": True, "result": str(res),
                "result_latex": sp.latex(res), "steps": steps}
    except Exception as e:
        return _err(f"结式消元失败: {e}")


# =====================================================================================
# Tool: groebner_basis — Groebner 基 (多方程消元)
# =====================================================================================
def groebner_basis(
    equations: list[str],
    variables: list[str],
    order: str = "grevlex",
) -> dict[str, Any]:
    """计算 Groebner 基: 多个多项式方程的等价方程组 (化简后).

    用于多约束联立消元 (如圆锥曲线+直线+切线条件三方程消元).

    Args:
        equations: 多项式列表 (均 = 0), 如 ["y - k*x - m", "x**2 + y**2 - r**2"]
        variables: 变量名列表, 如 ["x", "y"]
        order: 项序 "grevlex" / "lex" / "grlex"

    Returns:
        {"success": True, "result": [基多项式列表], "steps": "..."}
    """
    try:
        syms = [sp.Symbol(v) for v in variables]
        polys = []
        for eq in equations:
            e, _ = _parse_expr(eq, variables)
            polys.append(e)
        gb = sp.groebner(polys, *syms, order=order)
        steps = f"对方程组计算 Groebner 基 (项序 {order}):\n"
        for i, eq in enumerate(equations, 1):
            steps += f"  f{i} = {eq} = 0\n"
        steps += f"  Groebner 基 = {sp.latex(gb)}"
        gb_list = [str(g) for g in gb]
        return {"success": True, "result": gb_list,
                "result_latex": sp.latex(gb), "steps": steps}
    except Exception as e:
        return _err(f"Groebner 基计算失败: {e}")


# =====================================================================================
# Tool: solve_polynomial_system
# =====================================================================================
def solve_polynomial_system(
    equations: list[str],
    variables: list[str],
) -> dict[str, Any]:
    """解多项式方程组 (精确解).

    Args:
        equations: 方程左端列表 (均 = 0)
        variables: 未知量名列表

    Returns:
        {"success": True, "result": [{x:1, y:2}, ...], "steps": "..."}
    """
    try:
        syms = [sp.Symbol(v) for v in variables]
        polys = []
        for eq in equations:
            e, _ = _parse_expr(eq, variables)
            polys.append(e)
        sols = sp.solve(polys, syms, dict=True)
        steps = f"解方程组:\n"
        for i, eq in enumerate(equations, 1):
            steps += f"  f{i} = {eq} = 0\n"
        steps += f"  解 = {sols}"
        sol_str = [ {k: str(v) for k, v in s.items()} for s in sols] if sols else []
        return {"success": True, "result": sol_str,
                "result_latex": str(sols), "steps": steps}
    except Exception as e:
        return _err(f"解方程组失败: {e}")


# =====================================================================================
# Tool: polynomial_divide
# =====================================================================================
def polynomial_divide(
    dividend: str,
    divisor: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """多项式除法: 返回商和余式."""
    try:
        d, _ = _parse_expr(dividend, variables)
        v, _ = _parse_expr(divisor, variables)
        q, r = sp.div(sp.Poly(d, sp.Symbol(variables[0]) if variables else list(d.free_symbols)[0]),
                      sp.Poly(v, sp.Symbol(variables[0]) if variables else list(d.free_symbols)[0]))
        steps = f"({dividend}) ÷ ({divisor}):\n  商 = {q}\n  余式 = {r}"
        return {"success": True, "result": {"quotient": str(q), "remainder": str(r)},
                "steps": steps}
    except Exception as e:
        return _err(f"多项式除法失败: {e}")


# =====================================================================================
# Tool: polynomial_gcd
# =====================================================================================
def polynomial_gcd(
    expr1: str,
    expr2: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """最大公因式."""
    try:
        e1, _ = _parse_expr(expr1, variables)
        e2, _ = _parse_expr(expr2, variables)
        g = sp.gcd(e1, e2)
        steps = f"gcd({expr1}, {expr2}) = {sp.latex(g)}"
        return {"success": True, "result": str(g),
                "result_latex": sp.latex(g), "steps": steps}
    except Exception as e:
        return _err(f"求公因式失败: {e}")


# =====================================================================================
# Tool: collect_terms
# =====================================================================================
def collect_terms(
    expression: str,
    by_variable: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """按指定变量整理 (合并同类项)."""
    try:
        expr, _ = _parse_expr(expression, variables)
        sym = sp.Symbol(by_variable)
        collected = sp.collect(expr, sym)
        steps = f"按 {by_variable} 整理:\n  {sp.latex(collected)}"
        return {"success": True, "result": str(collected),
                "result_latex": sp.latex(collected), "steps": steps}
    except Exception as e:
        return _err(f"整理失败: {e}")


# =====================================================================================
# Tool: compare_coefficients — 系数比较 (抽象证明核心)
# =====================================================================================
def compare_coefficients(
    expr1: str,
    expr2: str,
    by_variable: str,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """逐项比较两个多项式在指定变量下的系数, 返回系数差异详情.

    用于抽象证明： "对所有 x, P(x) = Q(x)" 等价于各次幂系数相等.
    也用于求未知参数：令 P(x) ≡ 0, 则各次幂系数均为零, 解出未知数.

    Args:
        expr1: 第一个多项式, 如 "4*p*k**3 + (q**2-4*q-5)*k**2 + (q**2-1)"
        expr2: 第二个多项式, 如 "0" (与零比较, 即求所有系数为零的条件)
        by_variable: 按哪个变量比较系数, 如 "k"
        variables: 变量名列表 (可选, 自动推断)

    Returns:
        {"success": True, "result": {"identical": bool, "coeff_diffs": {"k**2": "q**2-4*q-5", ...}}, "steps": "..."}
    """
    try:
        e1, _ = _parse_expr(expr1, variables)
        e2, _ = _parse_expr(expr2, variables)
        sym = sp.Symbol(by_variable)
        diff = sp.expand(e1 - e2)
        try:
            poly = sp.Poly(diff, sym)
            coeffs = poly.as_dict()
        except Exception:
            coeffs = {0: diff}

        identical = diff == 0
        steps = f"系数比较 (按 {by_variable}):\n"
        steps += f"  P({by_variable}) = {sp.latex(sp.expand(e1))}\n"
        steps += f"  Q({by_variable}) = {sp.latex(sp.expand(e2))}\n"
        steps += f"  P - Q = {sp.latex(diff)}\n"

        if identical:
            steps += "  所有系数相等 → 恒等式成立 ✓"
        else:
            steps += "  系数差异 (非零项):\n"
            for deg in sorted(coeffs.keys(), reverse=True):
                c = coeffs[deg]
                if c != 0:
                    if isinstance(deg, tuple):
                        steps += f"    {by_variable}^{deg}: 差 = {sp.latex(c)}\n"
                    else:
                        steps += f"    {by_variable}^{deg}: 差 = {sp.latex(c)}\n"

        return {
            "success": True,
            "result": {
                "identical": identical,
                "difference_poly": str(diff),
                "coefficients": {str(k): str(v) for k, v in coeffs.items()},
            },
            "result_latex": sp.latex(diff),
            "steps": steps,
        }
    except Exception as e:
        return _err(f"系数比较失败: {e}")


# =====================================================================================
# Dispatch table
# =====================================================================================
TOOL_FUNCTIONS = {
    "polynomial_factor": polynomial_factor,
    "polynomial_expand": polynomial_expand,
    "polynomial_simplify": polynomial_simplify,
    "polynomial_resultant": polynomial_resultant,
    "groebner_basis": groebner_basis,
    "solve_polynomial_system": solve_polynomial_system,
    "polynomial_divide": polynomial_divide,
    "polynomial_gcd": polynomial_gcd,
    "collect_terms": collect_terms,
    "compare_coefficients": compare_coefficients,
}


def dispatch_polynomial_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a polynomial tool by name."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _err(f"未知工具: {name}")
    try:
        return fn(**args)
    except TypeError as e:
        return _err(f"参数错误: {e}")


__all__ = [
    "polynomial_factor", "polynomial_expand", "polynomial_simplify",
    "polynomial_resultant", "groebner_basis", "solve_polynomial_system",
    "polynomial_divide", "polynomial_gcd", "collect_terms",
    "TOOL_FUNCTIONS", "dispatch_polynomial_tool",
]
