"""Unified tool registry for the Geometry Agent reasoning loop.

This module merges two families of tools:

1. The pre-existing pipeline tools (``verify`` / ``solve`` / ``search`` /
   ``graph_query`` / ``reflect``) declared in
   :mod:`geometry_agent.reasoning.tools`.
2. The new code-execution + advanced geometry-method tools declared in this
   package: ``execute_code`` / ``complex_method`` / ``coordinate_method`` /
   ``projective_method``.

:func:`get_tool_schemas` returns the merged OpenAI function-calling schema
list. :func:`get_tool_dispatchers` returns a ``name -> callable`` mapping
that the reasoning agent can use to invoke the new tools; existing tools
remain sourced from the pipeline-supplied ``tools_dict``.
"""

from __future__ import annotations

from typing import Any, Callable

from geometry_agent.tools.code_executor import CodeExecutor
from geometry_agent.tools.geometry_prover import (
    complex_method,
    coordinate_method,
    projective_method,
)
from geometry_agent.tools import polynomial_tools as _poly
from geometry_agent.tools import conic_tools as _conic
from geometry_agent.tools import function_tools as _func
from geometry_agent.tools import algebra_tools as _algebra

# Re-export the existing schema list so callers can reach it from one place.
from geometry_agent.reasoning.tools import TOOL_SCHEMAS as _EXISTING_TOOL_SCHEMAS


