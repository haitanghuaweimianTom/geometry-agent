"""Render a GeometryGraph to a Chinese-language LaTeX document string.

Pure text/table layout -- no TikZ, no figure. Output is a ``ctexart``
document compiled with ``xelatex`` (Noto CJK fonts).

Public API: :func:`graph_to_latex`.
"""

from __future__ import annotations

from typing import Any

from ..types import (
    Edge,
    GeometryGraph,
    Node,
    NodeType,
    RelType,
    VerifyState,
)
from .tikz_render import graph_to_tikz


REL_CN: dict[RelType, str] = {
    RelType.ON: "在...上",
    RelType.CENTER: "为...圆心",
    RelType.COLLINEAR: "共线",
    RelType.INTERSECT: "相交",
    RelType.TANGENT: "相切",
    RelType.PARALLEL: "平行",
    RelType.PERPENDICULAR: "垂直",
    RelType.EQUAL: "相等",
    RelType.INSIDE: "在...内",
    RelType.OUTSIDE: "在...外",
    RelType.CONCENTRIC: "同心",
    RelType.TANGENT_POINT: "切点",
    RelType.INSCRIBED: "内接",
    RelType.CIRCUMSCRIBED: "外接",
    RelType.SAME_ARC: "同弧",
    RelType.SIMILAR: "相似",
    RelType.CONGRUENT: "全等",
}

NODETYPE_CN: dict[NodeType, str] = {
    NodeType.POINT: "点",
    NodeType.LINE: "直线",
    NodeType.SEGMENT: "线段",
    NodeType.RAY: "射线",
    NodeType.CIRCLE: "圆",
    NodeType.ARC: "弧",
    NodeType.ELLIPSE: "椭圆",
    NodeType.POLYGON: "多边形",
}

VERIFY_CN: dict[VerifyState, str] = {
    VerifyState.TRUE: "已验证",
    VerifyState.FALSE: "不成立",
    VerifyState.UNCERTAIN: "待确认",
    VerifyState.PENDING: "待验证",
}

_UNCERTAIN_STATES = {VerifyState.UNCERTAIN, VerifyState.PENDING, VerifyState.FALSE}


def _fmt_num(x: Any) -> str:
    f = float(x)
    if f.is_integer():
        return str(int(f))
    return f"{f:g}"


def _fmt_coords(xy: Any) -> str:
    if xy is None:
        return ""
    return f"({_fmt_num(xy[0])}, {_fmt_num(xy[1])})"


def _tex_escape(s: str) -> str:
    if s is None:
        return ""
    out = []
    for ch in str(s):
        if ch == "\\":
            out.append(r"\textbackslash{}")
        elif ch in "%&$#_{}":
            out.append("\\" + ch)
        elif ch == "^":
            out.append(r"\textasciicircum{}")
        elif ch == "~":
            out.append(r"\textasciitilde{}")
        else:
            out.append(ch)
    return "".join(out)


def _label_of(node: Node) -> str:
    return node.label or node.id


def _node_attrs_desc(node: Node) -> str:
    """Chinese one-line description of a node's key attributes."""
    t = node.type
    a = node.attrs
    if t == NodeType.POINT:
        c = a.get("coords")
        if c is not None:
            return f"坐标 {_fmt_coords(c)}"
        return "坐标未知"
    if t == NodeType.CIRCLE:
        r = a.get("radius")
        return f"半径 {_fmt_num(r)}" if r is not None else "半径未知"
    if t == NodeType.ARC:
        p1 = a.get("p1")
        p2 = a.get("p2")
        if p1 and p2:
            return f"端点 {_tex_escape(str(p1))}, {_tex_escape(str(p2))}"
        return "弧"
    if t == NodeType.ELLIPSE:
        c = a.get("center")
        parts = []
        if c is not None:
            parts.append(f"中心 {_fmt_coords(c)}")
        parts.append(f"半长轴 {_fmt_num(a.get('semi_major', 0.0))}")
        parts.append(f"半短轴 {_fmt_num(a.get('semi_minor', 0.0))}")
        return ", ".join(parts)
    if t in (NodeType.SEGMENT, NodeType.LINE, NodeType.RAY):
        p1 = a.get("p1")
        p2 = a.get("p2")
        if p1 and p2:
            return f"端点 {_tex_escape(str(p1))}, {_tex_escape(str(p2))}"
        return ""
    if t == NodeType.POLYGON:
        verts = a.get("vertices_labels") or []
        if verts:
            return "顶点 " + ", ".join(_tex_escape(str(v)) for v in verts)
        return ""
    return ""


def _obj_ref_label(node_by_id: dict[str, Node], nid: str) -> str:
    n = node_by_id.get(nid)
    if n is None:
        return nid
    if n.type == NodeType.POINT:
        return _label_of(n)
    kw = {
        NodeType.SEGMENT: "线段", NodeType.LINE: "直线", NodeType.RAY: "射线",
        NodeType.CIRCLE: "圆", NodeType.ARC: "弧", NodeType.ELLIPSE: "椭圆",
        NodeType.POLYGON: "多边形", NodeType.POINT: "点",
    }.get(n.type, n.type.value)
    return f"{kw} {_label_of(n)}"


def _edge_evidence(edge: Edge) -> str:
    parts = []
    if edge.evidence:
        parts.append(edge.evidence)
    if edge.source and edge.source != "detected":
        parts.append(f"来源:{edge.source}")
    if edge.confidence < 1.0:
        parts.append(f"置信度 {_fmt_num(edge.confidence)}")
    return "; ".join(parts)


