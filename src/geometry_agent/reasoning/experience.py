"""Experience memory: extract, store, and retrieve problem-solving experience.

After each problem attempt (success or failure), the system extracts lessons
learned — which methods worked, which failed, what pitfalls were hit. These
are stored as :class:`ExperienceEntry` records and retrieved for similar
future problems, creating a learning loop.

This implements the "experience extraction + reflection" capability:
- 成功经验: what method led to the solution
- 失败经验: what was tried and why it failed
- 通用教训: pitfalls applicable across problems
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..types import ProofPlan, Solution, SubjectType, ToolCall


class ExperienceEntry:
    """A single lesson learned from solving (or failing) a problem."""

    def __init__(
        self,
        problem_text: str,
        subject: str,
        grade: str,
        success: bool,
        method_used: str = "",
        failed_methods: list[str] | None = None,
        lesson: str = "",
        key_steps: list[str] | None = None,
        pitfalls: list[str] | None = None,
    ):
        self.problem_text = problem_text[:300]
        self.subject = subject
        self.grade = grade
        self.success = success
        self.method_used = method_used
        self.failed_methods = failed_methods or []
        self.lesson = lesson
        self.key_steps = key_steps or []
        self.pitfalls = pitfalls or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_text": self.problem_text,
            "subject": self.subject,
            "grade": self.grade,
            "success": self.success,
            "method_used": self.method_used,
            "failed_methods": self.failed_methods,
            "lesson": self.lesson,
            "key_steps": self.key_steps,
            "pitfalls": self.pitfalls,
        }

    def __repr__(self):
        status = "✓" if self.success else "✗"
        return f"Experience({status} {self.subject} method={self.method_used})"


class ExperienceMemory:
    """In-memory store of solving experiences, with simple keyword retrieval."""

    def __init__(self, max_entries: int = 200):
        self.entries: list[ExperienceEntry] = []
        self.max_entries = max_entries

    def add(self, entry: ExperienceEntry) -> None:
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)  # FIFO eviction

    def retrieve(self, problem_text: str, subject: str = "", top_k: int = 3) -> list[ExperienceEntry]:
        """Retrieve relevant past experiences by keyword overlap."""
        if not self.entries:
            return []
        query_words = set(re.findall(r"\w+", problem_text.lower()))

        def score(e: ExperienceEntry) -> int:
            s = 0
            if subject and e.subject == subject:
                s += 10
            entry_words = set(re.findall(r"\w+", e.problem_text.lower()))
            s += len(query_words & entry_words)
            # Successful experiences are slightly more valuable
            if e.success:
                s += 1
            return s

        ranked = sorted(self.entries, key=score, reverse=True)
        # Only return entries with score > 0
        return [e for e in ranked[:top_k] if score(e) > 0]

    def format_for_prompt(self, problem_text: str, subject: str = "") -> str:
        """Format retrieved experiences as a prompt fragment."""
        relevant = self.retrieve(problem_text, subject)
        if not relevant:
            return ""
        lines = ["[过往经验参考]"]
        for i, e in enumerate(relevant, 1):
            status = "成功" if e.success else "失败"
            lines.append(f"{i}. [{status}] {e.subject} 题: {e.method_used}")
            if e.lesson:
                lines.append(f"   经验: {e.lesson}")
            if e.pitfalls:
                for p in e.pitfalls:
                    lines.append(f"   易错: {p}")
            if e.key_steps and e.success:
                lines.append(f"   关键步骤: {' → '.join(e.key_steps[:3])}")
        return "\n".join(lines) + "\n\n"


# =====================================================================================
# Experience extraction from a completed solving attempt
# =====================================================================================
def extract_experience(
    problem_text: str,
    subject: str,
    grade: str,
    plan: ProofPlan,
    solution: Solution,
    tool_calls: list[ToolCall] | None = None,
) -> ExperienceEntry:
    """Analyze a solving attempt and extract an :class:`ExperienceEntry`.

    Examines the proof plan, tool call log, and solution to determine:
    - Was it successful? (solution.verified or confidence > 0.5)
    - What method was used? (from proof steps' reasons)
    - What methods failed? (from reflect tool calls / failed verifies)
    - What was the key insight? (from the last verified step)
    - What pitfalls were hit? (from failed tool calls)
    """
    tool_calls = tool_calls or plan.tool_calls or []
    success = solution.verified or solution.confidence >= 0.5

    # Extract method used from proof steps
    method_used = ""
    all_reasons = " ".join(st.reason for st in plan.plan if st.reason)
    method_keywords = {
        "射影定理": "射影定理", "相似": "相似三角形", "勾股": "勾股定理",
        "面积法": "面积法", "共高": "共高定理", "共底": "共底定理",
        "等积变换": "等积变换", "切线": "切线定理", "圆周角": "圆周角定理",
        "坐标法": "坐标法", "向量": "向量法", "复数法": "复数法",
        "射影几何": "射影几何", "仿射": "仿射变换",
        "导数": "导数法", "构造函数": "构造函数法", "分离参数": "分离参数法",
        "韦达定理": "韦达定理", "结式": "结式消元",
    }
    for kw, method_name in method_keywords.items():
        if kw in all_reasons:
            method_used = method_name
            break

    # Extract failed methods from tool calls
    failed_methods: list[str] = []
    pitfalls: list[str] = []
    for tc in tool_calls:
        res = tc.result
        if isinstance(res, dict):
            verified = res.get("verified")
            if verified is False or str(verified) == "false":
                failed_methods.append(f"{tc.name}({tc.args})")
            # Check for common pitfalls in error messages
            err = str(res.get("error", ""))
            if "平方" in err or "开方" in err:
                pitfalls.append("面积比与线段比转换时注意平方/开方")
            if "共高" in err or "collinear" in err.lower():
                pitfalls.append("确认共高条件: 高必须落在同一直线或平行线上")

    # Extract key steps from successful proof
    key_steps: list[str] = []
    for st in plan.plan:
        if st.verified and st.statement:
            key_steps.append(st.statement[:80])

    # Generate lesson
    lesson = ""
    if success:
        if method_used:
            lesson = f"用{method_used}成功求解。"
        if key_steps:
            lesson += f" 关键步骤: {key_steps[-1][:60]}"
    else:
        if failed_methods:
            lesson = f"尝试了{', '.join(failed_methods[:3])}但未成功。"
        lesson += " 需要尝试其他方法或构造辅助线。"

    return ExperienceEntry(
        problem_text=problem_text,
        subject=subject,
        grade=grade,
        success=success,
        method_used=method_used,
        failed_methods=failed_methods,
        lesson=lesson,
        key_steps=key_steps,
        pitfalls=pitfalls,
    )


# =====================================================================================
# Reflection: generate a self-reflection summary after solving
# =====================================================================================
def generate_reflection_summary(
    problem_text: str,
    plan: ProofPlan,
    solution: Solution,
    experience: ExperienceEntry,
) -> str:
    """Generate a human-readable reflection summary after a solving attempt.

    This is stored alongside the solution and can be included in the PDF report
    or displayed to the user.
    """
    lines = ["【反思总结】"]

    if experience.success:
        lines.append(f"本题成功用{experience.method_used or '综合方法'}求解。")
    else:
        lines.append("本题未能完全求解。")

    if experience.key_steps:
        lines.append("")
        lines.append("关键步骤:")
        for i, step in enumerate(experience.key_steps, 1):
            lines.append(f"  {i}. {step}")

    if experience.failed_methods:
        lines.append("")
        lines.append("尝试过但失败的方法:")
        for fm in experience.failed_methods:
            lines.append(f"  - {fm}")

    if experience.pitfalls:
        lines.append("")
        lines.append("易错点:")
        for p in experience.pitfalls:
            lines.append(f"  - {p}")

    if experience.lesson:
        lines.append("")
        lines.append(f"经验教训: {experience.lesson}")

    # Suggest improvements
    if not experience.success:
        lines.append("")
        lines.append("改进建议:")
        lines.append("  - 尝试不同的辅助线构造")
        lines.append("  - 考虑面积法或坐标法")
        lines.append("  - 检查是否有遗漏的已知条件")

    return "\n".join(lines)


__all__ = [
    "ExperienceEntry",
    "ExperienceMemory",
    "extract_experience",
    "generate_reflection_summary",
]
