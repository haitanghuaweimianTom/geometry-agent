# 📐 Geometry Agent

> 中文几何题智能解题系统 · 神经-符号混合推理（LLM + SymPy/Z3 + 符号验证）
>
> 输入一道初中 / 高中 / 竞赛几何题，系统自主完成"读题 → 建模 → 推理 → 符号验证 → 数值交叉校验 → 生成 PDF 解答报告"全流程。

---

## ✨ 功能特性

- **全中文解题**：支持平面几何、解析几何（圆锥曲线）、立体几何、函数导数等题型
- **神经-符号混合推理**：LLM 主导策略，SymPy / Z3 / 韦达定理等结构化工具做精确计算与验证
- **先猜后证**：对定点 / 不等式 / 面积比等问题内置专用启发式（如特殊值猜点 + 数值交叉校验）
- **自动验证**：每步结论调用 `verify` 工具确认；定点问题额外做 3 组参数的数值交叉校验，不通过自动重试
- **离线推理**：默认 `web_enabled=false`，全程不联网，所有计算本地完成
- **PDF 报告**：生成带题目 / 几何图形 / 解答步骤 / 答案 / 解题思路 / 关键算式的中文 LaTeX PDF
- **Web 界面**：FastAPI 后端 + 原生 HTML/JS 前端，输入题目即出 PDF，支持单题 / 多小题模式
- **多学段**：初中（junior）/ 高中（senior）/ 竞赛（competition），按学段注入不同知识与方法

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                      用户输入题目                          │
│  (CLI / Web UI / API)                                    │
└──────────────┬───────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────┐
│  1. 感知层 Perception                                    │
│     OCR + 图像分析 → 几何元素提取 (点/线/圆/角)            │
└──────────────┬───────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────┐
│  2. 图谱层 Graph                                         │
│     构建 GeometryGraph，计算平行/垂直/相切/共线等关系       │
└──────────────┬───────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────┐
│  3. 推理层 Reasoning (核心)                               │
│     EnhancedReasoningAgent:                              │
│     ┌─────────────────────────────────────────────┐      │
│     │  LLM (GLM-5.2) 主导策略                     │      │
│     │  + 32 个结构化工具 (solve/verify/execute_code│      │
│     │    /vieta_theorem/polynomial_factor/...)    │      │
│     │  + 知识库检索 (定理/方法)                    │      │
│     │  + 反思重试 (reflect)                       │      │
│     │  + 启发式注入 (定点/不等式/面积比)           │      │
│     └─────────────────────────────────────────────┘      │
│     输出: ProofPlan (步骤 + 答案 + 解题思路 + 关键算式)    │
└──────────────┬───────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────┐
│  4. 验证层 Verification                                  │
│     数值交叉校验 (定点问题取 3 组参数验证)                 │
│     不通过 → 自动重试 (最多 3 次, 每次全新 agent)          │
└──────────────┬───────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────┐
│  5. 报告层 Report                                        │
│     LaTeX (ctexart) → PDF                                │
│     含: 题目/图形/解答步骤/答案/解题思路/关键算式          │
└──────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Python ≥ 3.10
- 一个 OpenAI 兼容的 LLM API（GLM / OpenAI / DeepSeek 等均可）
- LaTeX 发行版（xelatex，用于生成 PDF；Ubuntu 安装：`sudo apt install texlive-xetex texlive-lang-chinese`）

### 安装

```bash
git clone https://github.com/haitanghuaweimianTom/geometry-agent.git
cd geometry-agent
pip install -e ".[dev]"
```

### 配置 LLM 密钥

复制配置模板，填入你自己的 API 密钥：

```bash
cp configs/default.example.yaml configs/default.yaml
# 编辑 configs/default.yaml, 填写 llm.api_key 和 llm.base_url
```

或使用环境变量（推荐，优先级高于配置文件）：

```bash
export LLM_API_KEY="your-key"
export LLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export LLM_MODEL="GLM-5.2"
```

---

## 💻 使用方式

### 方式一：Web 界面（推荐）

```bash
uvicorn geometry_agent.api.server:app --host 0.0.0.0 --port 8000
```

浏览器打开 http://localhost:8000 ，输入题目、选学段、点"开始求解"，出 PDF 下载。

### 方式二：命令行（单题）

