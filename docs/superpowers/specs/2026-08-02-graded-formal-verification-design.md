# 三档分阶几何推理系统:引理库/每步验证/Lean远程

**日期**: 2026-08-02
**状态**: Draft

## 目标

将 Geometry Agent 从"LLM+SymPy启发式求解器"升级为带每步形式化验证的三档推理系统:

1. **初中模式**: 本地轻量符号步进验证(SymPy/Z3) + 初中引理库
2. **高中模式**: 本地轻量符号步进验证(SymPy/Z3) + 高中引理库
3. **竞赛模式**: 远程 Lean 4 编译验证(rdzs02) + 竞赛引理库

验证失败处理: 重试该步 ≤3 次 → 仍失败则 LLM-judge 兜底,答案带存疑标记继续。

## 非目标

- 不重写推理主循环(沿用 enhanced_agent._run_feedback_loop)
- 不引入 Lean 常驻本地 server(资源约束)
- 不做整段翻译为 Lean 的批量验证(不满足每步验证)
- 竞赛模式暂时不覆盖立体几何(现有 subject-grade 兼容性已排除)

## 架构

```
LLM 产出 step(通过 tool_call)
    ↓
StepVerifier 中间件 (新增)
    ├─ 按 grade 路由:
    │    junior/senior → SymbolicStepVerifier (本地 SymPy/Z3)
    │    competition  → LeanStepVerifier   (HTTP → rdzs02:9407/verify)
    ├─ 通过 → 注入 verified=True 反馈
    ├─ 不过 → 重试该步(≤3),每次给 LLM 失败原因
    └─ 3 次后仍失败 → LLMJudge.verdict → 标记 verified=uncertain 继续
```

## 组件

### 1. StepVerifier 中间件 (`src/geometry_agent/verification/__init__.py`)

**接口**:
```python
class StepVerifier(Protocol):
    def verify(self, step: Step, premises: list[Step]) -> Verdict: ...

class Verdict(BaseModel):
    verified: Literal["true", "false", "uncertain"]
    evidence: str           # 符号化简结果/Lean编译输出/judge理由
    reason: str             # 失败时的人可读原因
    lean_source: str | None = None  # 竞赛模式:生成的Lean代码
```

**注入点**: `_run_feedback_loop` 中工具结果返回后、`_build_feedback` 前。若工具调用产出了一个结论性 step(新 `claim_step` 工具或在 `solve`/`verify` 结果中出现新等式/关系),则触发 StepVerifier。

**新工具 `claim_step`**: 让 LLM 显式声明一步结论及其依据,由 StepVerifier 验证后才进入下一步。这把"证明义务"结构化,避免隐式结论跳过验证。

```python
# tools.py 新增
{
  "name": "claim_step",
  "parameters": {
    "statement": "要断言的结论(中文+公式,如 AB·AC = AD·AE)",
    "premises": ["所依赖的已验证结论ID"],
    "justification": "使用的引理ID或方法"
  }
}
```

`claim_step` 返回 `Verdict`,验证失败时 `_build_feedback` 把 reason 回灌给 LLM 触发重试。

### 2. SymbolicStepVerifier (`src/geometry_agent/verification/symbolic.py`)

初中/高中模式使用。核心逻辑:

- 将 `statement`(中文+公式)解析为 SymPy 表达式/关系
- 将 `premises`(已验证步)加入假设集
- 用 SymPy `simplify`/`solveset`/`refine` 检查 `conclusion - premises` 是否化简为 0/True
- 几何关系(平行/垂直/共线)走 Z3 求解器:构造几何约束模型,检查结论是否在所有满足前提的模型中成立
- 三角恒等式用 SymPy `trigsimp`
- 返回 `Verdict(verified=bool, evidence=simplified_expr)`

资源:本地进程内调用,单步验证 <200ms,无额外进程。

### 3. LeanStepVerifier (`src/geometry_agent/verification/lean_client.py`)

竞赛模式使用。核心逻辑:

- 将 `statement` 翻译为 Lean 4 命题(模板+规则映射,不是通用翻译器)
- 复用前提步的 Lean 上下文(每步累积 `have` 语句)
- POST 到 rdzs02 Lean 服务,带超时 10s
- 解析编译输出:`error:` 行 → 失败;`warning:` 但通过 → 通过带 warning;其他 → 通过
- 返回 `Verdict(verified=bool, evidence=lean_output, lean_source=source)`

**翻译模板覆盖**:
- 线段相等/比例: `Eq (dist A B) (dist C D)`
- 平行/垂直: `Parallel`/`Perpendicular` 谓词
- 共线/共圆: `Collinear`/`Concyclic`
- 角相等: `Eq (angle A B C) (angle D E F)`
- 代数等式:直接 `ring`/`linarith`/`nlinarith`/`field_simp` 战术
- 三角:Real.sin/cos/tan

注:翻译器是模板覆盖的,不是通用 N2F;竞赛模式证明主体由 LLM 产出策略,验证只做"给定前提+结论是否成立"的检查。

