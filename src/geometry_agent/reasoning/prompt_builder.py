"""Prompt assembly for the :class:`EnhancedReasoningAgent`.

:func:`build_enhanced_prompt` merges the enhanced system prompt, a knowledge
fragment (with method-priority annotations), a few-shot example, and the
DSL+problem context into the message list consumed by the CoT loop.

Key features:
- **面积比启发式**: when area-ratio problems are detected, the 7-step
  decision flow is injected as a forced heuristic.
- **探索模式**: when prior-knowledge methods fail, the prompt switches to
  encourage independent creative thinking.
- **经验注入**: past solving experiences are injected as reference.
"""

from __future__ import annotations

from typing import Any, Optional

from ..types import GradeLevel
from .prompts import ENHANCED_SYSTEM_PROMPT


# =====================================================================================
# Area-ratio 7-step decision flow (from research report §2.3)
# =====================================================================================
AREA_RATIO_HEURISTIC = """\
[面积比问题强制决策流程]
遇到"面积比/面积关系"题, 必须按以下7步依次检查:
1. 是否出现相似三角形? → 是 ⇒ 面积比 = 相似比² (注意: 线段比→面积比要平方, 面积比→线段比要开方!)
2. 是否两三角形共高(共顶点/底共线)? → 是 ⇒ 共高定理, 面积比 = 底比
3. 是否两三角形共底(顶点在平行线上)? → 是 ⇒ 共底定理, 或做等积变换
4. 是否含等角/互补角? → 是 ⇒ 共角定理 S₁/S₂ = (a₁·b₁)/(a₂·b₂)
5. 是否需要把面积当中介证其它量? → 是 ⇒ 正弦面积公式 S = ½ab·sinC 做桥
6. 是否给定坐标? → 是 ⇒ 鞋带公式直接算 S = ½|Σ(xᵢyᵢ₊₁ - xᵢ₊₁yᵢ)|
7. 都不直接适用? → 构造辅助线(平行线/中线/相似), 把未知面积比转化为上述可算情形

[面积比易错点检查]
- 平方/开方: 线段比⇄面积比转换时必须平方或开方
- 共高判定: 确认"高"确实落在同一直线或平行线上
- 相似比方向: 相似比k=A→B时面积比是k²; B→A则是1/k²
- 等积变换条件: 必须确认顶点在平行于底的直线上
"""


# =====================================================================================
# Exploration mode prompt (when prior knowledge fails)
# =====================================================================================
EXPLORATION_PROMPT = """\
[探索模式 — 前置知识方法已失败, 切换独立思考]
前面的推荐方法未能解决问题。现在请你自己思考, 不局限于推荐的方法:
1. 重新审视题目条件, 是否有被忽略的隐含条件?
2. 尝试从未推荐的方法:
   - 坐标法(建系) + sympy 代数爆算
   - 几何观察: 寻找共线/共点/定值关系
   - 射影几何: 极点极线 — 焦点 F 的极线是准线 l; 调和同调 — 以 F 为中心、l 为轴的射影变换保圆曲线
   - 仿射变换: 将椭圆压缩为圆, 简化计算
   - 复数法: 旋转/共线/垂直的简洁表达
   - 向量法、面积法、三角法
3. 尝试构造辅助元素: 辅助线(平行线/垂线/中线/角平分线)、辅助圆、辅助函数
4. 尝试逆向思考: 从结论出发, 要证什么就需要什么, 反推需要什么条件
5. 尝试特殊化: 先考虑特殊位置/特殊值, 发现规律再推广

不要害怕尝试新方法。如果一种思路行不通, 用 reflect 工具总结失败原因, 然后换一种思路。
工具是你的计算器, 任何计算都交给工具, 你只负责思路。
"""


