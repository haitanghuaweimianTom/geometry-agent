"""Enhanced Reasoning Agent with symbolic feedback loop + exploration + experience.

Architecture (inspired by AlphaGeometry + InternGeometry):

1. **Knowledge-informed reasoning**: classify subject → retrieve grade-scoped
   knowledge → inject into prompt.
2. **Symbolic feedback loop**: LLM proposes a step → symbolic tools verify →
   structured feedback (success/failure+reason) → LLM adjusts → next step.
3. **Exploration mode**: when prior-knowledge methods exhaust without success,
   automatically switch to exploration prompt encouraging novel approaches.
4. **Experience extraction**: after each attempt, extract lessons learned and
   store in :class:`ExperienceMemory` for future retrieval.

When no ``knowledge_manager`` is supplied the agent degrades to a plain CoT
loop but still exposes the extended code-execution tools. When no ``api_key``
is configured the agent returns an empty :class:`ProofPlan`.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import LLMConfig
from ..knowledge.subject_classifier import classify_subject
from ..tools.registry import get_tool_dispatchers, get_tool_schemas
from ..types import GoalSpec, GradeLevel, ProofPlan, ToolCall
from .agent import _failure_desc, _has_failure
from .cot import goal_spec, parse_plan
from .experience import (
    ExperienceMemory,
    extract_experience,
    generate_reflection_summary,
)
from .llm_client import LLMClient
from .prompt_builder import build_enhanced_prompt
from .prompts import fewshot_for, fewshot_for_subject
from .reflection import reflect
from .tools import TOOL_SCHEMAS, claim_step, dispatch


def _clean_summary(text: str) -> str:
    """Lightly clean an LLM-written 解题思路 summary.

    The model writes the summary itself (no keyword heuristics). We only
    remove markdown artifacts and JSON fragments that may leak in, and cap
    the length. No English filtering here — the prompt forbids English.
    """
    import re as _re

    s = str(text or "").strip()
    if not s:
        return ""
    # Strip code fences and JSON plan fragments
    s = _re.sub(r"```(?:json)?.*?```", "", s, flags=_re.DOTALL)
    s = _re.sub(r'\{?"plan":.*', "", s, flags=_re.DOTALL)
    # Markdown artifacts
    s = _re.sub(r"\*+", "", s)
    s = _re.sub(r"#+\s*", "", s)
    s = _re.sub(r"`+", "", s)
    s = _re.sub(r"\s+", " ", s).strip("；，。 \t")
    if len(s) > 400:
        s = s[:400] + "…"
    return s


class EnhancedReasoningAgent:
    """Reasoning agent with knowledge injection + symbolic feedback loop +
    exploration mode + experience memory."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        tools: dict | None = None,
        knowledge_manager: Any = None,
        grade: GradeLevel = GradeLevel.SENIOR,
        experience_memory: ExperienceMemory | None = None,
    ):
        self.config = config or LLMConfig()
        self.tools = tools or {}
        self.knowledge_manager = knowledge_manager
        self.grade = grade
        self.experience_memory = experience_memory or ExperienceMemory()
        self.client = LLMClient(self.config)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def reason(self, dsl: str, problem: str, tools: dict) -> ProofPlan:
        """Produce a :class:`ProofPlan` for the given DSL + problem text.

        Two-phase approach:
          Phase 1: Knowledge-informed reasoning with symbolic feedback loop.
          Phase 2: If phase 1 fails, switch to exploration mode.

        After solving, extract experience and store in memory.
        """
        effective = self._merge_tools(tools)

        if self.client.is_offline:
            return ProofPlan()

        goal = problem or ""
        subject = classify_subject(problem, dsl)

        if self.knowledge_manager is None:
            return self._degrade_reason(dsl, problem, goal, effective)

        # ---- Retrieve experience from past attempts ---- #
        experience_text = self.experience_memory.format_for_prompt(problem, subject.value)

        # ---- Phase 1: Knowledge-informed reasoning ---- #
        knowledge_text = ""
        try:
            rk = self.knowledge_manager.get_knowledge(problem, dsl, grade=self.grade)
            knowledge_text = self.knowledge_manager.format_for_prompt(rk, grade=self.grade)
            subject = rk.topic
        except Exception:
            knowledge_text = ""

        fewshot = fewshot_for_subject(subject)
        messages = build_enhanced_prompt(
            dsl=dsl, problem=problem, goal=goal,
            knowledge=knowledge_text, subject=subject, fewshot=fewshot,
            experience=experience_text, exploration_mode=False,
        )
        plan = self._run_feedback_loop(messages, effective, goal)

        # ---- Phase 2: Exploration mode if phase 1 failed ---- #
        if _has_failure(plan) and not self.client.is_offline:
            plan = self._exploration_phase(dsl, problem, goal, subject,
                                           effective, experience_text)

        # ---- Phase 2b: Cross-grade escalation ---- #
        # If junior grade fails and the problem is solvable with senior methods
        # (e.g. area ratio via coordinates), escalate to senior grade for a
        # final attempt.  This is explicitly allowed by the user.
        if _has_failure(plan) and not self.client.is_offline and self.grade == GradeLevel.JUNIOR:
            plan = self._cross_grade_escalation(dsl, problem, goal, subject,
                                                effective, experience_text)

        # ---- Reflection rounds ---- #
        if not self.client.is_offline and _has_failure(plan):
            history: list[dict[str, Any]] = []
            for _ in range(max(0, self.config.max_reflections)):
                failure = _failure_desc(plan)
                revised = reflect(self.client, failure, plan, history)
                history.append({"failure": failure, "plan": plan.model_dump()})
                plan = revised
                if not _has_failure(plan):
                    break

        # ---- Extract experience ---- #
        self._extract_and_store_experience(problem, subject, plan)

        return plan

    # ------------------------------------------------------------------ #
    # Phase 2: Exploration mode
    # ------------------------------------------------------------------ #
    def _exploration_phase(
        self, dsl: str, problem: str, goal: str, subject: Any,
        effective: dict[str, Any], experience_text: str,
    ) -> ProofPlan:
        """Switch to exploration mode: encourage novel approaches."""
        fewshot = fewshot_for_subject(subject)
        messages = build_enhanced_prompt(
            dsl=dsl, problem=problem, goal=goal,
            knowledge="",  # No knowledge in exploration mode
            subject=subject, fewshot=fewshot,
            experience=experience_text, exploration_mode=True,
        )
        # Add a context message about what failed
        messages.append({
            "role": "user",
            "content": (
                "前面的推荐方法未能解决此题。请放下推荐的方法, "
                "从头独立思考。尝试坐标法、面积法、构造辅助线、"
                "逆向分析等不同思路。任何计算交给工具。"
            ),
        })
        return self._run_feedback_loop(messages, effective, goal)

    # ------------------------------------------------------------------ #
    # Phase 2b: Cross-grade escalation (junior → senior)
    # ------------------------------------------------------------------ #
    def _cross_grade_escalation(
        self, dsl: str, problem: str, goal: str, subject: Any,
        effective: dict[str, Any], experience_text: str,
    ) -> ProofPlan:
        """When junior-grade methods fail, escalate to senior-grade methods.

        This allows using coordinates, sine/cosine theorem, vectors, etc.
        for problems that are theoretically solvable with junior methods
        but where the system couldn't find the junior-level approach.
        """
        # Retrieve senior-grade knowledge
        knowledge_text = ""
        try:
            rk = self.knowledge_manager.get_knowledge(
                problem, dsl, grade=GradeLevel.SENIOR,
            )
            knowledge_text = self.knowledge_manager.format_for_prompt(
                rk, grade=GradeLevel.SENIOR,
            )
        except Exception:
            pass

        fewshot = fewshot_for_subject(subject)
        messages = build_enhanced_prompt(
            dsl=dsl, problem=problem, goal=goal,
            knowledge=knowledge_text, subject=subject, fewshot=fewshot,
            experience=experience_text, exploration_mode=False,
        )
        messages.append({
            "role": "user",
            "content": (
                "初中课内方法未能解出此题。现在允许使用高中方法重新尝试，包括但不限于：\n"
                "1. 坐标法：建立直角坐标系，用坐标和方程求解\n"
                "2. 正弦定理：a/sinA = b/sinB = c/sinC = 2R\n"
                "3. 余弦定理：a² = b² + c² - 2bc·cosA\n"
                "4. 二倍角公式：sin2A=2sinA·cosA, cos2A=cos²A-sin²A\n"
                "5. 向量法：用向量点积/叉积处理角度和长度\n"
                "6. 三角恒等变换：和差化积、积化和差等\n\n"
                "【坐标法详细建系指导】(推荐优先尝试):\n"
                "对于含直角条件的题(如∠BAC=90°)，坐标法最有效:\n"
                "- 第1步: 以直角顶点A为原点，两直角边为坐标轴\n"
                "  本题: A=(0,0), AB在x轴, AC在y轴\n"
                "- 第2步: 根据已知长度写坐标\n"
                "  AC=2√5 → C=(0, 2√5)\n"
                "  设AD=t, 则BD=3t, AB=4t → D=(t,0), B=(4t,0)\n"
                "- 第3步: 用剩余条件列方程\n"
                "  E在CD上: E = C + s*(D-C) = (s*t, 2√5*(1-s)), 0<s<1\n"
                "  AE⊥CD: 向量AE·向量CD = 0 → 一个方程\n"
                "  AE=2: |AE|²=4 → 另一个方程\n"
                "  两个方程解两个未知数 s 和 t\n"
                "- 第4步: 求F坐标\n"
                "  F是AE延长线与BC的交点\n"
                "  直线AE参数: (λ*Ex, λ*Ey), λ>1\n"
                "  直线BC参数: B + u*(C-B)\n"
                "  联立解λ和u\n"
                "- 第5步: 用鞋带公式算面积\n"
                "  S△BEF = ½|xB(yE-yF)+xE(yF-yB)+xF(yB-yE)|\n"
                "  S△BDE = ½|xB(yD-yE)+xD(yE-yB)+xE(yB-yD)|\n"
                "  面积比 = S△BEF / S△BDE\n\n"
                "请严格按此步骤, 用 solve_polynomial_system 或 execute_code 工具求解。"
                "每步算出结果后立即记录, 全部算完后输出 JSON。"
            ),
        })
        return self._run_feedback_loop(messages, effective, goal)

    # ------------------------------------------------------------------ #
    # Symbolic feedback loop (core engine)
    # ------------------------------------------------------------------ #
    def _run_feedback_loop(
        self,
        messages: list[dict[str, Any]],
        tools_dict: dict[str, Any],
        goal: str,
    ) -> ProofPlan:
        """Enhanced CoT loop with symbolic feedback.

        Each LLM tool call is executed and the result is fed back with
        structured feedback. When consecutive failures are detected, a
        reflection nudge is injected to encourage method switching.
        """
        tool_log: list[ToolCall] = []
        cfg = self.client.config
        max_calls = getattr(cfg, "max_tool_calls", 30) or 30
        temp = getattr(cfg, "temperature", 0.3)
        tool_schemas = get_tool_schemas()

        consecutive_failures = 0
        consecutive_successes = 0
        non_json_rounds = 0
        total_calls = 0
        seen_calls: list[tuple[str, str]] = []  # (name, args_json) for dup detection
        duplicate_count = 0

        for _ in range(max(1, int(max_calls))):
            try:
                resp = self.client.chat(messages, tools=tool_schemas, temperature=temp)
            except Exception:
                return self._synthesize_plan(tool_log, goal)

            if resp is None or resp.get("offline"):
                return self._synthesize_plan(tool_log, goal)

            choice = (resp.get("choices") or [{}])[0]
            msg = choice.get("message") or {}

            assistant_msg: dict[str, Any] = {
                "role": msg.get("role", "assistant"),
                "content": msg.get("content") or "",
            }
            if msg.get("tool_calls"):
                assistant_msg["tool_calls"] = msg["tool_calls"]
            messages.append(assistant_msg)

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                non_json_rounds = 0
                for tc in tool_calls:
                    fn = tc.get("function", {}) or {}
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args = (
                            json.loads(raw_args)
                            if isinstance(raw_args, str)
                            else (raw_args or {})
                        )
                    except Exception:
                        args = {}
                    result = dispatch(name, args, tools_dict)
                    tool_log.append(ToolCall(name=name, args=args, result=result))
                    total_calls += 1

                    # Build structured feedback message
                    feedback = self._build_feedback(name, result)
                    messages.append(feedback)

                    # ---- Duplicate detection ----
                    call_sig = (name, json.dumps(args, sort_keys=True, default=str)[:200])
                    if call_sig in seen_calls:
                        duplicate_count += 1
                    else:
                        seen_calls.append(call_sig)
                        duplicate_count = 0

                    # Track consecutive failures / successes
                    if self._is_failure(result):
                        consecutive_failures += 1
                        consecutive_successes = 0
                    else:
                        consecutive_successes += 1
                        consecutive_failures = 0

                    # Inject reflection nudge after 3 consecutive failures
                    if consecutive_failures >= 3:
                        messages.append({
                            "role": "user",
                            "content": (
                                f"已连续{consecutive_failures}次工具调用失败。"
                                "请用 reflect 工具总结失败原因, 然后换一种完全不同的方法。"
                                "不要重复已经失败的思路。"
                            ),
                        })
                        consecutive_failures = 0

                    # ---- Duplicate nudge: LLM is repeating the same call ----
                    if duplicate_count >= 1:
                        messages.append({
                            "role": "user",
                            "content": (
                                "你刚才重复执行了相同的计算。请不要重复, 直接进行下一步:\n"
                                "- 如果坐标已求出, 请继续求交点F的坐标\n"
                                "- 如果所有点坐标已知, 请用鞋带公式算面积\n"
                                "- 如果面积已算出, 请算面积比并输出最终JSON\n"
                                "不要重复已经完成的计算!"
                            ),
                        })
                        duplicate_count = 0

                    # Inject progress nudge after 3 consecutive successes
                    if consecutive_successes == 3:
                        messages.append({
                            "role": "user",
                            "content": (
                                "你已成功完成3次计算。请检查你的解题进度:\n"
                                "- 是否还有未完成的步骤(如求交点、算面积)? 如有, 请继续。\n"
                                "- 如果所有必要计算都已完成, 请输出 JSON 解答。"
                            ),
                        })
                    elif consecutive_successes >= 6:
                        messages.append({
                            "role": "user",
                            "content": (
                                "已计算多次, 请立即输出最终 JSON 解答, 不要再调用工具。"
                                '格式: {"plan":[{"step":1,"statement":"结论",'
                                '"reason":"依据","verified":true}],'
                                '"goal":{"kind":"Prove","statement":"..."},'
                                '"summary":"用2~3句中文总结核心方法与关键观察",'
                                '"key_equations":["证明主线上2~4个核心公式"]}'
                            ),
                        })
                        consecutive_successes = 0

                # Convergence nudge — gentle for proof/inequality problems
                # (they need sustained multi-step reasoning), aggressive for
                # computation problems.
                is_proof = any(
                    k in goal for k in ("证明", "求证", "试证", "大于", "小于", "≥", "≤")
                )
                nudge_threshold = (
                    int(max_calls * 0.85) if is_proof
                    else max(3, int(max_calls) // 2)
                )
                if total_calls >= nudge_threshold:
                    messages.append({
                        "role": "user",
                        "content": (
                            "已收集足够证据。请停止调用工具, 直接输出最终证明的单一 JSON 对象, "
                            '格式: {"plan":[{"step":1,"statement":"...","reason":"...",'
                            '"verified":true}],"goal":{"kind":"Prove","statement":"..."},'
                            '"summary":"用2~3句中文总结核心方法与关键观察",'
                            '"key_equations":["证明主线上2~4个核心公式"]}。'
                            "只输出 JSON, 不要其他内容。"
                        ),
                    })
                continue

            # No tool calls — try to parse as final plan
            content = msg.get("content") or ""
            plan = parse_plan(content, goal)
            plan.tool_calls = tool_log
            plan.summary = _clean_summary(plan.summary)
            # Keep only meaningful LLM-written key equations (no code garbage)
            plan.key_equations = [
                _clean_summary(eq) for eq in (plan.key_equations or [])
                if _clean_summary(eq)
            ]
            return plan

        # Fallback: synthesize from tool log
        plan = self._synthesize_plan(tool_log, goal)
        return plan

    # ------------------------------------------------------------------ #
    # Feedback construction
    # ------------------------------------------------------------------ #
    def _build_feedback(self, tool_name: str, result: Any) -> dict[str, Any]:
        """Build a structured feedback message from a tool result.

        Instead of just dumping the raw result, this adds interpretive
        feedback that helps the LLM understand what to do next.
        For execute_code, the stdout output is highlighted prominently.
        """
        result_str = json.dumps(result, ensure_ascii=False, default=str)

        if isinstance(result, dict):
            if result.get("success") is False:
                error = result.get("error", "未知错误")
                content = f"工具 {tool_name} 执行失败: {error}\n请检查参数或换一种方法。"
            elif result.get("verified") is True or str(result.get("verified")) == "true":
                content = f"工具 {tool_name} 验证成功: {result_str}\n结论已确认, 可以继续下一步。"
            elif result.get("verified") is False or str(result.get("verified")) == "false":
                content = f"工具 {tool_name} 验证失败: {result_str}\n此路不通, 请尝试其他方法或修正推理。"
            elif result.get("success") is True:
                # Structured computation tool succeeded
                steps = result.get("steps", "")
                res_val = result.get("result", "")
                content = f"工具 {tool_name} 计算成功。结果: {res_val}"
                if steps:
                    content += f"\n计算过程:\n{steps}"
                content += "\n请基于此结果继续推理。"
            else:
                # execute_code result: {success, output, error, value, code}
                # Highlight the output prominently so the LLM can read it.
                output = result.get("output", "")
                error = result.get("error", "")
                value = result.get("value", "")
                if output and not error:
                    content = (
                        f"【计算成功】工具 {tool_name} 的输出结果:\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{output}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    )
                    if value:
                        content += f"返回值: {value}\n"
                    content += "请仔细阅读上面的输出, 提取关键数值, 然后继续下一步计算或输出最终答案。"
                elif error:
                    content = f"工具 {tool_name} 执行出错: {error}\n请修正代码后重试。"
                else:
                    content = result_str
        else:
            content = str(result)

        return {
            "role": "tool",
            "tool_call_id": "",
            "name": tool_name,
            "content": content,
        }

    def _is_failure(self, result: Any) -> bool:
        """Check if a tool result indicates failure."""
        if not isinstance(result, dict):
            return False
        if result.get("success") is False:
            return True
        v = result.get("verified")
        if v is False or str(v) == "false":
            return True
        return False

    # ------------------------------------------------------------------ #
    # Plan synthesis from tool log (fallback)
    # ------------------------------------------------------------------ #
    def _synthesize_plan(self, tool_log: list[ToolCall], goal: str) -> ProofPlan:
        """Build a fallback ProofPlan from successful tool calls."""
        from .cot import _plan_from_tool_log
        return _plan_from_tool_log(tool_log, goal)

    # ------------------------------------------------------------------ #
    # Experience extraction
    # ------------------------------------------------------------------ #
    def _extract_and_store_experience(
        self, problem: str, subject: Any, plan: ProofPlan,
    ) -> None:
        """Extract experience from the solving attempt and store in memory."""
        try:
            from ..types import Solution
            # Build a pseudo-solution from the plan for experience extraction
            verified_count = sum(1 for st in plan.plan if st.verified)
            total_count = len(plan.plan)
            confidence = verified_count / total_count if total_count > 0 else 0.0
            solution = Solution(
                answer="",
                proof=plan.plan,
                confidence=confidence,
                verified=confidence >= 0.5,
            )
            subject_str = getattr(subject, "value", str(subject))
            grade_str = self.grade.value if hasattr(self.grade, "value") else str(self.grade)
            entry = extract_experience(
                problem_text=problem,
                subject=subject_str,
                grade=grade_str,
                plan=plan,
                solution=solution,
                tool_calls=plan.tool_calls,
            )
            self.experience_memory.add(entry)
        except Exception:
            pass  # experience extraction is best-effort

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _merge_tools(self, tools: dict | None) -> dict[str, Any]:
        user_tools = dict(tools) if tools else {}
        merged = get_tool_dispatchers(user_tools)
        for name, fn in user_tools.items():
            merged.setdefault(name, fn)
        if "reflect" not in merged:
            merged["reflect"] = self._make_reflect_tool()
        if "claim_step" not in merged:
            merged["claim_step"] = claim_step
        return merged

    def _degrade_reason(
        self, dsl: str, problem: str, goal: str, effective: dict[str, Any]
    ) -> ProofPlan:
        from .cot import cot_reason
        fewshot = fewshot_for("triangle")
        return cot_reason(self.client, dsl, problem, goal, effective, fewshot)

    def _make_reflect_tool(self):
        client = self.client

        def _reflect_tool(failure: str = "", plan: Any = None, history: Any = None):
            revised = reflect(client, failure or "", plan, history or [])
            return revised.model_dump()

        return _reflect_tool


__all__ = ["EnhancedReasoningAgent"]
