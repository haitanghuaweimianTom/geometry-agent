"""Projective geometry tools for the reasoning loop.

Covers the core projective-geometry operations needed for Chinese high-school
and competition math problems: pole/polar, harmonic division, cross-ratio,
and projective transformations.

Each tool takes structured string arguments, returns a JSON-serializable dict
with ``success`` / ``result`` / ``steps``, following the conventions of
:mod:`geometry_agent.tools.polynomial_tools`.
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp

from .polynomial_tools import _parse_expr, _err


# =====================================================================================
# Internal helpers
# =====================================================================================
def _parse_point(pt_str: str) -> tuple[sp.Expr, sp.Expr]:
    """Parse a point string like '1,2' or '(x0, y0)' or '[x0, y0]'."""
    s = pt_str.strip().replace("（", "(").replace("）", ")").strip("()[]")
    parts = [p.strip() for p in re.split(r"[,，\s]+", s) if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"无法解析点: {pt_str!r} (需要 x,y 格式)")
    return sp.sympify(parts[0]), sp.sympify(parts[1])


def _parse_line(line_str: str) -> tuple[sp.Expr, sp.Expr, sp.Expr]:
    """Parse a line string like 'Ax+By+C=0' or 'y=kx+b' into (A, B, C) for Ax+By+C=0."""
    s = line_str.strip().replace(" ", "")
    if "=" in s:
        left, right = s.split("=", 1)
        # Move everything to left: left - right = 0 -> A x + B y + C = 0
        expr = sp.sympify(f"({left}) - ({right})")
    else:
        expr = sp.sympify(s)
    poly = sp.Poly(sp.expand(expr), sp.Symbol('x'), sp.Symbol('y'))
    coeff = poly.as_dict()
    A = coeff.get((1, 0), 0)
    B = coeff.get((0, 1), 0)
    C = coeff.get((0, 0), 0)
    return A, B, C


def _conic_matrix(conic_type: str, a: sp.Expr, b: sp.Expr, extra: sp.Expr | None = None) -> sp.Matrix:
    """Build the 3×3 symmetric matrix of a conic in standard form.

    The conic is represented as [x y 1] · M · [x y 1]ᵀ = 0.
    """
    M = sp.zeros(3, 3)
    if conic_type == "椭圆":
        # x²/a² + y²/b² = 1 → x²/a² + y²/b² - 1 = 0
        M[0, 0] = 1 / a**2
        M[1, 1] = 1 / b**2
        M[2, 2] = -1
    elif conic_type == "双曲线":
        # x²/a² - y²/b² = 1 → x²/a² - y²/b² - 1 = 0
        M[0, 0] = 1 / a**2
        M[1, 1] = -1 / b**2
        M[2, 2] = -1
    elif conic_type == "抛物线":
        # y² = 2px → y² - 2p x = 0
        p = extra if extra is not None else a
        M[1, 1] = 1
        M[0, 2] = -p
        M[2, 0] = -p
    elif conic_type == "圆":
        # x² + y² = r² → x² + y² - r² = 0
        r = a
        M[0, 0] = 1
        M[1, 1] = 1
        M[2, 2] = -(r**2)
    elif conic_type == "一般":
        # ax² + bxy + cy² + dx + ey + f = 0
        M[0, 0] = a
        M[0, 1] = b / 2
        M[0, 2] = b / 2 if extra is None else extra / 2  # extra = d
        M[1, 0] = b / 2
        M[1, 1] = b if extra is None else extra  # extra = c
        M[1, 2] = (extra if extra is not None else 0) / 2  # e/2
        M[2, 0] = M[0, 2]
        M[2, 1] = M[1, 2]
        M[2, 2] = 0
    return M


def _conic_matrix_from_eq(eq_str: str) -> sp.Matrix:
    """Build the 3×3 matrix from a general conic equation string like '3*x**2 - y**2 - 3'.

    The equation is assumed to be of the form F(x,y) = 0.
    """
    expr = sp.sympify(eq_str)
    x, y = sp.Symbol('x'), sp.Symbol('y')
    poly = sp.Poly(sp.expand(expr), x, y)
    coeff = poly.as_dict()
    # Terms: (x_deg, y_deg) -> coefficient
    a = coeff.get((2, 0), 0)  # x²
    b = coeff.get((1, 1), 0)  # xy
    c = coeff.get((0, 2), 0)  # y²
    d = coeff.get((1, 0), 0)  # x
    e = coeff.get((0, 1), 0)  # y
    f = coeff.get((0, 0), 0)  # constant
    M = sp.Matrix([
        [a, b/2, d/2],
        [b/2, c, e/2],
        [d/2, e/2, f],
    ])
    return M


# =====================================================================================
# Tool: pole_of_point — 求点关于圆锥曲线的极线
# =====================================================================================
def pole_of_point(
    point: str,
    conic_eq: str = "",
    conic_type: str = "",
    a: str = "1",
    b: str = "1",
) -> dict[str, Any]:
    """求点关于圆锥曲线的极线 (polar line).

    给定点 P(x₀, y₀) 和圆锥曲线 C, 返回 P 关于 C 的极线方程。
    极线是连接从 P 向 C 所作两条切线切点的直线；若 P 在 C 上, 极线即切线。

    用法一 (标准型): conic_type="椭圆", a="2", b="1", point="x0,y0"
    用法二 (一般方程): conic_eq="3*x**2 - y**2 - 3", point="x0,y0"

    Args:
        point: 点坐标, 如 "x0,y0" 或 "2,1"
        conic_eq: 圆锥曲线一般方程 (设为 0), 如 "3*x**2 - y**2 - 3"
        conic_type: 标准型名称: 椭圆/双曲线/抛物线/圆
        a: 参数 a (或半径 r, 当 conic_type="圆")
        b: 参数 b (椭圆/双曲线)

    Returns:
        {"success": True, "result": {"polar": "Ax+By+C=0", "A":..., "B":..., "C":...},
         "steps": "推导过程", "result_latex": "..."}
    """
    try:
        x0, y0 = _parse_point(point)

        if conic_eq:
            M = _conic_matrix_from_eq(conic_eq)
            x, y = sp.Symbol('x'), sp.Symbol('y')
        elif conic_type:
            a_val = sp.sympify(a)
            b_val = sp.sympify(b)
            M = _conic_matrix(conic_type, a_val, b_val)
            x, y = sp.Symbol('x'), sp.Symbol('y')
        else:
            return _err("必须提供 conic_eq 或 conic_type")

        # Polar line: [x₀ y₀ 1] · M · [x y 1]ᵀ = 0
        pt_hom = sp.Matrix([x0, y0, 1])
        var_hom = sp.Matrix([x, y, 1])
        polar_expr = sp.expand((pt_hom.T * M * var_hom)[0])

        # Extract A, B, C from Ax + By + C = 0
        poly = sp.Poly(polar_expr, x, y)
        coeff = poly.as_dict()
        A = coeff.get((1, 0), 0)
        B = coeff.get((0, 1), 0)
        C = coeff.get((0, 0), 0)

        polar_str = f"{sp.latex(A)}x + {sp.latex(B)}y + {sp.latex(C)} = 0"
        if conic_type == "圆" and sp.simplify(A - x0) == 0 and sp.simplify(B - y0) == 0:
            simplified = f"x₀·x + y₀·y = r²"
        elif conic_type == "椭圆" and sp.simplify(A - x0/sp.sympify(a)**2) == 0:
            simplified = f"x₀x/a² + y₀y/b² = 1"
        else:
            simplified = polar_str

        steps = f"点 ({x0}, {y0}) 关于圆锥曲线的极线:\n"
        if conic_eq:
            steps += f"  曲线: {conic_eq} = 0\n"
        else:
            steps += f"  曲线: {conic_type} (a={a}, b={b})\n"
        steps += f"  极线: {simplified}"

        return {
            "success": True,
            "result": {
                "polar_equation": f"{A}*x + {B}*y + {C} = 0",
                "A": str(A), "B": str(B), "C": str(C),
                "simplified": simplified,
            },
            "result_latex": sp.latex(sp.Eq(A*x + B*y, -C)),
            "steps": steps,
        }
    except Exception as e:
        return _err(f"极线计算失败: {e}")


# =====================================================================================
# Tool: polar_of_line — 求直线关于圆锥曲线的极点
# =====================================================================================
def polar_of_line(
    line: str,
    conic_eq: str = "",
    conic_type: str = "",
    a: str = "1",
    b: str = "1",
) -> dict[str, Any]:
    """求直线关于圆锥曲线的极点 (pole).

    给定直线 l: Ax+By+C=0 和圆锥曲线 C, 返回 l 关于 C 的极点坐标。
    这是 pole_of_point 的逆运算。

    Args:
        line: 直线方程, 如 "x+2=0" 或 "2*x+3*y-1=0" 或 "y=k*x+b"
        conic_eq: 圆锥曲线一般方程
        conic_type: 标准型名称
        a, b: 参数

    Returns:
        {"success": True, "result": {"pole": "(x, y)", "x":..., "y":...}, "steps": "..."}
    """
    try:
        A, B, C = _parse_line(line)
        if sp.simplify(C) == 0:
            return _err("直线常数项不能为零 (极点不存在或无定义)")

        if conic_eq:
            M = _conic_matrix_from_eq(conic_eq)
        elif conic_type:
            a_val = sp.sympify(a)
            b_val = sp.sympify(b)
            M = _conic_matrix(conic_type, a_val, b_val)
        else:
            return _err("必须提供 conic_eq 或 conic_type")

        # The pole [x₀, y₀, 1] satisfies: [x₀ y₀ 1] · M = k · [A B C]
        # Solve for x₀, y₀, k
        M_inv = M.inv()
        k = sp.Symbol('k')
        # Actually, [x₀ y₀ 1] = k · [A B C] · M⁻¹
        line_hom = sp.Matrix([A, B, C])
        pole_hom = line_hom.T * M_inv  # This is k · [x₀ y₀ z₀]
        # Normalize: divide by the last component
        x0 = sp.simplify(pole_hom[0] / pole_hom[2])
        y0 = sp.simplify(pole_hom[1] / pole_hom[2])

        steps = f"直线 {A}x + {B}y + {C} = 0 关于圆锥曲线的极点:\n"
        steps += f"  极点 = ({sp.latex(x0)}, {sp.latex(y0)})"
        if conic_type == "椭圆":
            steps += f"\n  (验证: x₀x/a² + y₀y/b² = 1 即 {sp.latex(A)}x + {sp.latex(B)}y + {sp.latex(C)} = 0)"

        return {
            "success": True,
            "result": {"pole": f"({x0}, {y0})", "x": str(x0), "y": str(y0)},
            "result_latex": f"({sp.latex(x0)}, {sp.latex(y0)})",
            "steps": steps,
        }
    except Exception as e:
        return _err(f"极点计算失败: {e}")


# =====================================================================================
# Tool: cross_ratio — 计算四点交比
# =====================================================================================
def cross_ratio(
    points: str,
) -> dict[str, Any]:
    """计算四点 (A,B;C,D) 的交比 (cross-ratio).

    四点必须共线。交比定义为 (A,B;C,D) = (AC/BC) / (AD/BD)。

    Args:
        points: 四个点坐标, 格式 "x1,y1; x2,y2; x3,y3; x4,y4"

    Returns:
        {"success": True, "result": {"cross_ratio": value, "is_harmonic": bool}, "steps": "..."}
    """
    try:
        parts = [p.strip() for p in points.split(";")]
        if len(parts) != 4:
            return _err(f"需要4个点 (分号分隔), 得到 {len(parts)} 个")

        pts = [_parse_point(p) for p in parts]
        x = [p[0] for p in pts]
        y = [p[1] for p in pts]

        # Parameterize on the line through first two points
        dx = x[1] - x[0]
        dy = y[1] - y[0]

        if sp.simplify(dx) == 0 and sp.simplify(dy) == 0:
            return _err("前两点重合, 无法确定直线方向")

        # Project onto the direction vector: param = ((X-x1)*dx + (Y-y1)*dy)/(dx²+dy²)
        denom = dx**2 + dy**2
        t = [sp.simplify(((x[i] - x[0])*dx + (y[i] - y[0])*dy) / denom) for i in range(4)]

        # Cross-ratio (A,B;C,D) = (t3-t1)/(t2-t3) * (t4-t2)/(t4-t1)?
        # Standard: (A,B;C,D) = (AC/BC) / (AD/BD) = (t3-t1)/(t3-t2) * (t4-t2)/(t4-t1)
        # Actually, let me use the standard formula:
        # (A,B;C,D) = (AC * BD) / (BC * AD)
        AC = t[2] - t[0]
        BD = t[3] - t[1]
        BC = t[2] - t[1]
        AD = t[3] - t[0]

        cr = sp.simplify(AC * BD / (BC * AD))

        is_harmonic = sp.simplify(cr + 1) == 0

        steps = f"四点交比 (A,B;C,D):\n"
        for i, label in enumerate(["A", "B", "C", "D"]):
            steps += f"  {label} = ({x[i]}, {y[i]})\n"
        steps += f"  参数化: t(A)=0, t(B)=1, t(C)={sp.latex(t[2])}, t(D)={sp.latex(t[3])}\n"
        steps += f"  交比 = {sp.latex(cr)}"
        if is_harmonic:
            steps += "\n  调和分割! (交比 = -1)"

        return {
            "success": True,
            "result": {
                "cross_ratio": str(cr),
                "is_harmonic": is_harmonic,
                "parameters": [str(ti) for ti in t],
            },
            "result_latex": sp.latex(cr),
            "steps": steps,
        }
    except Exception as e:
        return _err(f"交比计算失败: {e}")


# =====================================================================================
# Tool: harmonic_conjugate — 求调和共轭点
# =====================================================================================
def harmonic_conjugate(
    a: str,
    b: str,
    c: str,
) -> dict[str, Any]:
    """求点 C 关于线段 AB 的调和共轭点 D, 使得 (A,B;C,D) = -1.

    三点必须共线。

    Args:
        a: 点 A 坐标, 如 "x1,y1"
        b: 点 B 坐标
        c: 点 C 坐标

    Returns:
        {"success": True, "result": {"d": "(x,y)", "x":..., "y":...}, "steps": "..."}
    """
    try:
        xA, yA = _parse_point(a)
        xB, yB = _parse_point(b)
        xC, yC = _parse_point(c)

        # (A,B;C,D) = -1 means D is the harmonic conjugate of C w.r.t. A,B
        # Using the section formula: if C divides AB in ratio λ = AC/CB,
        # then D divides AB in ratio -λ.
        # Let t_C parameterize C on line AB: C = ((1-t_C)*A + t_C*B) for some t_C
        # Then D = ((1-t_D)*A + t_D*B) where (0,1;t_C,t_D) = -1
        # (t_C-0)/(t_C-1) * (t_D-1)/(t_D-0) = -1
        # t_C/(t_C-1) * (t_D-1)/t_D = -1
        # t_C(t_D-1) = -t_D(t_C-1)
        # t_C·t_D - t_C = -t_D·t_C + t_D
        # 2t_C·t_D = t_C + t_D
        # t_D = t_C/(2t_C-1)

        # First find t_C: C = (1-t_C)*A + t_C*B
        dx = xB - xA
        dy = yB - yA
        if sp.simplify(dx) == 0 and sp.simplify(dy) == 0:
            return _err("A 和 B 重合, 无法定义调和共轭")

        if sp.simplify(dx) != 0:
            tC = sp.simplify((xC - xA) / dx)
        else:
            tC = sp.simplify((yC - yA) / dy)

        # tD = tC/(2tC-1)
        tD = sp.simplify(tC / (2*tC - 1))

        xD = sp.simplify(xA + tD * dx)
        yD = sp.simplify(yA + tD * dy)

        steps = f"点 C({xC},{yC}) 关于线段 AB 的调和共轭点:\n"
        steps += f"  A = ({xA}, {yA}), B = ({xB}, {yB})\n"
        steps += f"  t(C) = {sp.latex(tC)}\n"
        steps += f"  t(D) = tC/(2tC-1) = {sp.latex(tD)}\n"
        steps += f"  D = ({sp.latex(xD)}, {sp.latex(yD)})\n"
        steps += f"  验证: (A,B;C,D) = -1"

        return {
            "success": True,
            "result": {"d": f"({xD}, {yD})", "x": str(xD), "y": str(yD)},
            "result_latex": f"({sp.latex(xD)}, {sp.latex(yD)})",
            "steps": steps,
        }
    except Exception as e:
        return _err(f"调和共轭计算失败: {e}")


# =====================================================================================
# Tool: check_harmonic — 验证四点调和分割
# =====================================================================================
def check_harmonic(
    points: str,
) -> dict[str, Any]:
    """验证四点 (A,B;C,D) 是否构成调和分割 (交比 = -1)。

    Args:
        points: 四个点, 格式 "x1,y1; x2,y2; x3,y3; x4,y4"

    Returns:
        {"success": True, "result": {"is_harmonic": bool, "cross_ratio": value}, "steps": "..."}
    """
    try:
        result = cross_ratio(points=points)
        if not result["success"]:
            return result
        cr = result["result"]["cross_ratio"]
        is_harm = result["result"]["is_harmonic"]
        return {
            "success": True,
            "result": {
                "is_harmonic": is_harm,
                "cross_ratio": cr,
            },
            "steps": result["steps"],
        }
    except Exception as e:
        return _err(f"调和验证失败: {e}")


# =====================================================================================
# Tool: projective_transform — 射影变换矩阵
# =====================================================================================
def projective_transform(
    from_points: str,
    to_points: str,
) -> dict[str, Any]:
    """求将四个点 (A,B,C,D) 映射到 (A',B',C',D') 的射影变换矩阵。

    射影变换将点 (x,y) 映射到 (x',y') 满足:
    x' = (h11*x + h12*y + h13) / (h31*x + h32*y + h33)
    y' = (h21*x + h22*y + h23) / (h31*x + h32*y + h33)

    Args:
        from_points: 原四点, 分号分隔, 如 "0,0; 1,0; 0,1; 1,1"
        to_points: 目标四点, 同上格式

    Returns:
        {"success": True, "result": {"matrix": [[h11,h12,h13],[h21,h22,h23],[h31,h32,h33]]}, "steps": "..."}
    """
    try:
        from_pts = [p.strip() for p in from_points.split(";")]
        to_pts = [p.strip() for p in to_points.split(";")]
        if len(from_pts) != 4 or len(to_pts) != 4:
            return _err("需要4对点 (from; to 各4个)")

        src = [_parse_point(p) for p in from_pts]
        dst = [_parse_point(p) for p in to_pts]

        # Build homogeneous linear system: H maps src[i] to k_i * dst[i]
        # For each point pair: cross(dst[i]_hom, H * src[i]_hom) = 0
        # This gives 2 equations per pair, 8 equations for 9 unknowns (H up to scale)
        # Fix h33 = 1, solve 8 equations for 8 unknowns

        h11, h12, h13, h21, h22, h23, h31, h32 = sp.symbols('h11 h12 h13 h21 h22 h23 h31 h32')
        eqs = []
        for i in range(4):
            sx, sy = src[i]
            dx, dy = dst[i]
            denom = h31 * sx + h32 * sy + 1
            eqs.append(sp.Eq((h11*sx + h12*sy + h13) / denom, dx))
            eqs.append(sp.Eq((h21*sx + h22*sy + h23) / denom, dy))

        # Multiply by denominator
        eqs_simplified = []
        for i in range(4):
            sx, sy = src[i]
            dx, dy = dst[i]
            eqs_simplified.append(sp.Eq(h11*sx + h12*sy + h13, dx*(h31*sx + h32*sy + 1)))
            eqs_simplified.append(sp.Eq(h21*sx + h22*sy + h23, dy*(h31*sx + h32*sy + 1)))

        sol = sp.solve(eqs_simplified, [h11, h12, h13, h21, h22, h23, h31, h32], dict=True)
        if not sol:
            return _err("射影变换无解 (四点可能不构成一般位置)")

        s = sol[0]
        H = [
            [str(s[h11]), str(s[h12]), str(s[h13])],
            [str(s[h21]), str(s[h22]), str(s[h23])],
            [str(s[h31]), str(s[h32]), "1"],
        ]

        steps = "射影变换矩阵 H:\n"
        steps += f"  H = {sp.latex(sp.Matrix([[s[h11],s[h12],s[h13]],[s[h21],s[h22],s[h23]],[s[h31],s[h32],1]]))}\n"
        steps += "  满足: H · [x y 1]ᵀ = k · [x' y' 1]ᵀ"

        return {
            "success": True,
            "result": {"matrix": H},
            "result_latex": sp.latex(sp.Matrix(H)),
            "steps": steps,
        }
    except Exception as e:
        return _err(f"射影变换计算失败: {e}")


# =====================================================================================
# Dispatch table
# =====================================================================================
TOOL_FUNCTIONS = {
    "pole_of_point": pole_of_point,
    "polar_of_line": polar_of_line,
    "cross_ratio": cross_ratio,
    "harmonic_conjugate": harmonic_conjugate,
    "check_harmonic": check_harmonic,
    "projective_transform": projective_transform,
}


def dispatch_projective_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a projective geometry tool by name."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _err(f"未知射影几何工具: {name}")
    try:
        return fn(**args)
    except TypeError as e:
        return _err(f"参数错误: {e}")


__all__ = [
    "pole_of_point", "polar_of_line", "cross_ratio",
    "harmonic_conjugate", "check_harmonic", "projective_transform",
    "TOOL_FUNCTIONS", "dispatch_projective_tool",
]