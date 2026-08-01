# 13 · 附录

> 本附录汇集术语表、关键容差默认值、风险对策、评估指标与参考文献。

---

## 1. 术语表

| 术语 | 含义 |
| --- | --- |
| VLM | Vision Language Model，视觉语言模型 |
| Geometry World Model | 几何世界模型，结构化几何对象与关系的内部表示 |
| Primitive | 几何原语，最小几何对象单元 |
| Geometry Graph | 几何知识图谱 |
| DSL | Domain-Specific Language，几何领域专用语言 |
| Verifier | 约束验证引擎 |
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| CoT | Chain-of-Thought，思维链 |
| ToT | Tree-of-Thoughts，思维树搜索 |
| Self-Reflection | 自我反思（失败回溯修正） |
| Self-Consistency Voting | 多路径投票 |
| SAM | Segment Anything Model，零样本分割模型 |
| LSD | Line Segment Detector |
| RANSAC | Random Sample Consensus，随机采样一致性 |
| LM | Levenberg-Marquardt，非线性最小二乘优化 |
| Kasa 拟合 | 圆的代数最小二乘拟合 |
| Fitzgibbon 拟合 | 椭圆直接最小二乘拟合 |
| SMT | Satisfiability Modulo Theories |
| Lean | Lean 4 定理证明助手 |

---

## 2. 关键容差默认值

| 关系 | absolute_tol | relative_tol | scale |
| --- | --- | --- | --- |
| On (点在线) | 2.0 px | 0.5% | 线长 |
| On (点在圆) | 2.0 px | 1.5% | 半径 |
| Perpendicular | 3° | — | — |
| Parallel | 3° | — | — |
| Tangent (直线切圆) | 2.0 px | 1.5% | 半径 |
| Tangent (两圆) | 2.0 px | 1.5% | (r1+r2) |
| Equal (线段等长) | — | 2% | 平均长度 |
| Equal (角相等) | 2° | — | — |
| EllipseSum | — | 1.5% | 2a |
| Collinear | 2.0 px | 0.5% | 包围盒对角线 |
| Concentric | 2.0 px | 1% | 平均半径 |

### 2.1 三态判定
设 $e = |\text{measured} - \text{expected}|$，$\text{tol}=\max(\text{abs}, \text{rel}\times\text{scale})$：
- $e \le \text{tol}$ → `true`
- $\text{tol} < e \le 3\cdot\text{tol}$ → `uncertain`
- $e > 3\cdot\text{tol}$ → `false`

---

## 3. 风险与对策汇总

| 风险 | 影响 | 对策 | 详见 |
| --- | --- | --- | --- |
| 手绘图质量差 | 检测召回下降 | RANSAC + 多假设 + 低置信标记 | 01,02 |
| LLM 幻觉 | 编造未验证关系 | 强制 Tool Calling + Verifier 闭环 | 05,07 |
| 关系歧义 | 多候选无法消歧 | 保留多假设，LLM 上下文消歧 | 03,04 |
| 定理库不全 | RAG 漏检 | 持续扩充 + 教材整理 | 08,09 |
| 计算延迟 | 多 Agent + ToT 慢 | 并行化 + 路径剪枝 + 缓存 | 04,07,11 |
| 合成→真实域差距 | 真题准确率低 | 风格增强 + 真题精标迭代 | 09 |
| 验证器自身错误 | 全系统失效 | 合成回归测试 + 单元测试 + 交叉验证 | 05 |
| Phase 5 Lean 成本高 | 延期 | 可选阶段，不阻塞主线 | 12 |

---

## 4. 评估指标

| 指标 | 定义 | 目标 |
| --- | --- | --- |
| 检测准确率 | Primitive 检测 Precision/Recall | P/R ≥ 0.9（合成） |
| 关系验证准确率 | Verifier 判定与真值一致率 | ≥ 0.95 |
| 端到端答案准确率 | 最终答案与标准答案一致率 | ≥ 0.7（真题） |
| 证明正确率 | 证明链可被 Solver/Lean 校验通过率 | ≥ 0.6（Phase 5） |
| 幻觉率 | 未验证关系进入结论的比例 | < 5% |
| 可解释性评分 | 人工评估证明可读性（1-5） | ≥ 4 |
| 端到端延迟 P95 | 95 分位单题延迟 | < 60s |
| 投票一致性 | 多路径答案一致率 | ≥ 0.8 |

---

## 5. 数据结构速查

### 5.1 PrimitiveSet
```json
{"points":[...],"segments":[...],"circles":[...],"ellipses":[...],
 "arcs":[...],"polygons":[...],"marks":[...],"metadata":{...}}
```

### 5.2 GeometryGraph
```json
{"graph_version":"1.0","nodes":[...],"edges":[...],"metadata":{...}}
```

### 5.3 Edge
```json
{"src":"P_A","dst":"C_O","rel":"On","confidence":0.98,
 "verified":"true","evidence":"...","attrs":{...}}
```

### 5.4 VerifyResult
```json
{"verified":"true","evidence":"...","measured":{...},"attrs":{...}}
```

### 5.5 Solution
```json
{"answer":"...","proof":[...],"confidence":0.93,
 "verified":true,"verification_log":[...]}
```

---

## 6. 工具调用接口速查

| 工具 | 签名 | 返回 |
| --- | --- | --- |
| verify | `verify(relation, src, dst, attrs)` | VerifyResult |
| solve | `solve(equations, goal)` | Solution |
| search | `search(query)` | list[Theorem] |
| reflect | `reflect(failure, plan)` | revised_plan |
| graph_query | `graph_query(q)` | subgraph/facts |
| construct | `construct(obj_desc)` | new node |

---

## 7. 模块职责速查

| 模块 | 输入 | 输出 | 详见 |
| --- | --- | --- | --- |
| Geometry Parser | image, text | PrimitiveSet | 01,02 |
| Graph Builder | PrimitiveSet | GeometryGraph(候选) | 03 |
| Relation Agents | GeometryGraph | RelationCandidates | 04 |
| Verifier | Candidates + Graph | VerifiedGraph | 05 |
| DSL Serializer | GeometryGraph | DSL 文本 | 06 |
| LLM Agent | DSL + problem + tools | ProofPlan | 07 |
| Symbolic Solver | ProofPlan + Graph | Solution | 08 |

---

## 8. 参考文献（建议阅读）

> 以下为设计参考的理论与方法来源（实现阶段可深入阅读）。

1. **Neuro-Symbolic Reasoning**：神经符号混合推理范式。
2. **SAM**：Kirillov et al., *Segment Anything*, 2023.
3. **LSD**：Von Gioi et al., *LSD: A Line Segment Detector*, 2012.
4. **Fitzgibbon 椭圆拟合**：Fitzgibbon et al., *Direct least square fitting of ellipses*, 1999.
5. **Kasa 圆拟合**：Kasa, *A circle fitting procedure and its error analysis*, 1976.
6. **Tree-of-Thoughts**：Yao et al., *Tree of Thoughts*, 2023.
7. **Self-Consistency**：Wang et al., *Self-Consistency Improves Chain of Thought Reasoning*, 2022.
8. **Z3**：de Moura & Bjørner, *Z3: An Efficient SMT Solver*.
9. **Lean 4**：The Lean Theorem Prover.
10. **GeoQA / Geometry3K**：几何题数据集参考。
11. **人教版初高中数学教材**：定理库来源。

---

## 9. 文档版本

- v1.0：初版设计基线，拆分为 14 个子文档（README + 00~13）。
