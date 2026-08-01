# 01 · Geometry Parser 设计

> 本文档阐述感知层 Geometry Parser 的完整设计路线：三段式解析流水线、预处理各步骤算法、异构检测器调度策略、几何拟合、标注关联，以及错误处理与降级机制。具体检测算法（点/线/圆/椭圆）的数学细节见 [02-检测算法](./02-Detection-Algorithms.md)。

---

## 1. 设计目标与挑战

### 1.1 目标
从原始试卷图像中提取**结构化几何原语（Primitive）**，覆盖中考、高考几何题全部图元。Parser 的准确性决定后续所有模块的上限，故本层遵循"**高准确率优先**"原则：宁可召回不足，也不输出错误关系。

### 1.2 输入输出
- **输入**：试卷图像（PNG/JPG，可能含印刷体/手绘体、噪声、倾斜、光照不均）+ 题目文字。
- **输出**：`PrimitiveSet`（带标签、坐标、方程、置信度的原语集合）。

### 1.3 挑战
| 挑战 | 表现 | 应对 |
| --- | --- | --- |
| 图像质量差 | 模糊、低对比、抖动 | 预处理 + RANSAC 鲁棒拟合 |
| 文字干扰 | 标签字母被误检为线段 | OCR 定位 + mask |
| 倾斜 | 垂直/平行关系判定偏差 | 倾斜校正 |
| 手绘抖动 | 拟合残差大 | 多假设 + 降级标记 |
| 图元重叠 | 共线段、同心圆 | 拟合后分裂 + 一致性校验 |
| 标注符号多样 | 角标/等长/平行标记风格不一 | 轻量 YOLO 微调 |

---

## 2. 原语体系

系统定义如下原语类型，覆盖全部图元：

| 原语 | 符号 | 关键属性 | 备注 |
| --- | --- | --- | --- |
| Point | P | (x,y), label | 顶点/交点/标注点 |
| Line | L | 方向向量、过点 | 无限长直线 |
| Segment | S | 两端点 | 有限线段 |
| Ray | R | 起点、方向 | 射线 |
| Circle | C | 圆心、半径 | |
| Arc | Arc | 圆心、半径、起止角 | 圆弧 |
| Ellipse | E | 中心、长轴、短轴、倾角 | |
| Polygon | Poly | 顶点序列 | 三角形/四边形 |
| AngleMark | ∠ | 顶点、两边、度数 | 角度标注 |
| EqualMark | ≌ | 关联线段集合 | 等长标记（小竖线） |
| ParallelMark | ∥ | 关联线段对 | 平行标记（箭头） |
| RightAngleMark | ⊥ | 顶点、两边 | 直角符号（小方框） |

---

## 3. 三段式解析流水线

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Preprocess  │──▶│  Detection   │──▶│   Fitting    │──▶│   Labeling   │
│  预处理       │   │  检测/分割    │   │   几何拟合    │   │   标注关联    │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

三段式的核心思想：**预处理归一化 → 异构检测器并行检测 → 几何拟合精修 → 语义标注关联**。各段独立可测、可降级。

---

## 4. 预处理（Preprocess）

目标：将质量参差的试卷图像标准化，提升后续检测稳定性。每步均输出中间结果供调试。

### 4.1 灰度化与二值化
- 灰度化：`cv2.cvtColor(img, COLOR_BGR2GRAY)`。
- 自适应二值化：`cv2.adaptiveThreshold`（自适应高斯，块大小 31，C=10），处理光照不均；对印刷体可用 Otsu 全局阈值。
- 输出：`binary` 图，前景（几何线）为 255。

### 4.2 去噪
- 形态学开运算（`cv2.morphologyEx`，`MORPH_OPEN`，3×3 核）去除椒盐噪声。
- 形态学闭运算填补线段断裂。
- 中值滤波（3×3）保留边缘。

### 4.3 倾斜校正（Deskew）
倾斜会导致垂直/平行关系判定偏差，必须校正。

**算法**：
1. 对二值图做 Hough 直线检测（`cv2.HoughLinesP`），取所有线段方向角。
2. 对方向角做加权直方图（按线段长度加权），取峰值方向为主方向 θ₀。
3. 若 |θ₀ - 0°| 或 |θ₀ - 90°| 超过 1°，计算旋转角 `α = θ₀ - round(θ₀/90)*90`，仿射旋转 `cv2.warpAffine` 校正。
4. 若无显著直线，降级用最小外接矩形（`cv2.minAreaRect`）方向。

```python
def deskew(binary):
    lines = cv2.HoughLinesP(binary, 1, np.pi/180, 50, minLineLength=30, maxLineGap=10)
    angles = []
    weights = []
    for ln in lines:
        x1,y1,x2,y2 = ln[0]
        ang = np.degrees(np.arctan2(y2-y1, x2-x1))
        angles.append(ang); weights.append(np.hypot(x2-x1, y2-y1))
    # 加权主方向
    hist, edges = np.histogram(angles, bins=180, range=(-90,90), weights=weights)
    theta0 = edges[np.argmax(hist)]
    alpha = theta0 - round(theta0/90)*90
    if abs(alpha) > 1:
        H,W = binary.shape
        M = cv2.getRotationMatrix2D((W/2,H/2), alpha, 1.0)
        binary = cv2.warpAffine(binary, M, (W,H), flags=cv2.INTER_NEAREST, borderValue=0)
    return binary, alpha
```

