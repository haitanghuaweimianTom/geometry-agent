# Geometry Agent 系统设计文档集

> 本目录为 Geometry Agent 系统的完整设计文档集。系统目标是利用大语言模型（LLM）解决中国中考、高考数学几何题，采用**神经符号混合、多阶段、可验证**架构，刻意避免 `图片 → LLM → 答案` 的端到端范式。

## 文档索引

| 编号 | 文档 | 内容 |
| --- | --- | --- |
| 00 | [总体架构设计](./00-Overview.md) | 项目背景、VLM 失效分析、Geometry World Model、系统总架构、数据契约 |
| 01 | [Geometry Parser 设计](./01-Geometry-Parser.md) | 三段式解析流水线、预处理、异构检测器调度、标注关联、降级策略 |
| 02 | [几何对象检测算法](./02-Detection-Algorithms.md) | 点/直线/圆/椭圆检测算法详解、拟合数学、RANSAC、边界处理 |
| 03 | [Geometry Graph 设计](./03-Geometry-Graph.md) | 图 Schema、节点/边形式化、构建算法、查询接口、增量更新 |
| 04 | [Relation Extraction Agents](./04-Relation-Agents.md) | Multi-Agent 架构、各 Agent 判定算法、并行调度、冲突解决 |
| 05 | [Constraint Verification Engine](./05-Verifier.md) | 验证器体系、自适应容差模型、验证日志、闭环协议 |
| 06 | [Geometry DSL 设计](./06-DSL.md) | EBNF 语法、类型系统、解析器/序列化器、反事实编辑 |
| 07 | [LLM Reasoning Agent](./07-LLM-Agent.md) | Prompt 模板、CoT/ToT/Reflection/Voting、工具调用、上下文管理 |
| 08 | [Symbolic Solver](./08-Symbolic-Solver.md) | SymPy/Z3/自研引擎/Lean 集成、LLM-Solver 分工 |
| 09 | [数据集设计](./09-Dataset.md) | 标注 Schema、程序化合成引擎、风格增强、真题标注、质量评估 |
| 10 | [无后训练优化策略](./10-Optimization.md) | Prompt/RAG/Tool/Reflection/Voting 详解与组合 |
| 11 | [工程实现方案](./11-Engineering.md) | 技术栈、接口定义、项目结构、部署、可观测性、测试 |
| 12 | [开发路线图](./12-Roadmap.md) | 五阶段任务分解、依赖、验收指标、里程碑、风险 |
| 13 | [附录](./13-Appendix.md) | 术语表、容差默认值、风险对策、评估指标、参考文献 |

## 阅读顺序建议

- **决策者/架构评审**：00 → 12 → 13
- **算法工程师**：00 → 01 → 02 → 04 → 05
- **推理方向工程师**：00 → 03 → 06 → 07 → 08
- **数据工程师**：00 → 09 → 11
- **全栈实现**：按编号顺序通读

## 设计原则速览

| 原则 | 含义 |
| --- | --- |
| 不依赖大规模后训练 | 充分利用开源模型 + 传统 CV + 符号求解 |
| 高准确率优先 | 感知层追求精确，宁可召回不足也不要错误关系 |
| 可解释 | 每一步输出可追溯，证明过程可读 |
| 可验证 | 所有几何关系由数值/符号验证器判定真伪 |
| 可扩展 | 模块化设计，新对象/关系可独立加入 |
| 低成本数据 | 程序化合成 + 少量人工标注 |

## 版本

- v1.0：初版设计基线