# =====================================================================================
# Inequality / optimization deep-thinking heuristic
# =====================================================================================
INEQUALITY_HEURISTIC = """\
[不等式 / 优化问题深度思考流程]
遇到"证明 XX > YY" "证明 XX ≥ YY" "求 XX 的取值范围" "求 XX 最值" 等问题,
必须按以下深度思考流程进行, 充分使用 execute_code 做符号计算:

【第一步: 参数化】
- 在曲线上设点, 用参数表示各点坐标 (如抛物线 y=x²+c 上点设为 (t, t²+c))
- 把所有约束条件 (垂直、平行、共线、距离等) 用参数方程表示
- 用约束消元, 减少自由参数个数

【第二步: 建立目标函数】
- 把要证/要求的量 (周长、面积、距离、比值) 表示为参数的函数
- 用 execute_code (sympy) 做符号展开、化简, 得到目标函数表达式

【第三步: 求临界点】
- 对目标函数求偏导, 用 execute_code (sympy.diff + sympy.solve) 求临界点
- 检验临界点是否在定义域内 (参数有物理/几何意义约束)

【第四步: 检查退化 / 边界情形】
- 检查参数趋于 0/∞/重合 等退化情形, 目标函数的极限值
- 退化情形常给出下确界/上确界, 而非真正的最值
- "证明 XX > YY" 型问题, 往往下确界 = YY, 但退化情形不可达, 故严格大于

【第五步: 综合结论】
- 比较各临界点的函数值与退化极限值
- 给出严格不等式证明: 实际构型 vs 退化情形的差异

[典型范例: 抛物线上矩形周长不等式]
- 三点在 y=x²+c 上, 直角顶点 A, 设 A=(a,a²+c), B=(b,b²+c), D=(d,d²+c)
- 直角约束: AB·AD = (b-a)(d-a)[1+(a+b)(a+d)] = 0, 因 b≠a,d≠a 得 1+(a+b)(a+d)=0
- 令 p=a+b, q=a+d, 则 pq=-1, 即 d=-1/(a+b)-a
- |AB|=|b-a|√(1+p²), |AD|=|d-a|√(1+q²)
- 周长 P=2(|AB|+|AD|), 用 sympy 求偏导找临界点, 再检查 a→d 退化情形
"""


# =====================================================================================
# Abstract proof heuristic (no specific values → set up standard coordinates + parameters)
# =====================================================================================
ABSTRACT_PROOF_HEURISTIC = """\
[抽象证明题解题流程 — 多方法交叉验证]

遇到"求证" "证明" 等抽象证明题, 必须至少尝试 2 种方法:

【方法一: 坐标代数法 (必做, 兜底)】
- 题目没有给具体曲线方程? 必须自己设标准方程!
  * 椭圆: x²/a² + y²/b² = 1 (简化可取 a=2, b=1)
  * 双曲线: x²/a² - y²/b² = 1
  * 圆: x²+y²=r² (简化可取 r=1)
  * 抛物线: y²=2px 或 x²=2py
- 没有给具体点坐标? 必须设参数!
  * 动直线: 过定点设斜率 k, 方程 y-y₀=k(x-x₀)
  * 动点: 用参数坐标 (如椭圆上点 (a cosθ, b sinθ))
- 用 execute_code (sympy) 做代数推导:
  * 联立求交点 → 韦达定理/vieta_theorem
  * 消元 → polynomial_resultant / groebner_basis
  * 恒等式验证 → verify_identity / compare_coefficients
- 取 3 个随机参数值, 数值验证结论成立

【方法二: 几何观察/射影几何 (尝试, 加分)】
- 寻找共线关系: 用 collinear_check 或手动计算斜率验证
- 寻找共点关系: 检查三条直线是否交于一点
- 射影几何视角:
  * 极点极线: 焦点 F 关于圆锥曲线的极线是准线 l. 若 T ∈ l 则 F ∈ polar(T).
  * 调和同调: 以 F 为中心、极线 l 为轴的射影变换 H 保圆曲线且交换焦点弦两端点.
    若 H(N)=M, H(B)=A, 则 H(BN)=AM, 故 T=BN∩l 在 AM 上 → A,T,M 共线.
  * 仿射变换: 将椭圆压缩为圆, 简化计算.
- 用几何观察简化或验证坐标法的结果

【方法三: 其他高等方法 (可选)】
- 复数法: 用 complex_method 验证共线/垂直/等长
- 仿射变换: 用 affine_transform 将椭圆变圆, 在新图形中计算, 再变换回来

【最终输出】
- 至少包含两种方法的推导
- 两种方法得到相同结论, 交叉验证通过后才输出最终答案
- 在 summary 中说明用了哪几种方法

[典型范例: 双曲线角平分线定点问题]
- 方法一(坐标法): 设 N 坐标, 角平分线定理求 T, 韦达定理求 M, 硬算 k_TM = -3k
- 方法二(几何观察): 发现 A,T,M 共线, k_TM = k_AT = -3k, 一步到位
- 方法三(射影几何): 以 F 为中心、准线为轴的调和同调 H 保双曲线, H(N)=M, H(B)=A, 故 H(BN)=AM, T=BN∩准线 是定点, 因此 T∈AM → 共线
"""