# --------------------------------------------------------------------------- #
# New tool schemas (code execution + advanced geometry methods).
# --------------------------------------------------------------------------- #
_CODE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": (
                "Execute a sandboxed Python snippet for symbolic (sympy) or "
                "numeric (numpy) computation. Safe modules are pre-imported "
                "as math, np, sp, fractions, decimal, statistics. Returns "
                "{success, output, error, value, code}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "Python source. The trailing expression's value "
                            "is captured in `value`."
                        ),
                    }
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complex_method",
            "description": (
                "ADVANCED: 复数法 — verify a geometric relation (collinear / "
                "perpendicular / parallel / equal_length) using complex-number "
                "coordinates. Points are supplied as complex numbers or "
                "[re, im] pairs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "points": {
                        "type": "object",
                        "description": "Mapping label -> complex | [re, im].",
                    },
                    "relation": {
                        "type": "string",
                        "enum": ["collinear", "perpendicular", "parallel", "equal_length"],
                    },
                    "targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels the relation applies to.",
                    },
                },
                "required": ["points", "relation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "coordinate_method",
            "description": (
                "ADVANCED: 解析法 / 坐标法 — verify a geometric relation "
                "(distance / slope / collinear / perpendicular / parallel / "
                "midpoint) using Cartesian coordinates and sympy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "points": {
                        "type": "object",
                        "description": "Mapping label -> [x, y].",
                    },
                    "relation": {
                        "type": "string",
                        "enum": ["distance", "slope", "collinear",
                                 "perpendicular", "parallel", "midpoint"],
                    },
                    "targets": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "expected": {
                        "description": "Optional expected numeric value for distance / slope.",
                    },
                },
                "required": ["points", "relation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "projective_method",
            "description": (
                "ADVANCED: 射影法 hook — compute and optionally verify the "
                "cross-ratio (A,B;C,D) of four collinear points."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "points": {
                        "type": "object",
                        "description": "Mapping label -> [x, y] of four collinear points.",
                    },
                    "targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exactly 4 labels in order (A, B, C, D).",
                    },
                    "expected": {
                        "description": "Optional expected cross-ratio value.",
                    },
                },
                "required": ["points", "targets"],
            },
        },
    },
    # ------------------------------------------------------------------ #
    # Structured polynomial tools
    # ------------------------------------------------------------------ #
    {
        "type": "function",
        "function": {
            "name": "polynomial_factor",
            "description": "因式分解: 将多项式分解为不可约因式的乘积. 参数: expression(多项式字符串), variables(变量名列表, 可选).",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "多项式, 如 x**3-6*x**2+11*x-6"},
                    "variables": {"type": "array", "items": {"type": "string"}, "description": "变量名 (可选, 自动推断)"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "polynomial_expand",
            "description": "展开: 将乘积/幂展开为标准多项式. 参数: expression, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "polynomial_simplify",
            "description": "化简: 将表达式化简为最简形式. 参数: expression, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "polynomial_resultant",
            "description": "结式消元(圆锥曲线联立命门): 从两个多项式中消去指定变量, 得到不含该变量的多项式. 参数: expr1, expr2(两个方程左端=0), eliminate(要消去的变量), variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expr1": {"type": "string", "description": "第一个方程左端, 如 y-k*x-m"},
                    "expr2": {"type": "string", "description": "第二个方程左端, 如 x**2/4+y**2-1"},
                    "eliminate": {"type": "string", "description": "要消去的变量, 如 y"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expr1", "expr2", "eliminate"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "groebner_basis",
            "description": "Groebner基(多方程消元): 对多个多项式方程计算等价化简方程组. 参数: equations(方程左端列表), variables(变量名), order(项序, 默认grevlex).",
            "parameters": {
                "type": "object",
                "properties": {
                    "equations": {"type": "array", "items": {"type": "string"}},
                    "variables": {"type": "array", "items": {"type": "string"}},
                    "order": {"type": "string", "default": "grevlex"},
                },
                "required": ["equations", "variables"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "solve_polynomial_system",
            "description": "解多项式方程组(精确解). 参数: equations(方程左端=0列表), variables(未知量名).",
            "parameters": {
                "type": "object",
                "properties": {
                    "equations": {"type": "array", "items": {"type": "string"}},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["equations", "variables"],
            },
        },
    },
    # ------------------------------------------------------------------ #
    # Conic section tools
    # ------------------------------------------------------------------ #
    {
        "type": "function",
        "function": {
            "name": "conic_standard_form",
            "description": "一般二次方程化标准型: 判别曲线类型(椭圆/双曲线/抛物线)并提取系数. 参数: equation(方程左端=0), variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "equation": {"type": "string", "description": "如 x**2+2*y**2-4"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["equation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conic_tangent_line",
            "description": "求圆锥曲线的切线: 点在曲线上用隐函数求导; 点在曲线外设切线由判别式=0求解. 参数: conic_equation, point_x, point_y, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conic_equation": {"type": "string"},
                    "point_x": {"type": "string"},
                    "point_y": {"type": "string"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["conic_equation", "point_x", "point_y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conic_line_intersect",
            "description": "直线与圆锥曲线联立求交点. 参数: conic_equation, line_equation, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conic_equation": {"type": "string"},
                    "line_equation": {"type": "string"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["conic_equation", "line_equation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vieta_theorem",
            "description": "韦达定理: 直线代入圆锥曲线消去一变量后, 提取另一变量的韦达关系(x1+x2, x1*x2, Δ). 参数: conic_equation, line_equation, eliminate(默认y), variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conic_equation": {"type": "string"},
                    "line_equation": {"type": "string"},
                    "eliminate": {"type": "string", "default": "y"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["conic_equation", "line_equation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conic_chord_length",
            "description": "弦长公式: 直线截圆锥曲线所得弦长 = √(1+k²)·|x1-x2|. 参数: conic_equation, line_equation, eliminate, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conic_equation": {"type": "string"},
                    "line_equation": {"type": "string"},
                    "eliminate": {"type": "string", "default": "y"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["conic_equation", "line_equation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conic_focus_chord",
            "description": "焦点弦性质速查: 给定曲线类型和参数, 返回焦点、焦点弦长公式、通径. 参数: conic_type(椭圆/双曲线/抛物线), a, b, c_or_p.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conic_type": {"type": "string", "enum": ["椭圆", "双曲线", "抛物线"]},
                    "a": {"type": "string"},
                    "b": {"type": "string", "default": "0"},
                    "c_or_p": {"type": "string", "default": "0"},
                },
                "required": ["conic_type", "a"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conic_eccentricity",
            "description": "求离心率. 参数: conic_type(椭圆/双曲线/抛物线), a, b.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conic_type": {"type": "string", "enum": ["椭圆", "双曲线", "抛物线"]},
                    "a": {"type": "string"},
                    "b": {"type": "string"},
                },
                "required": ["conic_type", "a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "affine_transform",
            "description": "仿射变换(竞赛): 对曲线施加2×2线性变换+平移. 参数: conic_equation, matrix(2×3变换矩阵[[a11,a12,b1],[a21,a22,b2]]), variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conic_equation": {"type": "string"},
                    "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "2×3矩阵"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["conic_equation", "matrix"],
            },
        },
    },
    # ------------------------------------------------------------------ #
    # Function & derivative tools
    # ------------------------------------------------------------------ #
    {
        "type": "function",
        "function": {
            "name": "compute_derivative",
            "description": "求导: 计算函数的n阶导数. 参数: expression, variable(默认x), order(阶数, 默认1), variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "如 x**3-3*x"},
                    "variable": {"type": "string", "default": "x"},
                    "order": {"type": "integer", "default": 1},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_extrema",
            "description": "求极值: 找驻点并用二阶导数判断极大/极小. 参数: expression, variable, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_monotonic_intervals",
            "description": "求单调区间: 通过导数符号分析. 参数: expression, variable, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tangent_line",
            "description": "切线方程: 求曲线在x=point_x处的切线. 参数: expression, point_x, variable, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "point_x": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression", "point_x"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_limit",
            "description": "求极限(支持洛必达, SymPy自动判断). 参数: expression, variable, target(极限点), direction(+-/ +/-), variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "target": {"type": "string", "default": "0"},
                    "direction": {"type": "string", "default": "+-"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_integral",
            "description": "求积分: 不定积分或定积分. 参数: expression, variable, lower, upper(定积分上下限, 不填则不定积分), variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "lower": {"type": "string"},
                    "upper": {"type": "string"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "taylor_expand",
            "description": "泰勒展开: 在x=center处展开到n阶. 参数: expression, variable, center, order, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "center": {"type": "string", "default": "0"},
                    "order": {"type": "integer", "default": 4},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inequality_prove",
            "description": "构造函数法证不等式: 构造h(x)=left-right, 分析最小值符号. 参数: left, right, variable, domain, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "left": {"type": "string"},
                    "right": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "domain": {"type": "string", "default": "R"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["left", "right"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "separate_parameter",
            "description": "分离参数法: 从含参不等式中分离参数, 求参数范围. 参数: expression, parameter, variable, inequality, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "parameter": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "inequality": {"type": "string", "default": ">="},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression", "parameter"],
            },
        },
    },
    # ------------------------------------------------------------------ #
    # General algebra tools (v2)
    # ------------------------------------------------------------------ #
    {
        "type": "function",
        "function": {
            "name": "solve_equation",
            "description": "解方程(任意类型: 多项式/三角/指数/对数): 求 f(x)=0 的根. 参数: equation(方程左端=0), variable(未知量, 默认x), domain(可选: R 或 (0,oo) 等区间过滤).",
            "parameters": {
                "type": "object",
                "properties": {
                    "equation": {"type": "string", "description": "方程左端, 如 x**2-4 或 sin(x)-1/2"},
                    "variable": {"type": "string", "default": "x"},
                    "domain": {"type": "string", "default": "R"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["equation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "solve_inequality",
            "description": "解一元不等式, 返回解集区间. 参数: inequality(如 x**2-4>0), variable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "inequality": {"type": "string"},
                    "variable": {"type": "string", "default": "x"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["inequality"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_identity",
            "description": "符号验证恒等式 left=right 是否成立 (化简差值为0则真). 推理链安全网: 任何化简/等式结论都应调用本工具确认. 参数: left, right, variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "left": {"type": "string", "description": "等式左边, 如 (x+1)**2"},
                    "right": {"type": "string", "description": "等式右边, 如 x**2+2*x+1"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["left", "right"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rationalize",
            "description": "分母有理化: 1/(√2+1) → √2-1. 参数: expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simplify_trig",
            "description": "三角恒等变换化简, 如 sin(x)**2+cos(x)**2 → 1. 参数: expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "variables": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "distance_two_points",
            "description": "两点间距离(精确): d=√[(x1-x2)²+(y1-y2)²]. 参数: point1, point2 (格式 'x,y' 或 '[x, y]').",
            "parameters": {
                "type": "object",
                "properties": {
                    "point1": {"type": "string", "description": "如 '1,1'"},
                    "point2": {"type": "string", "description": "如 '3,5'"},
                },
                "required": ["point1", "point2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "midpoint_formula",
            "description": "中点坐标: ((x1+x2)/2, (y1+y2)/2). 参数: point1, point2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "point1": {"type": "string"},
                    "point2": {"type": "string"},
                },
                "required": ["point1", "point2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "line_equation",
            "description": "过两点的直线方程(一般式 Ax+By+C=0). 参数: point1, point2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "point1": {"type": "string"},
                    "point2": {"type": "string"},
                },
                "required": ["point1", "point2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collinear_check",
            "description": "三点共线判定(叉积=0). 参数: point1, point2, point3.",
            "parameters": {
                "type": "object",
                "properties": {
                    "point1": {"type": "string"},
                    "point2": {"type": "string"},
                    "point3": {"type": "string"},
                },
                "required": ["point1", "point2", "point3"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "angle_between_lines",
            "description": "两直线夹角: tanθ=|(k2-k1)/(1+k1k2)|. 参数: slope1, slope2 (斜率, 可用分数).",
            "parameters": {
                "type": "object",
                "properties": {
                    "slope1": {"type": "string", "description": "如 1/2"},
                    "slope2": {"type": "string", "description": "如 -2"},
                },
                "required": ["slope1", "slope2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "matrix_det",
            "description": "方阵行列式(精确), 用于共线/面积/坐标变换验证. 参数: matrix (n×n 字符串方阵).",
            "parameters": {
                "type": "object",
                "properties": {
                    "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                },
                "required": ["matrix"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "matrix_inverse",
            "description": "方阵求逆(精确). 参数: matrix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                },
                "required": ["matrix"],
            },
        },
    },
]


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return the full OpenAI function-calling schema list.

    Order: existing pipeline tools first (verify / solve / search /
    graph_query / reflect), then the new code-execution + geometry-method
    tools.
    """
    return list(_EXISTING_TOOL_SCHEMAS) + list(_CODE_TOOL_SCHEMAS)


def get_tool_dispatchers(
    tools_dict: dict[str, Any] | None = None,
    *,
    executor: CodeExecutor | None = None,
) -> dict[str, Callable[..., Any]]:
    """Return a ``name -> callable`` dispatcher map.

    The map always contains the new code-execution tools. Existing pipeline
    tools (verify / solve / search / ...) are pulled from ``tools_dict`` if
    provided, so the reasoning loop can keep using whatever callables the
    pipeline already wires up.

    The ``execute_code`` callable takes ``code: str`` and returns a
    :class:`~geometry_agent.types.CodeResult`. The geometry-method callables
    take ``args: dict`` (plus an optional ``config``) and return a
    ``CodeResult``.
    """
    tools_dict = dict(tools_dict or {})
    exe = executor or CodeExecutor()

    def _execute_code(code: str = "", **kw: Any) -> Any:
        if not code and "args" in kw and isinstance(kw["args"], dict):
            code = kw["args"].get("code", "")
        return exe.execute(code)

    def _complex(args: dict | None = None, **kw: Any) -> Any:
        if args is None:
            args = kw
        return complex_method(args)

    def _coordinate(args: dict | None = None, **kw: Any) -> Any:
        if args is None:
            args = kw
        return coordinate_method(args)

    def _projective(args: dict | None = None, **kw: Any) -> Any:
        if args is None:
            args = kw
        return projective_method(args)

    # Structured tool wrappers — accept either kwargs or a single args dict.
    def _make_structured(fn):
        def _wrapper(args: dict | None = None, **kw: Any) -> Any:
            if args is None:
                args = kw
            return fn(**args)
        return _wrapper

    dispatchers: dict[str, Callable[..., Any]] = {
        "execute_code": _execute_code,
        "complex_method": _complex,
        "coordinate_method": _coordinate,
        "projective_method": _projective,
    }
    # Register polynomial tools
    for _name, _fn in _poly.TOOL_FUNCTIONS.items():
        dispatchers[_name] = _make_structured(_fn)
    # Register conic tools
    for _name, _fn in _conic.TOOL_FUNCTIONS.items():
        dispatchers[_name] = _make_structured(_fn)
    # Register function tools
    for _name, _fn in _func.TOOL_FUNCTIONS.items():
        dispatchers[_name] = _make_structured(_fn)
    # Register algebra tools
    for _name, _fn in _algebra.TOOL_FUNCTIONS.items():
        dispatchers[_name] = _make_structured(_fn)

    for name, fn in tools_dict.items():
        dispatchers.setdefault(name, fn)
    return dispatchers


__all__ = ["get_tool_schemas", "get_tool_dispatchers"]
