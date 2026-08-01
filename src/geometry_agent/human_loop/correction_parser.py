"""Parse user corrections into graph mutations and apply them.

Two input modes (per :class:`CorrectionType`):

* ``DSL_EDIT`` -- a DSL snippet (optionally prefixed with ``dsl:``). It is
  merged with the current graph's object declarations and parsed via
  :func:`geometry_agent.dsl.parser.from_dsl`; the diff yields add/remove
  actions for nodes and edges.

* ``NATURAL_LANGUAGE`` -- free text. When ``llm_client`` is provided it is
  parsed by the LLM; otherwise a keyword/regex fallback extracts an
  operation (删除/添加/修改), a relation word, and object labels.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..dsl.parser import from_dsl
from ..dsl.serializer import to_dsl
from ..types import (
    Correction,
    CorrectionType,
    Edge,
    GeometryGraph,
    Node,
    NodeType,
    RelType,
    VerifyState,
)

logger = logging.getLogger(__name__)


_REL_KEYWORDS: list[tuple[str, RelType]] = [
    ("垂直", RelType.PERPENDICULAR),
    ("垂线", RelType.PERPENDICULAR),
    ("perpendicular", RelType.PERPENDICULAR),
    ("平行", RelType.PARALLEL),
    ("parallel", RelType.PARALLEL),
    ("相切", RelType.TANGENT),
    ("tangent", RelType.TANGENT),
    ("切线", RelType.TANGENT),
    ("相等", RelType.EQUAL),
    ("等长", RelType.EQUAL),
    ("equal", RelType.EQUAL),
    ("相交", RelType.INTERSECT),
    ("intersect", RelType.INTERSECT),
    ("共线", RelType.COLLINEAR),
    ("collinear", RelType.COLLINEAR),
    ("同心", RelType.CONCENTRIC),
    ("concentric", RelType.CONCENTRIC),
    ("内接", RelType.INSCRIBED),
    ("inscribed", RelType.INSCRIBED),
    ("外接", RelType.CIRCUMSCRIBED),
    ("相似", RelType.SIMILAR),
    ("similar", RelType.SIMILAR),
    ("全等", RelType.CONGRUENT),
    ("congruent", RelType.CONGRUENT),
    ("在.*上", RelType.ON),
    ("on", RelType.ON),
    ("在.*内", RelType.INSIDE),
    ("inside", RelType.INSIDE),
    ("圆心", RelType.CENTER),
    ("center", RelType.CENTER),
    ("切点", RelType.TANGENT_POINT),
]

_OP_KEYWORDS = {
    "remove": ["删除", "去掉", "移除", "去除", "remove", "delete"],
    "add": ["添加", "增加", "新增", "加上", "add"],
    "mark_uncertain": ["修改", "改为不确定", "存疑", "存疑", "uncertain"],
}

_LABEL_RE = re.compile(r"\b([A-Z]{1,6})\b")


def _node_id_for_label(graph: GeometryGraph, label: str) -> str | None:
    for n in graph.nodes:
        if n.label == label:
            return n.id
    return None


def _resolve_obj(graph: GeometryGraph, label: str) -> str | None:
    """Resolve a label to a node id, preferring non-Point objects for
    multi-letter labels (e.g. ``AB`` is a segment), but allowing single
    letters to match points."""
    matches = [n for n in graph.nodes if n.label == label]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0].id
    if len(label) > 1:
        non_point = [n for n in matches if n.type != NodeType.POINT]
        if non_point:
            return non_point[0].id
    return matches[0].id


def _strip_dsl_prefix(text: str) -> str:
    t = text.strip()
    if t.lower().startswith("dsl:"):
        return t[4:].lstrip()
    return t


def _parse_dsl_correction(text: str, graph: GeometryGraph) -> list[dict[str, Any]]:
    """Parse a user DSL snippet into add/remove actions.

    The snippet is *additive*: relations it declares become ``add_edge``
    actions. Removals are expressed with ``# remove: <RelExpr>`` comment
    lines, which become ``remove_edge`` actions. Object declarations in the
    snippet that are not already in the graph become ``add_node`` actions.

    To resolve object references, the snippet is merged with the existing
    graph's object declarations before parsing.
    """
    snippet = _strip_dsl_prefix(text)

    # Split out `# remove: <expr>` lines (the rest is additive DSL).
    remove_exprs: list[str] = []
    kept_lines: list[str] = []
    for ln in snippet.splitlines():
        m = re.match(r"^\s*#\s*remove\s*:\s*(.+?)\s*$", ln, re.IGNORECASE)
        if m:
            remove_exprs.append(m.group(1).strip())
        else:
            kept_lines.append(ln)
    add_snippet = "\n".join(kept_lines).strip()

    existing_obj_lines: list[str] = ["Objects:"]
    for n in graph.nodes:
        existing_obj_lines.append("  - " + _node_to_dsl_decl(n))
    existing_objs_block = "\n".join(existing_obj_lines)

    actions: list[dict[str, Any]] = []

    # ----- adds: merge objects + user snippet, parse, diff -----
    if add_snippet:
        if "Objects:" in add_snippet:
            merged = add_snippet
        else:
            merged = existing_objs_block + "\n" + add_snippet
        try:
            new_graph = from_dsl(merged)
        except Exception as exc:
            logger.warning("DSL correction parse failed (%s); skipping adds", exc)
            new_graph = None
        if new_graph is not None:
            old_node_ids = {n.id for n in graph.nodes}
            for n in new_graph.nodes:
                if n.id not in old_node_ids:
                    actions.append({"op": "add_node", "node": n.model_dump()})
            # every edge in the parsed snippet is an add (the snippet is additive)
            for e in new_graph.edges:
                actions.append({
                    "op": "add_edge",
                    "src": e.src,
                    "dst": e.dst,
                    "rel": e.rel.value,
                    "verified": e.verified.value,
                    "attrs": dict(e.attrs),
                })

    # ----- removes: parse each `# remove: <expr>` against existing objects -----
    for expr in remove_exprs:
        wrapped = existing_objs_block + "\nRelations:\n  - " + expr
        try:
            parsed = from_dsl(wrapped)
        except Exception as exc:
            logger.warning("DSL remove parse failed for %r: %s", expr, exc)
            continue
        for e in parsed.edges:
            actions.append({
                "op": "remove_edge",
                "src": e.src,
                "dst": e.dst,
                "rel": e.rel.value,
            })
    return actions


def _node_to_dsl_decl(node: Node) -> str:
    t = node.type
    label = node.label or node.id
    a = node.attrs
    if t == NodeType.POINT:
        c = a.get("coords")
        if c is not None:
            return f"Point({label}): [{_n(c[0])}, {_n(c[1])}]"
        return f"Point({label})"
    if t == NodeType.CIRCLE:
        return f"Circle({label}, r={_n(a.get('radius', 0.0))})"
    if t == NodeType.ARC:
        p1 = a.get("p1")
        p2 = a.get("p2")
        if p1 and p2:
            return f"Arc({label}, {p1}, {p2})"
        return f"Arc({label})"
    if t == NodeType.ELLIPSE:
        c = a.get("center")
        cstr = f"[{_n(c[0])}, {_n(c[1])}]" if c is not None else "[0, 0]"
        return (f"Ellipse({label}, {cstr}, {_n(a.get('semi_major', 0.0))}, "
                f"{_n(a.get('semi_minor', 0.0))}, {_n(a.get('rotation', 0.0))})")
    if t == NodeType.LINE:
        return f"Line({label})"
    if t == NodeType.RAY:
        return f"Ray({label})"
    if t == NodeType.SEGMENT:
        return f"Segment({label})"
    if t == NodeType.POLYGON:
        verts = a.get("vertices_labels") or []
        if verts:
            return f"Polygon({label}, {', '.join(verts)})"
        return f"Polygon({label})"
    return f"{t.value}({label})"


def _n(x: Any) -> str:
    f = float(x)
    return str(int(f)) if f.is_integer() else f"{f:g}"


def _parse_nl_with_llm(text: str, graph: GeometryGraph, llm_client: Any) -> list[dict[str, Any]]:
    """Use an LLM client (OpenAI-compatible) to parse natural-language
    corrections into a list of action dicts. The LLM is asked to return
    JSON; on any failure we fall back to keyword parsing."""
    import json
    node_list = [
        {"id": n.id, "type": n.type.value, "label": n.label or n.id}
        for n in graph.nodes
    ]
    edge_list = [
        {"src": e.src, "dst": e.dst, "rel": e.rel.value, "verified": e.verified.value}
        for e in graph.edges
    ]
    prompt = (
        "你是几何关系纠错助手。根据用户的自然语言反馈，输出 JSON 动作列表。\n"
        "可用动作:\n"
        '  {"op":"add_edge","src":"<nodeId>","dst":"<nodeId>","rel":"<RelType>"}\n'
        '  {"op":"remove_edge","src":"<nodeId>","dst":"<nodeId>","rel":"<RelType>"}\n'
        '  {"op":"mark_uncertain","src":"<nodeId>","dst":"<nodeId>","rel":"<RelType>"}\n'
        '  {"op":"add_node","node":{"id":"...","type":"Point","label":"X","attrs":{}}}\n'
        "RelType 取值: On, Center, Collinear, Intersect, Tangent, Parallel, "
        "Perpendicular, Equal, Inside, Outside, Concentric, TangentPoint, "
        "Inscribed, Circumscribed, SameArc, Similar, Congruent.\n"
        "只输出 JSON 数组,不要解释。\n\n"
        f"当前图节点:\n{json.dumps(node_list, ensure_ascii=False)}\n\n"
        f"当前图边:\n{json.dumps(edge_list, ensure_ascii=False)}\n\n"
        f"用户反馈:\n{text}\n"
    )
    try:
        if hasattr(llm_client, "chat") and hasattr(llm_client.chat, "completions"):
            resp = llm_client.chat.completions.create(
                model=getattr(llm_client, "model", None) or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = resp.choices[0].message.content or ""
        else:
            content = llm_client(prompt)
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        actions = json.loads(content)
        if isinstance(actions, dict):
            actions = [actions]
        return actions if isinstance(actions, list) else []
    except Exception as exc:
        logger.warning("LLM correction parse failed (%s); using keyword fallback", exc)
        return _parse_nl_with_keywords(text, graph)


def _parse_nl_with_keywords(text: str, graph: GeometryGraph) -> list[dict[str, Any]]:
    """Regex/keyword fallback parser. Recognises an operation verb, a
    relation word, and one or more uppercase labels. Returns a list of
    action dicts."""
    lower = text.lower()
    op = None
    for op_name, kws in _OP_KEYWORDS.items():
        if any(kw in lower or kw in text for kw in kws):
            op = op_name
            break
    if op is None:
        op = "add"

    rel: RelType | None = None
    for kw, r in _REL_KEYWORDS:
        if re.search(kw, text, re.IGNORECASE):
            rel = r
            break
    if rel is None:
        logger.warning("NL correction: no relation keyword in %r", text)
        return []

    labels = _LABEL_RE.findall(text)
    if not labels:
        logger.warning("NL correction: no object labels in %r", text)
        return []

    resolved = []
    for lab in labels:
        nid = _resolve_obj(graph, lab)
        if nid is None:
            logger.warning("NL correction: object label %r not found in graph", lab)
            continue
        resolved.append(nid)
    if len(resolved) < 2:
        return []

    src, dst = resolved[0], resolved[1]
    if op == "remove":
        return [{"op": "remove_edge", "src": src, "dst": dst, "rel": rel.value}]
    if op == "mark_uncertain":
        return [{"op": "mark_uncertain", "src": src, "dst": dst, "rel": rel.value}]
    return [{"op": "add_edge", "src": src, "dst": dst, "rel": rel.value,
             "verified": VerifyState.TRUE.value, "attrs": {}}]


def parse_correction(
    text: str,
    mode: CorrectionType,
    graph: GeometryGraph,
    llm_client: Any = None,
) -> Correction:
    """Parse ``text`` into a :class:`Correction` with executable actions."""
    if mode == CorrectionType.SKIP:
        return Correction(kind=CorrectionType.SKIP, text=text, actions=[])

    if mode == CorrectionType.DSL_EDIT:
        actions = _parse_dsl_correction(text, graph)
        return Correction(kind=CorrectionType.DSL_EDIT, text=text, actions=actions)

    if mode == CorrectionType.NATURAL_LANGUAGE:
        if llm_client is not None:
            actions = _parse_nl_with_llm(text, graph, llm_client)
        else:
            actions = _parse_nl_with_keywords(text, graph)
        return Correction(kind=CorrectionType.NATURAL_LANGUAGE, text=text, actions=actions)

    return Correction(kind=CorrectionType.SKIP, text=text, actions=[])


def apply_corrections(graph: GeometryGraph, corrections: list[Correction]) -> GeometryGraph:
    """Apply a list of :class:`Correction` actions to ``graph``.

    Returns a *new* graph (the input is not mutated). Unknown node ids are
    skipped with a warning rather than raising.
    """
    import copy
    new_graph = graph.model_copy(deep=True)
    node_ids = {n.id for n in new_graph.nodes}
    label_to_id = {n.label: n.id for n in new_graph.nodes if n.label}

    def _resolve(ref: str) -> str | None:
        if ref in node_ids:
            return ref
        return label_to_id.get(ref)

    for corr in corrections:
        for act in corr.actions:
            try:
                op = act.get("op")
                if op == "add_node":
                    node_data = act.get("node") or {}
                    nid = node_data.get("id") or _id_from_label(node_data)
                    if not nid:
                        logger.warning("add_node without id/label: %r", act)
                        continue
                    if nid in node_ids:
                        logger.warning("add_node: node %s already exists, skipping", nid)
                        continue
                    node = Node(**node_data) if "type" in node_data else Node(
                        id=nid,
                        type=NodeType(node_data.get("type", "Point")),
                        label=node_data.get("label"),
                        attrs=node_data.get("attrs", {}),
                    )
                    new_graph.nodes.append(node)
                    node_ids.add(nid)
                    if node.label:
                        label_to_id.setdefault(node.label, nid)
                elif op == "add_edge":
                    src = _resolve(act.get("src", ""))
                    dst = _resolve(act.get("dst", ""))
                    if not src or not dst:
                        logger.warning("add_edge: unresolved src/dst in %r", act)
                        continue
                    rel = _coerce_rel(act.get("rel"))
                    if rel is None:
                        logger.warning("add_edge: unknown rel %r", act.get("rel"))
                        continue
                    verified = _coerce_verified(act.get("verified", "true"))
                    attrs = act.get("attrs") or {}
                    if not any(e.src == src and e.dst == dst and e.rel == rel
                               for e in new_graph.edges):
                        new_graph.edges.append(Edge(
                            src=src, dst=dst, rel=rel,
                            verified=verified,
                            attrs=dict(attrs),
                        ))
                elif op == "remove_edge":
                    src = _resolve(act.get("src", ""))
                    dst = _resolve(act.get("dst", ""))
                    rel = _coerce_rel(act.get("rel"))
                    if not src or not dst or rel is None:
                        logger.warning("remove_edge: unresolved ref in %r", act)
                        continue
                    before = len(new_graph.edges)
                    new_graph.edges = [
                        e for e in new_graph.edges
                        if not (e.src == src and e.dst == dst and e.rel == rel)
                    ]
                    if len(new_graph.edges) == before:
                        logger.warning("remove_edge: no matching edge for %r", act)
                elif op == "mark_uncertain":
                    src = _resolve(act.get("src", ""))
                    dst = _resolve(act.get("dst", ""))
                    rel = _coerce_rel(act.get("rel"))
                    if not src or not dst or rel is None:
                        continue
                    hit = False
                    for e in new_graph.edges:
                        if e.src == src and e.dst == dst and e.rel == rel:
                            e.verified = VerifyState.UNCERTAIN
                            hit = True
                    if not hit:
                        logger.warning("mark_uncertain: no matching edge for %r", act)
                else:
                    logger.warning("unknown correction op: %r", op)
            except Exception as exc:
                logger.warning("correction action failed (%s): %r", exc, act)
                continue
    return new_graph


def _id_from_label(node_data: dict[str, Any]) -> str | None:
    label = node_data.get("label")
    if not label:
        return None
    t = node_data.get("type", "Point")
    prefix = {
        "Point": "P", "Segment": "S", "Line": "L", "Ray": "R",
        "Circle": "C", "Arc": "A", "Ellipse": "E", "Polygon": "Poly",
    }.get(t, "N")
    return f"{prefix}_{label}"


def _coerce_rel(val: Any) -> RelType | None:
    if val is None:
        return None
    try:
        return RelType(val)
    except Exception:
        try:
            return RelType(str(val).capitalize())
        except Exception:
            return None


def _coerce_verified(val: Any) -> VerifyState:
    try:
        return VerifyState(val)
    except Exception:
        return VerifyState.TRUE