# =====================================================================================
# Fixed-point / 过定点 proof heuristic (先猜后证, 特殊值法)
# =====================================================================================
FIXED_POINT_HEURISTIC = """\
[定点问题解题流程 — 先猜后证]
遇到"证明直线过定点" "证明恒过某点"等问题, 必须严格按以下步骤:

【第一步: 特殊值猜点】
- 取至少2组满足题设的特殊参数值(例如不同斜率k), 分别算出具体直线方程
- 求两条具体直线的交点, 作为候选定点F
- 【必须验证】再取第3组完全不同的参数值, 算该参数下的直线是否过F:
  若F在该直线上(误差<1e-8), 才接受F作为定点候选
- 若不在, 重新检查前面的计算是否有错

【第二步: 代数证明】
- 设参数为k, 把直线方程用k参数化(如: y=k(x-xA)+yA)
- 代入曲线方程, 用韦达定理求各点坐标关于k的表达式
- 证明对任意参数k, F点满足直线BC的方程(共线条件行列式恒为0)
- 所有代数化简必须调用 execute_code (sympy) 完成, 不能手算

【第三步: 结论自检】
- 最终答案写出定点坐标后, 必须再做一次数值验证: 取3个随机k值, 检查直线是否过F
- 若答案附带几何标签(如"即椭圆下顶点"、"即点A"), 必须单独verify该标签:
  例如定点是(0,-3/4)不能说它是椭圆下顶点(椭圆x²/4+y²/3=1下顶点是(0,-√3))
- 未验证的几何标签绝不能写进答案
"""


# =====================================================================================
# Problem-type detection for heuristic injection
# =====================================================================================
def _is_area_ratio_problem(problem: str) -> bool:
    """Detect whether a problem involves area ratios."""
    keywords = ("面积比", "S△", "S_{△", "面积之比", "面积的比", "S△BEF", "面积关系")
    return any(k in problem for k in keywords)


def _is_proof_problem(problem: str) -> bool:
    """Detect whether a problem is a proof (vs computation)."""
    return any(k in problem for k in ("求证", "证明", "试证"))


def _is_inequality_problem(problem: str) -> bool:
    """Detect whether a problem involves inequality proof or optimization."""
    keywords = (
        "大于", "小于", "不小于", "不大于", "大于等于", "小于等于",
        "≥", "≤", ">", "<",
        "最值", "最大值", "最小值", "取值范围",
        "恒成立", "成立",
    )
    return any(k in problem for k in keywords)


def _is_fixed_point_problem(problem: str) -> bool:
    """Detect whether a problem asks to prove a line/curve passes through a fixed point."""
    return ("过定点" in problem or "恒过" in problem or "定点" in problem) and _is_proof_problem(problem)