### 4.4 骨架化（Skeletonization）
将线宽归一化为 1px，便于端点提取与拟合。
- 算法：`cv2.ximgproc.thinning`（Zhang-Suen 细化）或 `skimage.morphology.skeletonize`。
- 输出：`skeleton` 图。

### 4.5 图与文分离
试卷图中文字标签（A、B、C、O）会干扰线段检测，必须先定位并 mask 掉；同时保留标签位置供 Labeling 关联。
- OCR：PaddleOCR 检测文字框（`det` 阶段即可，不需识别内容，识别在 Labeling 阶段做）。
- 对文字框区域在 `binary`/`skeleton` 上置 0，得到 `binary_clean`。
- 保存 `text_boxes = [(x,y,w,h), ...]` 供 Labeling。

---

## 5. 检测（Detection）

对不同原语采用**异构检测器**，避免单一模型负担过重。检测器调度由 `DetectorOrchestrator` 统一管理。

### 5.1 检测器选型矩阵

| 原语 | 主检测器 | 辅助 | 是否微调 | 详见 |
| --- | --- | --- | --- | --- |
| Point | 角点检测 + 端点检测 + 交点计算 | YOLO（小目标，可选） | 否（主）/ 小数据（辅） | 02 §1 |
| Line/Segment | LSD + HoughP | 共线段合并 | 否 | 02 §2 |
| Ray | LSD + 起点方向 | 延伸判定 | 否 | 02 §2 |
| Circle | Mask + 边界 + 圆拟合 | Hough Circle（候选） | 否 | 02 §3 |
| Arc | Mask + 轮廓 + 圆弧拟合 | 起止角估计 | 否 | 02 §3 |
| Ellipse | Mask + 轮廓 + 椭圆拟合 | RANSAC | 否 | 02 §4 |
| Polygon | 顶点序列 + 闭合判定 | 连通域 | 否 | — |
| AngleMark | YOLO 分类 | 模板匹配 | 小数据微调 | — |
| EqualMark | YOLO 检测小竖线 | 计数 + 关联 | 小数据微调 | — |
| ParallelMark | YOLO 检测箭头 | 箭头方向聚类 | 小数据微调 | — |
| RightAngleMark | YOLO 检测小方框 | — | 小数据微调 | — |

### 5.2 是否使用各模型的决策

- **SAM（Segment Anything Model）**：**使用**。SAM 零样本分割强，用于：(a) 分割图元连通域，将线/圆/弧从背景分离出 Mask；(b) 以关键点为 prompt 输出点所在线/圆的 Mask。SAM 无需训练即可适配新图风格，契合"不依赖后训练"原则。优先用 ViT-H，资源紧张时用 ViT-B。
- **YOLO / DETR**：**使用，但仅用于标注符号检测**（角标、等长标记、平行标记、直角符号）。这些符号类别少、目标小、风格固定，用少量标注（数百张）即可训练一个小 YOLOv8-n，单卡数小时可完成。DETR 训练成本更高，作为可选升级（Phase 4+）。
- **是否微调主图元检测器**：**不微调**。主图元（线、圆、椭圆）依赖传统 CV + SAM + 几何拟合，保证精度可控、可解释。
- **传统 CV**：**重度使用**。Hough、LSD、轮廓分析、形态学是几何拟合的基础，对像素级精度可控。

### 5.3 检测器调度（DetectorOrchestrator）

```
            binary_clean / skeleton
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
  PointDetector  LineDetector  CurveDetector(SAM)
        │            │            │
        │            │       ┌────┼────┐
        │            │       ▼    ▼    ▼
        │            │    Circle Arc Ellipse
        │            │       │    │    │
        │            │       └────┼────┘
        │            │            ▼
        │            │       CurveFitting
        │            │            │
        └────────────┴────────────┘
                     │
                     ▼
              PrimitiveMerge(去重/一致性)
                     │
                     ▼
              MarkDetector(YOLO)
                     │
                     ▼
              PrimitiveSet
```

调度策略：
1. **并行**：Point/Line/Curve 三大检测器并行执行（独立）。
2. **依赖**：CurveDetector 内部 Circle/Arc/Ellipse 共享 SAM Mask，串行拟合。
3. **后合并**：所有原语汇入 `PrimitiveMerger`，处理重叠/重复（如同一交点被多个检测器检出）。
4. **标记检测**：MarkDetector 在干净原图上独立运行（不受几何 mask 影响）。

