"""High-level facade: classify subject, retrieve from local DB with on-demand web
fallback, and format retrieved knowledge as a prompt fragment.

Supports three grade levels (junior / senior / competition) with a
subject-grade compatibility matrix:
  - 平面几何:    初中 / 高中 / 竞赛
  - 解析几何:         高中 / 竞赛  (初中无圆锥曲线)
  - 立体几何:         高中          (仅高中)
  - 函数导数:         高中 / 竞赛
  - 解三角形:   初中 / 高中 / 竞赛

When the user-selected grade is incompatible with the detected subject,
``resolve_grade`` auto-escalates to the minimum compatible grade.
The tool set is identical across grades.
"""

from __future__ import annotations

from typing import Optional

from ..config import KnowledgeConfig
from ..types import GradeLevel, MethodPriority, SubjectType, RetrievedKnowledge
from .db import KnowledgeDB
from .subject_classifier import classify_subject
from .web_retriever import WebRetriever

_PRIORITY_LABEL = {
    MethodPriority.IN_CLASS: "课内方法(推荐优先尝试)",
    MethodPriority.ADVANCED: "高等几何方法",
    MethodPriority.MACHINE: "机器证明方法",
}

_GRADE_PROMPT = {
    GradeLevel.JUNIOR: (
        "【学段: 初中】必须使用初中课内方法求解，禁止使用坐标法/解析几何/向量法/"
        "高等几何/导数。"
        "可用方法：射影定理、相似三角形、勾股定理、面积法、共高/共底定理、"
        "平行线分线段成比例、圆周角/切线定理、正弦/余弦定理（基础）等。"
    ),
    GradeLevel.SENIOR: (
        "【学段: 高中】优先使用高中课内方法（含向量法、坐标法、空间向量、导数）。"
        "允许适度使用高等几何（射影/仿射/复数法）作为补充，但课内方法优先。"
    ),
    GradeLevel.COMPETITION: (
        "【学段: 竞赛】可使用全部方法：课内方法、高等几何（射影/仿射/复数法/极坐标）、"
        "竞赛技巧（配点、引理、极端原理、解析法+齐次化）、机器证明等。"
        "鼓励选择最优雅的方法，但必须给出完整严格的推导。"
    ),
}

# Subject-grade compatibility: which grades are valid for each subject.
_SUBJECT_GRADES = {
    SubjectType.PLANE_GEOMETRY: {GradeLevel.JUNIOR, GradeLevel.SENIOR, GradeLevel.COMPETITION},
    SubjectType.TRIANGLE_SOLVING: {GradeLevel.JUNIOR, GradeLevel.SENIOR, GradeLevel.COMPETITION},
    SubjectType.ANALYTIC_GEOMETRY: {GradeLevel.SENIOR, GradeLevel.COMPETITION},
    SubjectType.SOLID_GEOMETRY: {GradeLevel.SENIOR},
    SubjectType.FUNCTION_DERIVATIVE: {GradeLevel.SENIOR, GradeLevel.COMPETITION},
    SubjectType.PROBABILITY: {GradeLevel.SENIOR, GradeLevel.COMPETITION},
    SubjectType.SEQUENCE: {GradeLevel.SENIOR, GradeLevel.COMPETITION},
}

# Grade ordering for escalation.
_GRADE_ORDER = [GradeLevel.JUNIOR, GradeLevel.SENIOR, GradeLevel.COMPETITION]


def resolve_grade(subject: SubjectType, grade: GradeLevel) -> tuple[GradeLevel, str]:
    """Resolve the effective grade for a subject.

    If ``grade`` is compatible with ``subject``, return it as-is.
    Otherwise, escalate to the minimum compatible grade and return a note.

    Returns:
        (effective_grade, note) — note is "" when no escalation happened.
    """
    valid = _SUBJECT_GRADES.get(subject, {GradeLevel.SENIOR})
    if grade in valid:
        return grade, ""
    # escalate to minimum compatible grade
    for g in _GRADE_ORDER:
        if g in valid:
            subject_name = {
                SubjectType.ANALYTIC_GEOMETRY: "解析几何",
                SubjectType.SOLID_GEOMETRY: "立体几何",
                SubjectType.FUNCTION_DERIVATIVE: "函数导数",
                SubjectType.PROBABILITY: "概率与统计",
                SubjectType.SEQUENCE: "数列与排列组合",
            }.get(subject, subject.value)
            return g, f"注意：{subject_name}不适用{grade.value}级别，已自动调整为{g.value}级别。"
    return GradeLevel.SENIOR, ""


