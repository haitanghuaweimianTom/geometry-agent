# V2 改进文档 (V2_IMPROVEMENTS)

> 本文件记录 Geometry Agent 第二轮 (v2) 的全部改进：数学公式渲染、符号计算能力、
> PDF 生成可靠性、输入友好性与测试保障。所有改动均有自动化测试覆盖。

---

## 1. 数学公式渲染引擎全面升级 (`src/geometry_agent/report/__init__.py`)

### 1.1 负分数：负号固定在分数前面
- `x=-3/4` → `x=-\frac{3}{4}`（不再输出 `\frac{-3}{4}`）
- `3/-2` → `-\frac{3}{2}`（分母中的负号也提到分数前）
- `(-1)/(-2)` → `\frac{1}{2}`（分子分母同为负时直接消去）
- `\frac{-(x+1)}{2}` → `-\frac{x+1}{2}`（后处理统一去括号）

### 1.2 括号策略：该加必加、不该加不加
- 冗余括号自动去除：`(a+b)/(c+d)` → `\frac{a+b}{c+d}`
- 必要括号严格保留：
  - `(x-1)^2/4` → `\frac{(x-1)^{2}}{4}`
  - `(a+b)(c+d)/2` → `\frac{(a+b)(c+d)}{2}`
  - `2x/3` → `\frac{2x}{3}`（系数与变量组合）
- 括号匹配升级为可嵌套多组：`(a+b)(c+d)` 整体识别为一个分子

### 1.3 上标下标：绝对正确显示
- Unicode 上/下标 → LaTeX：`x²³` → `x^{23}`、`x₁₂` → `x_{12}`、`a⁵` → `a^{5}`
- 连续上标合并：`^{a}^{b}` → `^{ab}`（循环 3 次直至稳定）
- 下标归一：`xA` → `x_A`、`x1` → `x_{1}`
- 特殊上标：`¹` → `^1`、`⁻` → `^{-}`、`sin⁻¹x` → `\sin^{-1}x`

### 1.4 数学符号全覆盖
- 新增符号映射：∝ ± ∓ ÷ ≡ ⊂ ⊃ ⊆ ⊇ ∉ ∀ ∃ ⇒ ⇔ ⊙ □ ∟ ⋯ … ∼ ∘ ∂ ∑ ∏ ∫ ′ ∅ ⌒
- 补全希腊字母：ε η ι κ ν ξ ρ σ τ υ χ ψ ζ Θ Γ Π Υ Ψ Ω Λ Ξ Φ（原有 θαβγδφωλμΣΔ 保留）
- 单位直立显示：`cm²` → `\mathrm{cm}^{2}`（支持 cm/dm/mm/km/min）
- 弧符号：`⌒AB` → `\overset{\frown}{AB}`
- 三角形面积下标：`S△ABC` → `S_{\triangle ABC}`
- 函数名自动识别：sin/cos/tan/cot/sec/csc + 反三角 → `\sin` 等罗马体
- 平方根：`√2` → `\sqrt{2}`、`√(a+b)` → `\sqrt{a+b}`、`³√` 兼容处理

### 1.5 全角字符处理
- 全角括号/逗号/冒号在数学段内自动转半角：`（1，2）` → `(1,2)`
- 全角字符被纳入数学段判定，避免被切成普通文本

## 2. 符号计算工具扩展 (`src/geometry_agent/tools/algebra_tools.py`)

新增 12 个精确符号计算工具（全部基于 SymPy，返回 `result/result_latex/steps`）：

| 工具 | 功能 | 示例 |
|------|------|------|
| `solve_equation` | 解任意方程（多项式/三角/指数/对数），支持定义域过滤 | `x²-4=0` → `[-2, 2]`；`sin x=1/2` → `[π/6, 5π/6]` |
| `solve_inequality` | 解一元不等式，返回区间/区间并 | `x²-4>0` → `(-∞,-2)∪(2,+∞)` |
| `verify_identity` | 符号验证恒等式（差值化简为 0 即真） | `(x+1)²=x²+2x+1` → TRUE |
| `rationalize` | 分母有理化 | `1/(√2+1)` → `√2-1` |
| `simplify_trig` | 三角恒等变换化简 | `sin²x+cos²x` → `1` |
| `distance_two_points` | 两点间距离（精确，保留根号） | `(1,1),(3,5)` → `2√5` |
| `midpoint_formula` | 中点坐标 | `(1,2),(3,6)` → `(2,4)` |
| `line_equation` | 过两点直线一般式 | `(0,0),(2,4)` → `-4x+2y=0` |
| `collinear_check` | 三点共线判定（叉积=0） | 共线→True，不共线→False |
| `angle_between_lines` | 两直线夹角（tan 公式，支持无限斜率） | `k₁=1/2,k₂=-2` → 90° |
| `matrix_det` | 方阵行列式（含符号） | `[[a,b],[c,d]]` → `ad-bc` |
| `matrix_inverse` | 方阵求逆（精确分数） | `[[1,2],[3,4]]` → 分数矩阵 |