### 4. Lean HTTP 服务(rdzs02:9407)

**部署**:rdzs02(10.42.0.124, Ubuntu 24.04, Docker 29, 6核/6GB可用)。

**方案**:Docker 容器跑 `leanprover/lean4:stable` 镜像,一个轻量 Python FastAPI 服务接收 `{"premises": [...], "conclusion": "..."}`,写入临时 `.lean` 文件,调用 `lake env lean` 编译,返回结果。不常驻 lake server,每次请求独立进程,内存峰值 ~500MB,空闲 0。

**端口**:9407(rdzs02 现有端口:22/5902/8080-8083/8384/22000/38609,9407 未占用)。

**API**:
```
POST /verify
Body: {"premises": ["have h1 : ...", ...], "conclusion": "..."}
Response: {"verified": bool, "output": "stdout+stderr", "elapsed_ms": int}
GET /health → {"status":"ok"}
```

**部署脚本**:`scripts/deploy_lean_service.sh`(一键:建 Dockerfile+docker compose,启动,health check)。本机 geometry_agent 配置 `lean.endpoint = "http://10.42.0.124:9407"`。

### 5. LLMJudge (`src/geometry_agent/verification/llm_judge.py`)

3 次重试后仍失败时调用。用现有 LLM 客户端(配置同 reasoning),发结构化 prompt:

```
以下步骤验证失败3次:
前提:{premises}
尝试结论:{statement}
失败原因:{reasons}
请判定:
1. 该结论是否在前提成立时必然成立?(yes/no/uncertain)
2. 如果不成立,反例是什么?
3. 如果成立,给出一个更清晰的证明路径。
```

返回 `Verdict(verified="uncertain" if uncertain else False, evidence=judge_response)`。uncertain 的结论进入最终 plan 但带 `verified="uncertain"` 标记,最终答案里标注存疑。

### 6. 重试逻辑(enhanced_agent.py)

在 `_run_feedback_loop` 中,工具结果返回后:

1. 若工具是 `claim_step` → 调 StepVerifier
2. Verdict.verified==True → 把 step 加入 `verified_steps: list[Step]`,feedback 标 `verified=True`
3. Verdict.verified==False → feedback 注入失败 reason,LLM 重新生成(计入 retry_count),**不推进** total_calls 计数
4. retry_count≥3 → 调 LLMJudge,judge 通过则标记 uncertain 继续;不通过则 reflect 换方法

现有 `consecutive_failures` 反射逻辑保留,与重试计数器独立。

### 7. 三档引理库

#### 7.1 现有结构扩展

`KnowledgeEntry` 新增 `grade` 字段(已有)、`formal_id`(Lean/符号引擎引用,新增)、`proof_hint`(给 LLM 的使用提示,新增)。

```python
class KnowledgeEntry(BaseModel):
    id: str
    subject: SubjectType
    title: str
    content: str
    method_priority: MethodPriority
    tags: list[str]
    applies_to: list[str]
    grade: GradeLevel
    formal_id: str = ""         # SymPy/Z3 调用名或 Lean 定理名
    proof_hint: str = ""        # "用xxx定理"一类提示
```

#### 7.2 扩充规模

- **初中(junior)**:从现有 ~60 条扩充到 ~150 条。补全:全等辅助线、圆幂、四点共圆判定、面积法、中位线、角平分线定理等中考常考引理
- **高中(senior)**:从现有 ~100 条扩充到 ~250 条。补全:圆锥曲线常用结论(焦点弦/中点弦/极线)、向量法模板、导数不等式、空间向量、计数概率模型
- **竞赛(competition)**:新增 ~200 条。包含:射影几何(极点极线/Desargues/Pascal/Brianchon)、三角恒等变换高级技巧、复数法/反演/根轴/调和点列、不等式技巧(AM-GM/Cauchy/Schur/Muirhead)、数论组合基础

手工扩充优先质量,公开数据集(GeoQA+/UniGeo 等)清洗后作为补充,所有条目人工 review 后入库。

#### 7.3 公开数据集导入工具

新增 `scripts/import_lemma_dataset.py`:
- 下载 GeoQA+/UniGeo 等公开几何数据集
- 按 subject/grade 过滤
- 去重(与现有 entries 向量相似度 >0.9 跳过)
- 输出待 review 的 YAML,人工审核后合入 curated.py

### 8. 配置

`configs/default.yaml` 新增:
```yaml
verification:
  enabled: true
  max_retries: 3
  symbolic:
    timeout_ms: 200
    z3_timeout_ms: 1000
  lean:
    endpoint: "http://10.42.0.124:9407"
    timeout_s: 10
    enabled_in_competition_only: true
  llm_judge:
    enabled: true
```

`GradeLevel` 已存在,`KnowledgeManager.get_knowledge` 已按 grade 过滤,无需大改。`_run_feedback_loop` 通过 `self.grade` 路由到对应验证器。

### 9. Prompt 改动