class KnowledgeManager:
    """Combines KnowledgeDB + classifier + WebRetriever into a single facade."""

    def __init__(
        self,
        config: Optional[KnowledgeConfig] = None,
        db: Optional[KnowledgeDB] = None,
        web_retriever: Optional[WebRetriever] = None,
    ):
        self.config = config or KnowledgeConfig()
        self.web_retriever = web_retriever or WebRetriever(self.config)
        self.db = db or KnowledgeDB(self.config, web_retriever=self.web_retriever)

    def get_knowledge(
        self,
        problem_text: str,
        dsl: str = "",
        grade: GradeLevel = GradeLevel.SENIOR,
    ) -> RetrievedKnowledge:
        """Retrieve knowledge scoped to ``grade``.

        If the subject is incompatible with ``grade``, the grade is
        auto-escalated via :func:`resolve_grade`.
        """
        subject = classify_subject(problem_text, dsl)
        effective_grade, _ = resolve_grade(subject, grade)

        knowledge = self.db.retrieve(query=problem_text, subject=subject)

        # Filter entries/methods by grade level.
        # - JUNIOR: keep only junior-grade items
        # - SENIOR: keep junior + senior items
        # - COMPETITION: keep all items
        valid_grades = {GradeLevel.JUNIOR}
        if effective_grade in (GradeLevel.SENIOR, GradeLevel.COMPETITION):
            valid_grades.add(GradeLevel.SENIOR)
        if effective_grade == GradeLevel.COMPETITION:
            valid_grades.add(GradeLevel.COMPETITION)

        knowledge.entries = [
            e for e in knowledge.entries if e.grade in valid_grades
        ]
        knowledge.methods = [
            m for m in knowledge.methods if m.grade in valid_grades
        ]
        return knowledge

    def grade_prompt(self, grade: GradeLevel) -> str:
        return _GRADE_PROMPT.get(grade, _GRADE_PROMPT[GradeLevel.SENIOR])

    def format_for_prompt(
        self,
        knowledge: RetrievedKnowledge,
        grade: GradeLevel = GradeLevel.SENIOR,
    ) -> str:
        lines: list[str] = []
        subject_label = {
            "plane_geometry": "平面几何",
            "triangle_solving": "解三角形",
            "analytic_geometry": "解析几何",
            "solid_geometry": "立体几何",
            "function_derivative": "函数与导数",
            "probability": "概率与统计",
            "sequence": "数列与排列组合",
        }.get(knowledge.topic.value, knowledge.topic.value)

        # Resolve effective grade + escalation note
        effective_grade, note = resolve_grade(knowledge.topic, grade)
        grade_label = {
            GradeLevel.JUNIOR: "初中",
            GradeLevel.SENIOR: "高中",
            GradeLevel.COMPETITION: "竞赛",
        }.get(effective_grade, "高中")

        lines.append(f"# 学科: {subject_label} | 学段: {grade_label}")
        if note:
            lines.append(f"# {note}")
        lines.append(self.grade_prompt(effective_grade))
        if knowledge.from_web:
            lines.append("# (已联网补充知识)")

        if knowledge.methods:
            lines.append("")
            lines.append("## 推荐方法 (按优先级排序, 课内方法优先尝试)")
            for i, m in enumerate(knowledge.methods, 1):
                label = _PRIORITY_LABEL.get(m.priority, m.priority.name)
                tag = " [推荐优先尝试]" if m.priority == MethodPriority.IN_CLASS else ""
                hint = f"（提示：{m.proof_hint}）" if getattr(m, "proof_hint", "") else ""
                lines.append(f"{i}. {m.name}{hint} ({label}){tag}")
                if m.description:
                    lines.append(f"   - 说明: {m.description}")
                if m.applicable_when:
                    lines.append("   - 适用: " + "、".join(m.applicable_when))
                if m.steps:
                    lines.append("   - 步骤: " + " → ".join(m.steps))

        if knowledge.entries:
            lines.append("")
            lines.append("## 相关知识点")
            for i, e in enumerate(knowledge.entries, 1):
                src = "联网" if e.source == "web" else "课内"
                hint = f"（提示：{e.proof_hint}）" if e.proof_hint else ""
                lines.append(f"{i}. {e.title}{hint} [{src}]")
                content = e.content.replace("\n", " ")
                if len(content) > 160:
                    content = content[:160] + "…"
                lines.append(f"   - {content}")

        return "\n".join(lines)


__all__ = ["KnowledgeManager", "resolve_grade"]