已在 `tools/registry.py` 注册：工具 schema 数从 32 → 44，推理 agent 可直接调用。

## 3. PDF 生成可靠性加固 (`src/geometry_agent/human_loop/pdf_compiler.py`)

- **`-file-line-error`**：错误定位到 `doc.tex:行号`，诊断信息可操作
- **友好错误提示**：常见错误自动翻译为中文提示（未知命令/括号不配对/数学模式/字体缺失），并附原始错误片段
- **救援清洗 (rescue sanitize)**：编译失败后自动修复结构性错误（补全 `\begin{document}`/`\end{document}`、花括号配对）并重试一次；内容性错误（未知命令）保持失败，绝不静默吞错
- **唯一文件名 (`unique_pdf_path`)**：`solution_to_pdf`/`multi_question_to_pdf` 默认不覆盖已存在文件，自动生成 `name_1.pdf`、`name_2.pdf`…
- **编译超时**：120s 超时转为明确中文错误

## 4. 报告版式美化 (preamble 升级)

`report/__init__.py` 与 `human_loop/latex_render.py` 的 preamble 同步升级：
- **titlesec**：章节标题统一大号粗体、间距优化（试卷风格）
- **fancyhdr**：页脚居中显示「第 X 页」，页眉清除（整洁留白）
- **`\allowdisplaybreaks`**：长公式允许跨页断行，不再溢出页边
- **hyperref**：彩色链接、PDF 书签（bookmarksnumbered），支持长文档导航

## 5. 输入友好化：全角字符自动归一 (`src/geometry_agent/normalize.py`)

新增共享输入归一化函数 `normalize_problem_text`，所有入口（CLI / Web UI / FastAPI）接入：
- 全角数字/字母 → 半角：`Ａ（１，２）` → `A(1,2)`
- 全角运算与标点 → 半角：`＋ － ／ ＝ ＜ ＞ ｜ ｛ ｝ ［ ］ ： ； ， （ ） ％` 等
- 全角空格 → 普通空格；U+2212 减号 → `-`
- **保留**：中文句读（。？！、）保证 PDF 中文排版美观；数学符号（× ÷ ² ³ ⁻ ⌒ ∠）交由渲染层处理
- 幂等：重复调用结果一致

## 6. 各入口体验改进

### Web UI (`web_ui.py`)
- **自动重试**：单题/多小题模式均增加 3 次重试（低置信度/定点数值校验失败自动重试）
- **友好错误**：推理失败与 PDF 生成失败均显示中文提示而非异常堆栈
- **修复 bug**：`solve_single` 返回值数量与 UI 组件不匹配的潜在崩溃

### CLI (`geometry_agent_cli.py`)
- **Ctrl+C 优雅退出**：交互模式中断返回输入循环；命令行模式退出码 130
- **PDF 失败提示**：失败时给出安装指引（`sudo apt install texlive-xetex texlive-lang-chinese`）

## 7. 测试保障

| 测试文件 | 覆盖内容 | 数量 |
|----------|----------|------|
| `tests/unit/test_report_math.py` | 负分数/括号策略/上下标/符号/单位/全角/根号等渲染规则 | 19 |
| `tests/unit/test_normalize.py` | 全角归一化（含幂等、保留规则） | 8 |
| `tests/unit/test_human_loop.py` | PDF 编译（含错误路径、TikZ 图形） | 17（既有） |

运行方式（pyz3 插件与 pytest 9 不兼容，需禁用）：

```bash
python3 -m pytest tests/unit/ -p no:pyz3 -q    # 179 passed
python3 -m pytest tests/regression/ -p no:pyz3 -q  # 9 passed
```

> 注：`tests/e2e/` 依赖 OCR 模型与 LLM 环境，离线环境会挂起，属既有行为。

## 8. 变更文件清单

| 文件 | 变更 |
|------|------|
| `src/geometry_agent/report/__init__.py` | 数学渲染引擎重写 + preamble 美化 |
| `src/geometry_agent/human_loop/latex_render.py` | preamble 美化（图形审阅文档） |
| `src/geometry_agent/human_loop/pdf_compiler.py` | 编译加固（唯一文件名/救援清洗/友好错误） |
| `src/geometry_agent/tools/algebra_tools.py` | **新增** 12 个符号计算工具 |
| `src/geometry_agent/tools/registry.py` | 注册新工具（32 → 44 schemas） |
| `src/geometry_agent/normalize.py` | **新增** 输入归一化模块 |
| `geometry_agent_cli.py` | 归一化接入 + Ctrl+C 处理 + PDF 失败提示 |
| `web_ui.py` | 归一化接入 + 重试循环 + 友好错误 + bug 修复 |
| `src/geometry_agent/api/server.py` | 归一化接入 |
| `tests/unit/test_report_math.py` | **新增** 19 条渲染测试 |
| `tests/unit/test_normalize.py` | **新增** 8 条归一化测试 |
