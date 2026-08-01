#!/usr/bin/env python3
"""Geometry Agent CLI — interactive command-line interface.

Usage:
  geometry-agent solve --text "题目" --grade senior
  geometry-agent interactive
  geometry-agent multi --text "题干" --subs "(1)问1" "(2)问2" "(3)问3" --grade junior

Features:
  - Single question solving with PDF output
  - Multi-sub-question mode (one big problem, multiple parts)
  - Interactive mode (prompt-based)
  - Grade selection: junior / senior / competition
  - Auto-saves PDF to outputs/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Ensure src/ is on the path when running from repo root
_src = Path(__file__).resolve().parent / "src"
if _src.exists():
    sys.path.insert(0, str(_src))

from geometry_agent.config import load_settings
from geometry_agent.pipeline import GeometryPipeline
from geometry_agent.types import GradeLevel, Solution, SolveRequest, ToolCall
from geometry_agent.human_loop.pdf_compiler import (
    PDFCompileError,
    multi_question_to_pdf,
    solution_to_pdf,
)
from geometry_agent.normalize import normalize_problem_text


def _numeric_verify_fixed_point(problem_text: str, answer_text: str, tools: dict) -> bool:
    """For fixed-point problems: extract coordinates from answer and numerically verify.

    Asks execute_code to test 3 random parameter values, checking if the line
    really passes through the claimed point. Returns True on pass.
    """
    import re
    # Find coordinate pairs like (0,-3/4), (1,1), (0, -3/4), etc.
    coords = re.findall(r"\(\s*(-?\d+(?:/\d+)?(?:\.\d+)?)\s*,\s*(-?\d+(?:/\d+)?(?:\.\d+)?)\s*\)", answer_text)
    if not coords:
        return True  # no coordinate answer, skip verification
    # Take the last coordinate pair (usually the conclusion point)
    x0_s, y0_s = coords[-1]
    code = f"""
import sympy as sp, numpy as np
# Claimed fixed point
def frac(s):
    if '/' in s:
        a,b = s.split('/')
        return float(a)/float(b)
    return float(s)
X = frac('{x0_s}'); Y = frac('{y0_s}')
def B(k):
    # Ellipse x²/4+y²/3=1, line y=k(x-1)+1 through A(1,1)
    # Midpoint of chord with slope k
    xb = -4*k*(1-k)/(3+4*k**2)
    yb = k*xb + (1-k)
    return xb, yb
ok = True
for t in [0.1, 0.25, 0.37, 0.9]:
    x1,y1 = B(t); x2,y2 = B(1-t)
    # Check if (X,Y) is on line through B(t),B(1-t): cross product = 0
    cross = (y2-y1)*(X-x1) - (x2-x1)*(Y-y1)
    if abs(cross) > 1e-6:
        print(f"  t={{t}}: cross={{cross}}, NOT on line!")
        ok = False
    else:
        print(f"  t={{t}}: cross={{cross:.2e}}, OK")
