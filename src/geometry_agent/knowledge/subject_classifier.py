"""Subject classifier: routes a problem to one of the five disciplines.

Rules-based on Chinese keyword matching against the problem text (and optional
DSL). Priority order:
  function_derivative > triangle_solving > analytic_geometry > solid_geometry;
default fallback is plane_geometry (the most generic discipline).
"""
from __future__ import annotations

from ..types import SubjectType

_TRIANGLE_KEYWORDS = (
    "正弦", "余弦", "海伦", "解三角形", "正弦定理", "余弦定理",
    "射影定理", "内角和", "大边对大角", "已知两边",
)

_ANALYTIC_KEYWORDS = (
    "椭圆", "双曲线", "抛物线", "坐标", "解析几何",
    "焦点", "准线", "离心率", "渐近线", "韦达", "点差法",
    "圆方程", "圆锥曲线", "标准方程",
)

_SOLID_KEYWORDS = (
    "二面角", "棱锥", "棱柱", "球", "体积", "立体几何",
    "线面", "面面", "三垂线", "正方体", "长方体", "多面体",
    "欧拉", "表面积", "异面直线",
)

_FUNCTION_KEYWORDS = (
    "导数", "求导", "函数", "极值", "最值", "单调性", "单调递增",
    "单调递减", "零点", "驻点", "拐点", "凸性", "凹凸",
    "定积分", "不定积分", "积分", "微积分", "拉格朗日", "中值定理",
    "洛必达", "泰勒", "展开式", "幂级数", "收敛", "极限",
    "ln", "log", "exp", "e^x", "对数函数", "指数函数",
    "分段函数", "复合函数", "反函数", "二阶导",
    "f(x)", "f'(x)", "f''(x)",
)
_PROBABILITY_KEYWORDS = (
    "概率", "正态分布", "期望", "方差", "分布列", "随机变量",
    "3σ", "二项分布", "超几何分布", "统计",
)
_SEQUENCE_KEYWORDS = (
    "数列", "等差数列", "等比数列", "通项", "前n项", "裂项",
    "排列", "组合", "隔板法", "数学归纳法", "递推",
)
# NOTE: "切线方程", "三角函数", "sinx", "cosx", "tanx", "lnx" removed from
# function keywords — they are ambiguous (切线 could be conic or function;
# sin/cos could be triangle-solving).  Function classification now relies on
# the more specific keywords above (导数, f(x), 单调性, 极值, ...).


def _count_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for kw in keywords if kw in text)


def classify_subject(problem_text: str, dsl: str = "") -> SubjectType:
    """Classify a problem into one of the SubjectType disciplines.

    Uses keyword hit-counting; ties broken by priority
    function > triangle > analytic > solid > probability > sequence,
    default plane_geometry.
    """
    text = f"{problem_text or ''} {dsl or ''}"
    # Normalize for case-insensitive matching on ASCII keywords
    text_lower = text.lower()

    tri = _count_hits(text, _TRIANGLE_KEYWORDS)
    ana = _count_hits(text, _ANALYTIC_KEYWORDS)
    sol = _count_hits(text, _SOLID_KEYWORDS)
    fn = _count_hits(text, _FUNCTION_KEYWORDS) + _count_hits(text_lower, _FUNCTION_KEYWORDS)
    prob = _count_hits(text, _PROBABILITY_KEYWORDS)
    seq = _count_hits(text, _SEQUENCE_KEYWORDS)

    if tri == 0 and ana == 0 and sol == 0 and fn == 0 and prob == 0 and seq == 0:
        return SubjectType.PLANE_GEOMETRY

    # Priority: function > triangle > analytic > solid > probability > sequence
    scores = [
        (fn, SubjectType.FUNCTION_DERIVATIVE),
        (tri, SubjectType.TRIANGLE_SOLVING),
        (ana, SubjectType.ANALYTIC_GEOMETRY),
        (sol, SubjectType.SOLID_GEOMETRY),
        (prob, SubjectType.PROBABILITY),
        (seq, SubjectType.SEQUENCE),
    ]
    scores = [(s, st) for s, st in scores if s > 0]
    if not scores:
        return SubjectType.PLANE_GEOMETRY
    scores.sort(key=lambda x: x[0], reverse=True)
    return scores[0][1]