### 5.4 一致性校验
合并阶段执行跨原语一致性校验，矛盾项触发重检测或降级：
- 线段端点应与 PointDetector 输出吻合（距离 < 3px）。
- 圆上点应满足距离 ≈ 半径（容差内）。
- 共线段应被 LineDetector 合并。
- 矛盾项标记 `low_confidence`，进入 Verifier 复核。

---

## 6. 几何拟合（Fitting）

将检测到的像素集合拟合为精确数学对象，是保证"高准确率"的关键。详见 [02-检测算法](./02-Detection-Algorithms.md)，此处给出流程概览：

| 对象 | 拟合方法 | 精修 |
| --- | --- | --- |
| 点 | 角点/端点坐标 | `cv2.cornerSubPix` 亚像素 |
| 线 | 最小二乘 `ax+by+c=0` | 端点投影 |
| 圆 | Kasa 代数拟合 | Levenberg-Marquardt 几何拟合 |
| 椭圆 | Fitzgibbon 直接最小二乘 | LM 非线性精修 / RANSAC |

### 6.1 拟合残差与置信度
每个拟合输出残差 `residual`，转换为置信度：

$$
\text{confidence} = \max\left(0,\ 1 - \frac{\text{residual}}{\text{tol}}\right)
$$

`tol` 取对象特征尺寸的比例（如圆半径的 3%）。低置信原语标记 `uncertain`。

### 6.2 多假设保留
对歧义图元（如无法判断线段还是射线；无法判断圆还是椭圆）保留多个候选，交由后续 LLM + Verifier 在解题上下文中消歧。这是"高准确率优先 + 不丢召回"的折中。

---

## 7. 标注关联（Labeling）

将 OCR 识别到的字母标签与最近的关键点关联，赋予语义。

### 7.1 流程
1. 对 `text_boxes` 用 PaddleOCR 识别内容（如 "A"、"O"）。
2. 计算每个文字框中心与所有 Point 的距离。
3. 最近匹配（距离 < 阈值，如 25px）：将该 label 赋予该 Point。
4. 冲突处理：一个 label 匹配多个点时，取最近；一个点匹配多个 label 时，取距离最小且字符最可能为点标签（单字母）的。
5. 未匹配的标签：可能为圆/线标签，按距离最近圆心/线段中点关联。

### 7.2 标注符号关联
- **EqualMark**：小竖线按距离聚类到最近线段，同一线段上小竖线**计数相同**即判定等长。
- **ParallelMark**：箭头按方向聚类，同方向箭头关联的两线段判定平行。
- **RightAngleMark**：小方框关联到最近顶点，判定该顶点两边垂直。
- **AngleMark**：弧线/数字关联到顶点，若带数字则直接给出角度值。

这些关联关系作为**高置信边**直接写入 Geometry Graph（来源 `mark`），但仍经 Verifier 数值复核（标注符号可能误检）。

---

## 8. 错误处理与降级

| 失败场景 | 降级策略 |
| --- | --- |
| SAM 不可用/超时 | 降级为自适应阈值分割 |
| YOLO 标注符号漏检 | 降级为模板匹配 |
| 圆拟合残差过大 | 标记 `uncertain`，保留候选圆+弧 |
| 椭圆拟合失败 | 降级为"近似椭圆"低置信 |
| 点检测召回不足 | 用线-线/线-圆交点补全 |
| 倾斜校正失败 | 保留原图，扩大角度容差 |
| 全图解析失败 | 返回空 PrimitiveSet + 错误码，触发人工复核 |

降级遵循"**绝不编造**"原则：宁可输出空/低置信，也不输出错误关系。

---

## 9. 输出格式

```json
{
  "primitives": {
    "points": [
      {"id":"P_A","label":"A","coords":[180.0,84.5],"confidence":0.97,"source":"corner","subpixel":true}
    ],
    "segments": [
      {"id":"L_AB","label":"AB","endpoints":[[180.0,84.5],[260.0,140.0]],
       "equation":{"a":0.62,"b":-0.78,"c":-8.4},"length":113.2,"confidence":0.94}
    ],
    "circles": [
      {"id":"C_O","label":"O","center":[180.0,160.0],"radius":75.5,
       "fit_residual":1.2,"coverage":1.0,"confidence":0.96}
    ],
    "ellipses": [],
    "arcs": [],
    "polygons": [],
    "marks": [
      {"id":"M_1","type":"right_angle","vertex":"P_A","confidence":0.92}
    ]
  },
  "metadata": {
    "image_size":[400,320],
    "deskew_angle":0.3,
    "scale_px_per_cm":12.0,
    "warnings":["ellipse_fit_low_confidence"]
  }
}
```

---

## 10. 设计路线小结

Geometry Parser 的设计路线可概括为：**"预处理归一化 → 异构检测器并行 → 几何拟合精修 → 一致性校验 → 语义标注关联 → 多假设降级"**。其核心是把"看图"误差用传统 CV + SAM + 数值拟合控制在亚像素级，并通过多假设保留避免漏检，最终输出经一致性校验的 PrimitiveSet，为 Geometry Graph 提供可靠基石。