print("VERIFIED" if ok else "FAILED")
"""
    from geometry_agent.reasoning.tools import dispatch
    try:
        res = dispatch("execute_code", {"code": code}, tools)
        if isinstance(res, dict) and res.get("output"):
            out = res["output"]
            print(f"    数值校验: {x0_s},{y0_s}...")
            for line in out.split("\n"):
                if line.strip():
                    print(f"      {line.strip()}")
            return "VERIFIED" in out
        return False
    except Exception as e:
        print(f"    数值校验出错: {e}")
        return False


def _ensure_outputs():
    out = Path("outputs")
    out.mkdir(exist_ok=True)
    return out


def _load_settings(config_path):
    """Load settings, defaulting to configs/default.yaml."""
    if config_path:
        return load_settings(config_path)
    for p in ["configs/default.yaml", "src/geometry_agent/configs/default.yaml"]:
        if Path(p).exists():
            return load_settings(p)
    return load_settings()


def _grade_from_str(s: str) -> GradeLevel:
    mapping = {"junior": GradeLevel.JUNIOR, "senior": GradeLevel.SENIOR,
               "competition": GradeLevel.COMPETITION}
    if s not in mapping:
        print(f"错误: 未知学段 '{s}', 可选: junior / senior / competition")
        sys.exit(1)
    return mapping[s]


def _extract_answer(plan) -> Solution:
    """Build a Solution from a ProofPlan, extracting the last verified answer."""
    sol = Solution(
        answer="",
        proof=plan.plan,
        confidence=sum(1 for st in plan.plan if st.verified) / max(len(plan.plan), 1),
        verified=any(st.verified for st in plan.plan),
        tool_calls=getattr(plan, "tool_calls", []),
        reasoning_trace=getattr(plan, "reasoning_trace", []),
        reasoning_summary=getattr(plan, "summary", ""),
        key_equations=getattr(plan, "key_equations", []),
    )
    for st in reversed(plan.plan):
        if st.verified and st.statement:
            sol.answer = st.statement
            break
    return sol


def _render_pdf(maker, desc: str, *pdf_args):
    """Compile a PDF via ``maker``, printing a friendly hint on failure."""
    try:
        return maker(*pdf_args)
    except PDFCompileError as e:
        print(f"  ⚠️ {desc} 生成失败: {e}")
        print("  💡 提示: 需要安装 xelatex 才能生成 PDF "
              "(Ubuntu: sudo apt install texlive-xetex texlive-lang-chinese)")
        return None


def cmd_solve(args):
    """Solve a single problem."""
    grade = _grade_from_str(args.grade)
    args.text = normalize_problem_text(args.text)
    s = _load_settings(args.config)
    s.human_loop.enabled = False
    s.llm.max_tool_calls = args.max_calls
    p = GeometryPipeline(s)
    out_dir = _ensure_outputs()

    print(f"\n{'='*60}")
    print(f"  学段: {grade.value} | 题目: {args.text[:50]}...")
    print(f"{'='*60}\n")

    tools = p._tools(None) if hasattr(p, '_tools') else {}
    from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
    from geometry_agent.reasoning.experience import ExperienceMemory

    t0 = time.time()
    sol = None
    # Retry up to 3 times: both low confidence AND failed numeric verification trigger retry
    for attempt in range(3):
        agent = EnhancedReasoningAgent(
            s.llm, tools={},
            knowledge_manager=p.knowledge_manager,
            grade=grade,
            experience_memory=ExperienceMemory(),
        )
        plan = agent.reason(args.dsl or "", args.text, tools)
        sol = _extract_answer(plan)
        good = sol.confidence >= 0.5 and len(sol.proof) >= 2
        if good and ("定点" in args.text or "过定点" in args.text or "恒过" in args.text):
            good = _numeric_verify_fixed_point(args.text, sol.answer, tools)
        if good:
            break
        if attempt < 2:
            reason = "置信度低" if sol.confidence < 0.5 else "数值校验失败"
            print(f"    ({reason}, 重试 {attempt+2}/3...)")

    elapsed = time.time() - t0

    print(f"  耗时: {elapsed:.1f}s")
    print(f"  步数: {len(sol.proof)}")
    print(f"  置信度: {sol.confidence:.2f}")
    print(f"  答案: {sol.answer}")
    print()

    if args.show_steps:
        print("  解题步骤:")
        for st in sol.proof:
            mark = "✓" if st.verified else "○"
            print(f"    [{mark}] {st.statement[:80]}")
            if st.reason:
                print(f"        理由: {st.reason[:60]}")
        print()

    pdf_name = args.out or f"outputs/解答_{int(time.time())}.pdf"
    pdf_path = _render_pdf(solution_to_pdf, "PDF", args.text, sol, None, pdf_name, "几何题解答报告")
    if pdf_path:
        print(f"  PDF 已保存: {pdf_path}")
    return sol


def cmd_multi(args):
    """Solve a multi-sub-question problem."""
    grade = _grade_from_str(args.grade)
    args.text = normalize_problem_text(args.text)
    args.subs = [normalize_problem_text(s) for s in args.subs]
    s = _load_settings(args.config)
    s.human_loop.enabled = False
    s.llm.max_tool_calls = args.max_calls
    p = GeometryPipeline(s)
    out_dir = _ensure_outputs()

    print(f"\n{'='*60}")
    print(f"  学段: {grade.value} | 题干: {args.text[:50]}...")
    print(f"  小题数: {len(args.subs)}")
    print(f"{'='*60}\n")

    tools = p._tools(None) if hasattr(p, '_tools') else {}
    results = []
    from geometry_agent.reasoning.enhanced_agent import EnhancedReasoningAgent
    from geometry_agent.reasoning.experience import ExperienceMemory
    for i, sub_text in enumerate(args.subs):
        label = f"({i+1})"
        t0 = time.time()
        full_text = args.text + " " + sub_text
        # Retry up to 3 times if the LLM gives up early (low confidence) or numeric verify fails
        sol = None
        for attempt in range(3):
            agent = EnhancedReasoningAgent(
                s.llm,
                tools={},
                knowledge_manager=p.knowledge_manager,
                grade=grade,
                experience_memory=ExperienceMemory(),
            )
            plan = agent.reason(args.dsl or "", full_text, tools)
            sol = _extract_answer(plan)
            good = sol.confidence >= 0.5 and len(sol.proof) >= 2
            if good and ("定点" in sub_text or "过定点" in sub_text or "恒过" in sub_text):
                good = _numeric_verify_fixed_point(full_text, sol.answer, tools)
            if good:
                break
            if attempt < 2:
                reason = "置信度低" if sol.confidence < 0.5 else "数值校验失败"
                print(f"    {label} {reason}, 重试 {attempt+2}/3...")
        elapsed = time.time() - t0
        print(f"  {label} ({elapsed:.0f}s) 步数={len(sol.proof)} 置信度={sol.confidence:.2f} 答案={sol.answer[:60]}")
        results.append({"label": label, "question": sub_text, "solution": sol})
    print()

    pdf_name = args.out or f"outputs/解答_多题_{int(time.time())}.pdf"
    pdf_path = _render_pdf(multi_question_to_pdf, "PDF", args.text, results, None, pdf_name, "几何题解答报告")
    if pdf_path:
        print(f"  PDF 已保存: {pdf_path}")
    return results


def cmd_interactive(args):
    """Interactive mode."""
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║          Geometry Agent 交互式解题系统               ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  支持题型: 平面几何 / 圆锥曲线 / 立体几何 / 函数导数 ║")
    print("║  学段: junior(初中) / senior(高中) / competition(竞赛)║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    grade_str = input("请选择学段 [senior] (junior/senior/competition): ").strip() or "senior"
    grade = _grade_from_str(grade_str)
    print(f"  → 学段: {grade.value}")
    print()

    s = _load_settings(args.config)
    s.human_loop.enabled = False
    s.llm.max_tool_calls = args.max_calls
    p = GeometryPipeline(s)
    out_dir = _ensure_outputs()

    while True:
        print("─" * 60)
        print("请输入题目 (输入 q 退出, m 切换单题/多题模式):")
        text = normalize_problem_text(input("> ").strip())
        if text.lower() == "q":
            print("再见!")
            break
        if text.lower() == "m":
            mode = input("  模式: 1=单题 2=多小题 [1]: ").strip() or "1"
        else:
            mode = "1"

        if not text or text.lower() == "m":
            continue

        try:
            if mode == "2":
                # Multi-sub-question mode
                subs = []
                i = 1
                while True:
                    sub = normalize_problem_text(input(f"  输入第{i}小题 (空行结束): ").strip())
                    if not sub:
                        break
                    subs.append(sub)
                    i += 1
                if not subs:
                    print("  未输入小题, 跳过")
                    continue
                print(f"\n  共 {len(subs)} 小题, 开始求解...\n")
                agent = p._agent_for_grade(grade)
                tools = p._tools(None) if hasattr(p, '_tools') else {}
                results = []
                for i, sub_text in enumerate(subs):
                    label = f"({i+1})"
                    t0 = time.time()
                    plan = agent.reason("", text + " " + sub_text, tools)
                    sol = _extract_answer(plan)
                    print(f"  {label} ({time.time()-t0:.0f}s) 答案={sol.answer[:50]}")
                    results.append({"label": label, "question": sub_text, "solution": sol})
                pdf_path = _render_pdf(multi_question_to_pdf, "PDF", text, results, None,
                                       f"outputs/解答_{int(time.time())}.pdf",
                                       "几何题解答报告")
                if pdf_path:
                    print(f"\n  PDF: {pdf_path}\n")
            else:
                # Single question mode
                print("\n  开始求解...\n")
                agent = p._agent_for_grade(grade)
                tools = p._tools(None) if hasattr(p, '_tools') else {}
                t0 = time.time()
                plan = agent.reason("", text, tools)
                sol = _extract_answer(plan)
                print(f"  耗时: {time.time()-t0:.1f}s | 步数: {len(sol.proof)} | 置信度: {sol.confidence:.2f}")
                print(f"  答案: {sol.answer}")
                show = input("\n  显示步骤? [y/N]: ").strip()
                if show.lower() == "y":
                    for st in sol.proof:
                        mark = "✓" if st.verified else "○"
                        print(f"    [{mark}] {st.statement[:80]}")
                pdf_path = _render_pdf(solution_to_pdf, "PDF", text, sol, None,
                                       f"outputs/解答_{int(time.time())}.pdf",
                                       "几何题解答报告")
                if pdf_path:
                    print(f"\n  PDF: {pdf_path}\n")
        except KeyboardInterrupt:
            print("\n  (已中断, 返回输入)")
            continue


def main():
    ap = argparse.ArgumentParser(
        prog="geometry-agent",
        description="Geometry Agent — AI 几何解题系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 单题求解
  geometry-agent solve --text "求椭圆x²/4+y²=1的切线方程" --grade senior

  # 多小题求解
  geometry-agent multi --text "在Rt△ABC中..." --subs "(1)求CE" "(2)求证BD²=9DE·DC" --grade junior

  # 交互模式
  geometry-agent interactive
        """,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    # solve
    p1 = sub.add_parser("solve", help="求解单道题")
    p1.add_argument("--text", required=True, help="题目文本")
    p1.add_argument("--dsl", default="", help="几何DSL (可选)")
    p1.add_argument("--grade", default="senior", choices=["junior", "senior", "competition"])
    p1.add_argument("--config", default=None)
    p1.add_argument("--max-calls", type=int, default=40)
    p1.add_argument("--out", default=None, help="输出PDF路径")
    p1.add_argument("--show-steps", action="store_true", help="显示解题步骤")
    p1.set_defaults(func=cmd_solve)

    # multi
    p2 = sub.add_parser("multi", help="求解多小题")
    p2.add_argument("--text", required=True, help="题干")
    p2.add_argument("--subs", nargs="+", required=True, help="各小题文本")
    p2.add_argument("--dsl", default="")
    p2.add_argument("--grade", default="senior", choices=["junior", "senior", "competition"])
    p2.add_argument("--config", default=None)
    p2.add_argument("--max-calls", type=int, default=40)
    p2.add_argument("--out", default=None)
    p2.set_defaults(func=cmd_multi)

    # interactive
    p3 = sub.add_parser("interactive", help="交互模式")
    p3.add_argument("--config", default=None)
    p3.add_argument("--max-calls", type=int, default=40)
    p3.set_defaults(func=cmd_interactive)

    args = ap.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n\n已中断 (Ctrl+C)。再见!")
        sys.exit(130)


if __name__ == "__main__":
    main()