def graph_to_latex(
    graph: GeometryGraph,
    problem_text: str = "",
    y_up: bool = False,
    axes: bool = False,
) -> str:
    """Convert ``graph`` to a complete LaTeX document string (ctexart).

    The document describes the geometry purely with text and tables -- no
    figure is drawn. Suitable for ``xelatex`` compilation.
    """
    node_by_id: dict[str, Node] = {n.id: n for n in graph.nodes}

    problem_text = problem_text or (graph.goal.statement if graph.goal else "")
    title = _tex_escape(problem_text.strip()) if problem_text else "几何关系审阅"

    lines: list[str] = []
    lines.append(r"\documentclass[UTF8, a4paper, 11pt]{ctexart}")
    lines.append(r"\setCJKmainfont{Noto Serif CJK SC}")
    lines.append(r"\setCJKsansfont{Noto Sans CJK SC}")
    lines.append(r"\setCJKmonofont{Noto Sans Mono CJK SC}[Scale=0.85]")
    lines.append(r"\usepackage{geometry}")
    lines.append(r"\geometry{a4paper, margin=2.2cm}")
    lines.append(r"\usepackage{xcolor}")
    lines.append(r"\usepackage{pifont}")
    lines.append(r"\definecolor{green}{RGB}{0,128,0}")
    lines.append(r"\definecolor{red}{RGB}{200,0,0}")
    lines.append(r"\definecolor{orange}{RGB}{220,120,0}")
    lines.append(r"\usepackage{tikz}")
    lines.append(r"\usepackage{booktabs}")
    lines.append(r"\usepackage{longtable}")
    lines.append(r"\usepackage{array}")
    lines.append(r"\usepackage{setspace}")
    lines.append(r"\onehalfspacing")
    lines.append(r"\usepackage{titlesec}")
    lines.append(r"\titleformat{\section}{\Large\bfseries}{}{0em}{}")
    lines.append(r"\titlespacing*{\section}{0pt}{1.4em}{0.7em}")
    lines.append(r"\usepackage{fancyhdr}")
    lines.append(r"\pagestyle{fancy}")
    lines.append(r"\fancyhf{}")
    lines.append(r"\fancyfoot[C]{\small 第 \thepage\ 页}")
    lines.append(r"\renewcommand{\headrulewidth}{0pt}")
    lines.append(r"\allowdisplaybreaks")
    lines.append(r"\setlength{\parskip}{4pt}")
    lines.append(r"\setlength{\parindent}{0pt}")
    lines.append(r"\definecolor{gauncertain}{rgb}{0.45,0.45,0.45}")
    lines.append(r"\usepackage[colorlinks=true, linkcolor=blue!50!black, urlcolor=blue!60!black, bookmarksnumbered=true]{hyperref}")
    lines.append(r"\title{" + title + "}")
    lines.append(r"\date{}")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")

    if problem_text:
        lines.append(r"\section*{题目}")
        lines.append(_tex_escape(problem_text))
        lines.append("")

    # ----- 几何图形 (TikZ redraw from parsed coords) -----
    tikz = graph_to_tikz(graph, y_up=y_up, axes=axes)
    if tikz:
        lines.append(r"\section*{几何图形（系统重建）}")
        lines.append(r"下图由系统根据解析到的坐标重建，供您核对点线位置是否正确。")
        lines.append(tikz)
        lines.append("")

    # ----- 几何对象 table -----
    lines.append(r"\section*{几何对象}")
    if not graph.nodes:
        lines.append("（无几何对象）")
    else:
        lines.append(r"\begin{longtable}{@{}lll@{}}")
        lines.append(r"\toprule")
        lines.append(r"类型 & 标签 & 关键属性 \\")
        lines.append(r"\midrule")
        lines.append(r"\endhead")
        for n in graph.nodes:
            typ_cn = NODETYPE_CN.get(n.type, n.type.value)
            label = _tex_escape(_label_of(n))
            desc = _tex_escape(_node_attrs_desc(n))
            lines.append(f"{typ_cn} & {label} & {desc} \\\\")
        lines.append(r"\bottomrule")
        lines.append(r"\end{longtable}")
    lines.append("")

    # ----- 几何关系 table -----
    lines.append(r"\section*{几何关系}")
    if not graph.edges:
        lines.append("（无几何关系）")
    else:
        lines.append(r"\begin{longtable}{@{}lllll@{}}")
        lines.append(r"\toprule")
        lines.append(r"关系 & 对象1 & 对象2 & 验证状态 & 证据 \\")
        lines.append(r"\midrule")
        lines.append(r"\endhead")
        for e in graph.edges:
            rel_cn = REL_CN.get(e.rel, e.rel.value)
            obj1 = _tex_escape(_obj_ref_label(node_by_id, e.src))
            obj2 = _tex_escape(_obj_ref_label(node_by_id, e.dst))
            state_cn = VERIFY_CN.get(e.verified, e.verified.value)
            ev = _tex_escape(_edge_evidence(e))
            if e.verified in _UNCERTAIN_STATES:
                rel_cell = r"\textcolor{gauncertain}{\textit{" + _tex_escape(rel_cn) + "}}"
                state_cell = r"\textcolor{gauncertain}{" + _tex_escape(state_cn) + "}"
            else:
                rel_cell = _tex_escape(rel_cn)
                state_cell = _tex_escape(state_cn)
            lines.append(f"{rel_cell} & {obj1} & {obj2} & {state_cell} & {ev} \\\\")
        lines.append(r"\bottomrule")
        lines.append(r"\end{longtable}")
    lines.append("")

    if graph.goal and graph.goal.statement:
        lines.append(r"\section*{求解目标}")
        kind_cn = {"Prove": "证明", "Solve": "求解", "Find": "求"}.get(
            graph.goal.kind, graph.goal.kind)
        lines.append(f"{kind_cn}: {_tex_escape(graph.goal.statement)}")
        lines.append("")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"