`prompt_builder.py` 在系统 prompt 注入验证协议:
- 初中/高中模式: "每得出一个非平凡结论(非单纯计算),必须先用 claim_step 工具声明,等待验证通过后再继续"
- 竞赛模式: 同上,但 claim_step 会自动走 Lean 验证;鼓励用 Lean 常见战术名辅助翻译

## 数据流

```
用户输入(problem, grade)
    ↓
classify_subject → KnowledgeManager.get_knowledge(grade)
    ↓
build_enhanced_prompt(knowledge, verification_contract)
    ↓
_run_feedback_loop:
    LLM 产出 tool_calls
        ↓
    dispatch(name, args) → result
        ↓
    if name == "claim_step":
        verifier = {junior:Symbolic, senior:Symbolic, competition:Lean}[grade]
        verdict = verifier.verify(statement, premises)
        if verdict.verified:
            feedback = "✓ 已验证"  + evidence
            verified_steps.append(step)
        else:
            retries[step.id] += 1
            if retries[step.id] < 3:
                feedback = f"✗ 验证失败: {verdict.reason},请修正重述"
            else:
                judge = LLMJudge(...)
                if judge.verified:
                    feedback = "⚠ LLM-judge判定成立(存疑)"
                else:
                    feedback = "✗ judge判定不成立,换方法"
                    trigger reflect
    else:
        feedback = _build_feedback(result)  # 现有逻辑
    ↓
    messages.append(feedback) → 下一轮 LLM 调用
    ↓
_synthesize_plan(tool_log, goal, verified_steps)
    ↓
PDF 报告(带 ✓/✗/⚠ 标记每步验证状态)
```

## 错误处理

| 场景 | 处理 |
|---|---|
| rdzs02 Lean 服务不可达 | 竞赛模式降级为 SymbolicStepVerifier + 警告,不阻塞 |
| Lean 编译超时(>10s) | 视为一次验证失败,计 retry,3次后走 judge |
| SymPy 化简不定(既不恒为0也不矛盾) | 返回 Uncertain,走 judge |
| claim_step 漏用(LLM 不调) | 在 nudge 中提醒;最后合成前做一次兜底扫描 |
| Z3 超时(>1s) | 返回 Uncertain,走 judge |

## 测试

1. **单元测试**(`tests/unit/`):
   - `test_symbolic_verifier.py`: 50+ 代数/几何/三角命题验证,覆盖真/假/不确定
   - `test_lean_client.py`: mock HTTP,验证请求构造和响应解析
   - `test_llm_judge.py`: mock LLM,验证 verdict 输出
   - `test_verification_middleware.py`: 注入点测试,验证重试计数和路由
   - 引理库条目逐一验证正确性(symbolic 模式下可验证的引理必须 verified=True)

2. **集成测试**(`tests/e2e/`):
   - 5 道初中题(含中考)
   - 5 道高中题(含高考)
   - 3 道竞赛题(IMO 预选/联赛难度)
   - 每道题所有 claim_step 必须 verified=True 或 uncertain,不允许 False 进入最终 plan

3. **真实考题回归**:复用现有 `/tmp/opencode/real_exam_test.py` 框架,42 题必须全部通过且验证通过率统计。

## 部署顺序(实施计划的自然阶段)

1. **Phase 1 — 验证框架骨架**
   - `verification/` 模块,`StepVerifier` 协议,`claim_step` 工具
   - `_run_feedback_loop` 注入点
   - 单测框架跑通

2. **Phase 2 — SymbolicStepVerifier**
   - SymPy 代数/三角验证
   - Z3 几何关系验证
   - 3 次重试 + LLM-judge 兜底

3. **Phase 3 — 引理库扩充**
   - 初中/高中手工扩充
   - 竞赛引理(手工核心 + 数据集导入清洗)
   - `formal_id`/`proof_hint` 字段填充

4. **Phase 4 — Lean 服务部署(rdzs02)**
   - Docker + FastAPI 服务
   - `scripts/deploy_lean_service.sh`
   - `LeanStepVerifier` 客户端
   - 竞赛模式接通

5. **Phase 5 — 端到端验收**
   - PDF 报告加 ✓/✗/⚠ 标记
   - 42 题回归
   - 竞赛题验证
   - 性能基准:初中/高中题验证开销 <10% 总耗时

## 资源预算

| 组件 | 本地内存 | CPU | 说明 |
|---|---|---|---|
| SymbolicStepVerifier | ~50MB(SymPy/Z3 进程内) | <100ms/步 | 无额外进程 |
| LLMJudge | 0(复用现有 LLM 连接) | - | 仅 3 次重试后调用 |
| LeanStepVerifier | 0(远程) | - | 网络调用,rdzs02 侧每次 ~500MB 峰值 |
| Lean 服务(rdzs02) | 空闲 0,峰值 500MB | i5-8500 6核,每请求 <5s | Docker,按需起进程 |
| 引理库 | <10MB 内存 | - | 纯文本 |

对比现状(单 TUI ~1GB,event 表 303MB 已清理),新增开销 <100MB 本地,竞赛模式内存负载转移到 rdzs02,满足"不吃本地资源"约束。