# =====================================================================================
# Main prompt builder
# =====================================================================================
def build_enhanced_prompt(
    dsl: str,
    problem: str,
    goal: str,
    knowledge: str,
    subject: Any,
    fewshot: str,
    experience: str = "",
    exploration_mode: bool = False,
    grade: Optional[GradeLevel] = None,
) -> list[dict[str, Any]]:
    """Assemble the chat messages for the enhanced reasoning loop.

    Parameters
    ----------
    dsl, problem, goal:
        The geometry DSL, problem text, and goal statement.
    knowledge:
        Pre-formatted knowledge fragment. May be empty.
    subject:
        The classified :class:`SubjectType`.
    fewshot:
        A few-shot example string for the detected subject.
    experience:
        Past solving experiences formatted as a prompt fragment.
    exploration_mode:
        When True, switch to exploration prompt (prior knowledge failed).
    """
    system = ENHANCED_SYSTEM_PROMPT or ""
    if fewshot:
        system = f"{system}\n\n{fewshot}"

    subject_label = ""
    if subject is not None:
        subject_label = getattr(subject, "value", str(subject))

    # ---- Assemble knowledge block ----
    knowledge_block = ""
    if knowledge and knowledge.strip():
        knowledge_block = (
            "[推荐知识 / 推荐方法]\n"
            f"{knowledge}\n\n"
        )

    # ---- Assemble experience block ----
    experience_block = ""
    if experience and experience.strip():
        experience_block = experience

    # ---- Assemble heuristic block (area ratio etc.) ----
    heuristic_block = ""
    if _is_area_ratio_problem(problem):
        heuristic_block = AREA_RATIO_HEURISTIC + "\n"
    elif _is_fixed_point_problem(problem):
        heuristic_block = FIXED_POINT_HEURISTIC + "\n"
    elif _is_inequality_problem(problem) and _is_proof_problem(problem):
        heuristic_block = INEQUALITY_HEURISTIC + "\n"
    elif _is_proof_problem(problem):
        heuristic_block = ABSTRACT_PROOF_HEURISTIC + "\n"

    # ---- Assemble mode block ----
    mode_block = ""
    if exploration_mode:
        mode_block = EXPLORATION_PROMPT + "\n"

    # ---- Assemble verification-contract block ----
    verification_contract = ""
    if grade is not None:
        base_contract = (
            "[验证契约]\n"
            "每得出一个非平凡结论(非单纯算术结果), 必须先调用 claim_step 声明该结论, "
            "等待验证通过(✓)后再继续下一步。\n"
            "验证失败会返回具体原因, 请修正重述; 连续3次失败将由审查员裁决。\n"
        )
        if grade is GradeLevel.COMPETITION:
            base_contract += "(竞赛模式将使用 Lean 形式化验证)\n"
        verification_contract = base_contract + "\n"

    # ---- Assemble instructions ----
    if exploration_mode:
        instructions = (
            "[Instructions — 探索模式]\n"
            "1. 前面的推荐方法已失败, 请独立思考, 尝试新方法。\n"
            "2. 任何计算交给工具 (execute_code / solve / vieta_theorem / compute_derivative 等)。\n"
            "3. 每步结论调 verify 确认; 失败则用 reflect 总结原因并换思路。\n"
            "4. 不要放弃。换一种方法再试。\n"
            "5. 输出最终证明为单一 JSON 对象:\n"
            '   {"plan":[{"step":1,"statement":"...","reason":"...","verified":true}],'
            '"goal":{"kind":"Prove","statement":"..."},'
            '"summary":"用2~3句中文总结本解法的核心方法与关键观察",'
            '"key_equations":["本证明中最核心的2~4个公式/方程,每个一策"]}\n'
            "6. 除数学公式外一律使用中文; 不要出现英文短语、英文工具名或代码。\n"
            "7. 最终答案只写你已通过 verify 验证的坐标/等式/结论; "
            "若答案附带几何标签(如\"即椭圆下顶点\"、\"即点A\"、\"垂足\"), "
            "必须在最后一步用 verify 验证该标签对应的几何关系是否成立, "
            "未验证的标签绝不能写进答案。\n"
            "8. key_equations 只写证明主线上的核心公式(如中点坐标公式、韦达定理结果、"
            "共线条件), 不要写特殊值数值验证的中间结果, 不要写代码输出。\n"
        )
    else:
        instructions = (
            "[Instructions]\n"
            "1. 优先使用课内方法 (标有 [推荐优先尝试] 的方法); "
            "高等几何方法其次; 机器证明最后。\n"
            "2. 需要计算时调用 execute_code / solve / polynomial_factor / vieta_theorem "
            "/ compute_derivative 等结构化工具, 不要手算数值。\n"
            "3. 每步结论调 verify 确认; 若 verify 返回 false 则调 reflect 修正。\n"
            "4. 如果推荐方法全部失败, 系统会自动切换探索模式, 那时请独立思考。\n"
            "5. 输出最终证明为单一 JSON 对象:\n"
            '   {"plan":[{"step":1,"statement":"...","reason":"...",'
            '"verified":true,"tool_call":{"name":"...","args":{...}}}],'
            '"goal":{"kind":"Prove","statement":"..."},'
            '"summary":"用2~3句中文总结本解法的核心方法与关键观察",'
            '"key_equations":["本证明中最核心的2~4个公式/方程,每个一条"]}\n'
            "6. 除数学公式外一律使用中文; 不要出现英文短语、英文工具名或代码。\n"
            "7. 最终答案只写你已通过 verify 验证的坐标/等式/结论; "
            "若答案附带几何标签(如\"即椭圆下顶点\"、\"即点A\"、\"垂足\"), "
            "必须在最后一步用 verify 验证该标签对应的几何关系是否成立, "
            "未验证的标签绝不能写进答案。\n"
            "8. key_equations 只写证明主线上的核心公式(如中点坐标公式、韦达定理结果、"
            "共线条件), 不要写特殊值数值验证的中间结果, 不要写代码输出。\n"
        )

    user = (
        mode_block
        + knowledge_block
        + experience_block
        + heuristic_block
        + verification_contract
        + "[Context]\n"
        f"# Geometry DSL\n{dsl}\n\n"
        f"# Problem\n{problem}\n\n"
        "[Task]\n"
        f"Goal: {goal}\n"
        f"(Detected subject: {subject_label or 'unknown'})\n\n"
        + instructions
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


__all__ = [
    "build_enhanced_prompt",
    "AREA_RATIO_HEURISTIC",
    "INEQUALITY_HEURISTIC",
    "FIXED_POINT_HEURISTIC",
    "ABSTRACT_PROOF_HEURISTIC",
    "EXPLORATION_PROMPT",
]