```bash
python geometry_agent_cli.py solve \
  --text "设椭圆Γ: x²/4 + y²/3 = 1，过Γ内部一点A(1,1)作斜率之和为1的直线MN和PQ，分别交椭圆于点M,N和点P,Q。设MN中点为B，PQ中点为C，证明：直线BC过定点。" \
  --grade senior --max-calls 60
```

### 方式三：命令行（多小题）

```bash
python geometry_agent_cli.py multi \
  --text "已知椭圆E的中心为坐标原点，对称轴为x轴、y轴，且过A(0,-2), B(3/2,-1)两点。" \
  --subs "(1) 求E的方程" "(2) 证明直线HN过定点" \
  --grade senior --max-calls 60
```

### 方式四：Gradio 界面

```bash
python web_ui.py
# 打开 http://localhost:7860
```

### 方式五：REST API

```bash
curl -X POST http://localhost:8000/api/solve \
  -H "Content-Type: application/json" \
  -d '{"text":"证明：三角形内角和为180度","grade":"junior","max_calls":40}'
```

---

## 📝 解题示例

### 椭圆定点问题（高中）

**题目**：设椭圆 Γ: x²/4 + y²/3 = 1，过 Γ 内部一点 A(1,1) 作斜率之和为 1 的直线 MN 和 PQ，分别交椭圆于 M,N 和 P,Q。MN 中点为 B，PQ 中点为 C，证明：直线 BC 过定点。

**系统输出**：
- ✅ 答案：直线 BC 恒过定点 F(0, -3/4)
- 🔍 数值校验：取 k=0.1/0.25/0.37/0.9 四组参数，叉积误差均 ≤ 1.4e-17，VERIFIED
- 📄 PDF 报告含点差法中点公式、共线条件、关键相消等式

### Rt△ 面积比问题（初中，多小题）

**题目**：在 Rt△ABC 中，∠BAC=90°，AC=2√5，点 D 在 AB 上且 AD:DB=1:3...

**系统输出**：CE=4；BD²=9·DE·DC；S△BEF/S△BDE=2，三问全部验证通过。

---

## 🔧 配置说明

主配置文件 `configs/default.yaml`（从 `default.example.yaml` 复制）。关键项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `llm.model` | 模型名 | GLM-5.2 |
| `llm.api_key` | API 密钥（建议用环境变量） | "" |
| `llm.base_url` | OpenAI 兼容端点 | — |
| `llm.max_tool_calls` | 最大推理步数 | 60 |
| `llm.max_tokens` | 单次响应最大 token | 8192 |
| `knowledge.web_enabled` | 是否联网搜索（默认关闭） | false |
| `code_exec.timeout_sec` | 代码执行超时 | 10 |

环境变量（优先级最高）：

| 变量 | 作用 |
|------|------|
| `LLM_API_KEY` | 覆盖 `llm.api_key` |
| `LLM_BASE_URL` | 覆盖 `llm.base_url` |
| `LLM_MODEL` | 覆盖 `llm.model` |

---

## 🧪 测试

```bash
pytest tests/unit/ -p no:pyz3 -q
```

---

## 📂 项目结构

```
geometry-agent/
├── src/geometry_agent/
│   ├── api/server.py          # FastAPI 后端
│   ├── reasoning/             # 推理核心
│   │   ├── enhanced_agent.py  # 增强推理 agent (反馈循环 + 重试)
│   │   ├── prompt_builder.py  # 提示构建 + 启发式注入
│   │   └── tools.py           # 32 个结构化工具
│   ├── perception/            # OCR + 图像感知
│   ├── graph/                 # 几何图谱
│   ├── knowledge/             # 定理知识库
│   ├── report/__init__.py     # LaTeX/PDF 报告生成
│   └── types.py               # 数据模型
├── static/                    # Web 前端 (HTML/CSS/JS)
├── configs/                   # 配置文件
├── tests/unit/                # 单元测试
├── geometry_agent_cli.py      # CLI 入口
├── web_ui.py                  # Gradio UI
└── pyproject.toml
```

---

## 🛠️ 技术栈

- **LLM**：GLM-5.2（或任意 OpenAI 兼容模型）
- **符号计算**：SymPy, Z3
- **后端**：FastAPI + Uvicorn
- **前端**：原生 HTML/CSS/JS（无构建依赖）
- **PDF**：LaTeX (ctexart + xelatex)
- **测试**：pytest

---

## 📄 License

MIT
