#!/usr/bin/env python3
"""Geometry Agent Web UI — Gradio-based web interface.

Launch:
  python web_ui.py
Then open http://localhost:7860 in your browser.

Features:
  - 输入题目文本, 选择学段, 点击"求解"即出答案+PDF
  - 多小题模式: 一道大题多个小问, 合并出一个PDF
  - 实时显示解题步骤和工具调用
  - PDF下载链接
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.exists():
    sys.path.insert(0, str(_src))

import gradio as gr

from geometry_agent.config import load_settings
from geometry_agent.pipeline import GeometryPipeline
from geometry_agent.types import GradeLevel, Solution
from geometry_agent.human_loop.pdf_compiler import solution_to_pdf, multi_question_to_pdf
from geometry_agent.normalize import normalize_problem_text
from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
from geometry_agent.reasoning.experience import ExperienceMemory
from geometry_agent_cli import _numeric_verify_fixed_point

# Global pipeline instance (reused across requests)
_pipeline = None


def _load_settings(config_path=None):
    """Load settings, defaulting to configs/default.yaml."""
    if config_path:
        return load_settings(config_path)
    for p in ["configs/default.yaml", "src/geometry_agent/configs/default.yaml"]:
        if Path(p).exists():
            return load_settings(p)
    return load_settings()


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        s = _load_settings(None)
        s.human_loop.enabled = False
        s.llm.max_tool_calls = 40
        _pipeline = GeometryPipeline(s)
    return _pipeline


def extract_answer(plan) -> Solution:
    sol = Solution(
        answer="",
        proof=plan.plan,
        confidence=sum(1 for st in plan.plan if st.verified) / max(len(plan.plan), 1),
        verified=any(st.verified for st in plan.plan),
    )
    for st in reversed(plan.plan):
        if st.verified and st.statement:
            sol.answer = st.statement[:80]
            break
    return sol


def solve_single(problem_text, grade_str, show_steps):
    """Solve a single problem."""
    problem_text = normalize_problem_text(problem_text)
    if not problem_text.strip():
        return "请输入题目文本", None

    grade_map = {"初中": GradeLevel.JUNIOR, "高中": GradeLevel.SENIOR, "竞赛": GradeLevel.COMPETITION}
    grade = grade_map.get(grade_str, GradeLevel.SENIOR)

    p = get_pipeline()
    tools = p._tools(None) if hasattr(p, "_tools") else {}

    t0 = time.time()
    sol = None
    retry_log = []
    try:
        for attempt in range(3):
            agent = EnhancedReasoningAgent(
                p.settings.llm, tools={},
                knowledge_manager=p.knowledge_manager,
                grade=grade,
                experience_memory=ExperienceMemory(),
            )
            plan = agent.reason("", problem_text, tools)
            sol = extract_answer(plan)
            good = sol.confidence >= 0.5 and len(sol.proof) >= 2
            if good and ("定点" in problem_text or "过定点" in problem_text or "恒过" in problem_text):
                good = _numeric_verify_fixed_point(problem_text, sol.answer, tools)
            if good:
                break
            if attempt < 2:
                reason = "置信度低" if sol.confidence < 0.5 else "数值校验失败"
                retry_log.append(f"- {reason}, 已重试 {attempt+2}/3")
    except Exception as e:
        return f"## ❌ 求解失败\n\n题目解析或推理出错，请检查题目表述后重试。\n\n> 错误信息: {e}", None
    elapsed = time.time() - t0

    if sol is None:
        return "## ❌ 求解失败\n\n多次尝试后仍无法给出可靠解答，请检查题目表述。", None

    lines = [
        f"## 解题结果\n",
        f"- 耗时: {elapsed:.1f} 秒",
        f"- 步数: {len(sol.proof)}",
        f"- 置信度: {sol.confidence:.2f}",
        f"- **答案: {sol.answer}**\n",
    ]
    if retry_log:
        lines.append("**重试记录**")
        lines.extend(retry_log)
        lines.append("")

    if show_steps and sol.proof:
        lines.append("### 解题步骤\n")
        for i, st in enumerate(sol.proof, 1):
            mark = "✅" if st.verified else "⭕"
            lines.append(f"**第{i}步** {mark} {st.statement}")
            if st.reason:
                lines.append(f"  - 理由: {st.reason}")
            lines.append("")

    result_text = "\n".join(lines)

    try:
        out_dir = Path("outputs")
        out_dir.mkdir(exist_ok=True)
        pdf_path = solution_to_pdf(
            problem_text, sol, None,
            str(out_dir / f"解答_{int(time.time())}.pdf"),
            "几何题解答报告",
        )
    except Exception as e:
        return result_text + f"\n\n## ⚠️ PDF 生成失败\n\n> {e}", None

    return result_text, pdf_path


def solve_multi(problem_text, sub_questions_text, grade_str):
    """Solve a multi-sub-question problem."""
    problem_text = normalize_problem_text(problem_text)
    if not problem_text.strip():
        return "请输入题干", None

    subs = [normalize_problem_text(s.strip()) for s in sub_questions_text.strip().split("\n") if s.strip()]
    if not subs:
        return "请输入至少一个小题", None

    grade_map = {"初中": GradeLevel.JUNIOR, "高中": GradeLevel.SENIOR, "竞赛": GradeLevel.COMPETITION}
    grade = grade_map.get(grade_str, GradeLevel.SENIOR)

    p = get_pipeline()
    tools = p._tools(None) if hasattr(p, "_tools") else {}

    results = []
    lines = [f"## 解题结果 ({len(subs)} 小题)\n"]

    for i, sub_text in enumerate(subs):
        label = f"({i+1})"
        full_text = problem_text + " " + sub_text
        t0 = time.time()
        sol = None
        try:
            for attempt in range(3):
                agent = EnhancedReasoningAgent(
                    p.settings.llm, tools={},
                    knowledge_manager=p.knowledge_manager,
                    grade=grade,
                    experience_memory=ExperienceMemory(),
                )
                plan = agent.reason("", full_text, tools)
                sol = extract_answer(plan)
                if sol.confidence >= 0.5 and len(sol.proof) >= 2:
                    break
        except Exception as e:
            lines.append(f"### {label} {sub_text}")
            lines.append(f"- ❌ 求解出错: {e}\n")
            continue
        elapsed = time.time() - t0
        lines.append(f"### {label} {sub_text}")
        lines.append(f"- 耗时: {elapsed:.0f}s | 步数: {len(sol.proof)} | 置信度: {sol.confidence:.2f}")
        lines.append(f"- **答案: {sol.answer}**\n")
        results.append({"label": label, "question": sub_text, "solution": sol})

    result_text = "\n".join(lines)

    if not results:
        return result_text + "\n## ❌ 所有小题均求解失败", None

    try:
        out_dir = Path("outputs")
        out_dir.mkdir(exist_ok=True)
        pdf_path = multi_question_to_pdf(
            problem_text, results, None,
            str(out_dir / f"解答_{int(time.time())}.pdf"),
            "几何题解答报告",
        )
    except Exception as e:
        return result_text + f"\n\n## ⚠️ PDF 生成失败\n\n> {e}", None

    return result_text, pdf_path


def build_ui():
    with gr.Blocks(
        title="Geometry Agent — AI几何解题系统",
    ) as app:
        gr.Markdown(
            "# 📐 Geometry Agent — AI 几何解题系统\n"
            "支持: 平面几何 / 圆锥曲线 / 立体几何 / 函数导数\n"
            "学段: 初中 / 高中 / 竞赛\n"
            "输入题目, 点击求解, 自动生成PDF解答报告"
        )

        with gr.Tabs():
            # ---- 单题模式 ----
            with gr.Tab("单题求解"):
                with gr.Row():
                    with gr.Column(scale=3):
                        problem_input = gr.Textbox(
                            label="题目",
                            placeholder="输入题目文本, 如: 已知椭圆 x²/4+y²=1, 过点P(1,0)的直线l斜率k=1/2, 求弦长|AB|",
                            lines=5,
                        )
                    with gr.Column(scale=1):
                        grade_select = gr.Radio(
                            ["初中", "高中", "竞赛"],
                            label="学段",
                            value="高中",
                        )
                        show_steps = gr.Checkbox(label="显示步骤", value=True)
                        solve_btn = gr.Button("🚀 求解", variant="primary", size="lg")

                result_output = gr.Markdown(label="结果")
                pdf_output = gr.File(label="PDF下载")

                solve_btn.click(
                    fn=solve_single,
                    inputs=[problem_input, grade_select, show_steps],
                    outputs=[result_output, pdf_output],
                )

            # ---- 多小题模式 ----
            with gr.Tab("多小题求解"):
                with gr.Row():
                    with gr.Column(scale=3):
                        problem_input2 = gr.Textbox(
                            label="题干",
                            placeholder="输入题干, 如: 在Rt△ABC中, ∠BAC=90°, ...",
                            lines=4,
                        )
                        subs_input = gr.Textbox(
                            label="小题 (每行一个)",
                            placeholder="(1) 求 CE 的长\n(2) 求证 BD²=9·DE·DC\n(3) 求 S△BEF/S△BDE",
                            lines=5,
                        )
                    with gr.Column(scale=1):
                        grade_select2 = gr.Radio(
                            ["初中", "高中", "竞赛"],
                            label="学段",
                            value="初中",
                        )
                        solve_btn2 = gr.Button("🚀 求解", variant="primary", size="lg")

                result_output2 = gr.Markdown(label="结果")
                pdf_output2 = gr.File(label="PDF下载")

                solve_btn2.click(
                    fn=solve_multi,
                    inputs=[problem_input2, subs_input, grade_select2],
                    outputs=[result_output2, pdf_output2],
                )

            # ---- 示例 ----
            with gr.Tab("📝 示例题目"):
                gr.Markdown("""
### 平面几何 (初中)
```
在Rt△ABC中，∠BAC=90°，AC=2√5，点D在AB上且BD=3AD，连接CD。过点A作CD的垂线交CD于点E，交BC于点F，连接BE，AE=2。
(1) 求 CE 的长
(2) 求证 BD² = 9·DE·DC
(3) 求 S△BEF / S△BDE 的值
```

### 圆锥曲线 (高中)
```
已知椭圆 C: x²/4 + y² = 1。过点 P(1, 0) 的直线 l 与椭圆 C 交于 A、B 两点。若直线 l 的斜率 k=1/2，求弦长 |AB|。
```

### 函数导数 (高中)
```
已知函数 f(x) = x³ - 3x。求 f(x) 的单调区间和极值。
```

### 立体几何 (高中)
```
在正方体 ABCD-A₁B₁C₁D₁ 中，棱长为 2。求异面直线 AC 与 BD₁ 所成角的余弦值。
```
""")

    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)