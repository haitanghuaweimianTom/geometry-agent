# 04 · Relation Extraction Agents

> 本文档阐述关系抽取层的 Multi-Agent 架构设计、各 Agent 的判定算法、并行调度策略与冲突解决机制。Agent 输出候选关系，交由 [Verifier](./05-Verifier.md) 验证。

---

## 1. 为什么采用 Multi-Agent

几何关系类型多、判定逻辑差异大。若用单一 Agent/模型抽取全部关系，会导致：

| 问题 | 单一 Agent | Multi-Agent |
| --- | --- | --- |
| 上下文 | 过长，互相干扰 | 每个 Agent 上下文聚焦 |
| 错误定位 | 难 | 每条关系来源可追溯 |
| 扩展 | 改一处影响全局 | 新增类型只加 Agent |
| 并行 | 串行慢 | 无依赖关系可并行 |
| 复用 | 难 | Agent 可独立测试/复用 |

Multi-Agent 带来**关注点分离、并行执行、可解释、可扩展**四大收益，是本系统结构化层的核心架构选择。

---

## 2. Agent 划分

| Agent | 负责对象 | 主要关系 | 主要方法 |
| --- | --- | --- | --- |
| Point Agent | Point | 共线、在线、在圆/椭圆上、交点 | 距离 / 解析判定 |
| Line Agent | Line/Segment/Ray | 平行、垂直、相交、共线段合并 | 方向向量夹角 |
| Circle Agent | Circle/Arc | 切线、割线、弦、圆周角、圆心角、两圆关系、切点 | 距离=半径、角度 |
| Ellipse Agent | Ellipse | 焦点关系、切线、顶点 | 解析 + 数值 |
| Polygon Agent | Polygon | 内接/外切、相似/全等、面积/周长 | 顶点关系传递 |
| Mark Agent | AngleMark/EqualMark/ParallelMark | 角度、等长、平行（来自标注符号） | 检测结果直接转关系 |
| Cross Agent | 跨类 | 线圆相切、点在圆弧上、椭圆切线 | 跨对象联合判定 |

---

## 3. 统一 Agent 接口

所有 Agent 实现统一接口，便于调度与扩展：

```python
class RelationAgent(Protocol):
    name: str
    def extract(self, graph: GeometryGraph) -> list[RelationCandidate]: ...

class RelationCandidate(BaseModel):
    src: str
    dst: str
    rel: RelType
    evidence: str          # 判定证据(可读)
    confidence: float
    attrs: dict = {}       # 关系特有属性
```

---

## 4. Point Agent

### 4.1 职责
- 共线（Collinear）
- 在线上（On, Point→Line/Segment/Ray）
- 在圆上（On, Point→Circle/Arc）
- 在椭圆上（On, Point→Ellipse）
- 交点补全（Intersect）

### 4.2 共线判定
对任意三点组判定共线。朴素 $O(n^3)$ 不可行，采用**主方向聚类降维**：

1. 对所有点对，计算方向角，做加权直方图（按距离加权）。
2. 取直方图峰值方向作为候选共线方向 θ。
3. 对每个峰值方向，将所有点投影到该方向，按投影坐标聚类（DBSCAN）。
4. 每个聚类内（≥3 点）判定共线：计算点到拟合直线的距离，< tol 即共线，生成 Collinear 边。

```python
def collinear(points, tol):
    # 1. 主方向直方图
    angles = [angle(p,q) for p,q in pairs(points)]
    peaks = find_peaks(histogram(angles))
    candidates = []
    for theta in peaks:
        # 2. 投影聚类
        proj = [project(p, theta) for p in points]
        clusters = dbscan(proj, eps=tol)
        for cl in clusters:
            if len(cl) >= 3:
                line = fit_line([points[i] for i in cl])
                if max(dist(p, line) for p in cl) < tol:
                    candidates.append(CollinearCandidate(cl))
    return candidates
```

### 4.3 在线判定
- 点 $P$ 到直线 $ax+by+c=0$ 距离 $d=|ax_p+by_p+c|/\sqrt{a^2+b^2}$。
- `d < tol`（tol = max(2px, 0.5%·线长)）→ On。
- 若为 Segment，还需参数 $t\in[0,1]$（投影在线段范围内）。

### 4.4 在圆上判定
- $d=|P-O_c|$，判定 $|d-r|<\text{tol}$，tol = max(2px, 1.5%·r)。

### 4.5 交点补全
对 Line×Line、Line×Circle、Circle×Circle 解析求交，若交点不在已注册 Point 中，新增 Point（`source=inferred`）并生成 Intersect 边。

---

## 5. Line Agent

### 5.1 职责
- 平行（Parallel）
- 垂直（Perpendicular）
- 相交（Intersect）
- 共线段合并（合并后更新 Graph）

### 5.2 平行/垂直判定
方向向量 $\vec u, \vec v$：
- 夹角 $\theta=\arccos\left(\frac{|\vec u\cdot\vec v|}{|\vec u||\vec v|}\right)$。
- $\theta < 3°$ → Parallel。
- $\theta \in [87°,93°]$ → Perpendicular。

### 5.3 相交判定
解析求线线交点；若存在且在线段范围内 → Intersect 边 + 交点回填。

---

## 6. Circle Agent（重点）

圆相关关系是几何题高频考点，Circle Agent 需覆盖：

| 关系 | 判定 |
| --- | --- |
| 切线（直线切圆） | 圆心到直线距离 $d$ 满足 $|d-r|<\text{tol}$；切点为垂足 |
| 切线（两圆外切/内切） | 圆心距 $d$ 满足 $|d-(r_1\pm r_2)|<\text{tol}$ |
| 割线 | 直线与圆有两个交点 |
| 弦 | 圆上两点的连线段 |
| 圆周角 | 共弧两点对圆上第三点的角，等于同弧圆心角的一半 |
| 圆心角 | 圆心与圆上两点所成角 |
| 两圆关系 | 相离/外切/相交/内切/内含/同心，由圆心距与半径关系判定 |
| 切点 | 切线与圆的交点（On + Tangent 联合） |
| 圆幂 | 点 P 对圆 O 的幂 $\text{Pow}=OP^2-r^2$ |

### 6.1 两圆关系判定

设两圆 $(O_1,r_1),(O_2,r_2)$，圆心距 $d=|O_1O_2|$：

| 条件 | 关系 |
| --- | --- |
| $d > r_1+r_2+\text{tol}$ | 相离（Disjoint） |
| $|d-(r_1+r_2)|<\text{tol}$ | 外切（ExternallyTangent） |
| $|r_1-r_2|-\text{tol} < d < r_1+r_2-\text{tol}$ | 相交（Intersect） |
| $|d-|r_1-r_2||<\text{tol}$ | 内切（InternallyTangent） |
| $d < |r_1-r_2|-\text{tol}$ | 内含（Contained） |
| $d < \text{tol}$ | 同心（Concentric） |

### 6.2 圆周角与圆心角
对圆上三点 $A,B,C$（$A,C$ 共弧，$B$ 为顶点）：
- 圆心角 $\angle AOC = 2\angle ABC$（同弧）。
- 生成 `InscribedAngle` 属性，供 Solver 应用圆周角定理。

### 6.3 切点
切线 $L$ 切圆 $O$ 于点 $T$：$T$ 为 $O$ 到 $L$ 的垂足，且 $T$ 在圆上。生成 `Tangent` 边 + `TangentPoint` 边（$T \to O$）。

---

## 7. Ellipse Agent

### 7.1 职责
- 焦点关系（FocusRelation）：椭圆上点 $P$ 满足 $|PF_1|+|PF_2|=2a$。
- 切线（Tangent to ellipse）：椭圆上点 $P$ 处切线方向由隐函数梯度给出。
- 顶点/长轴/短轴：由拟合参数直接给出。

### 7.2 焦点关系验证
对候选点 $P$：$\text{sum}=|PF_1|+|PF_2|$，判定 $|\text{sum}-2a|/a < 1.5\%$ → On(P, Ellipse)。

### 7.3 椭圆切线
椭圆 $\frac{(x-c_x)\cos\theta+(y-c_y)\sin\theta}{a})^2 + (\frac{-(x-c_x)\sin\theta+(y-c_y)\cos\theta}{b})^2 = 1$。
点 $P$ 处梯度方向即为法向，切线与法向垂直。判定候选直线是否与法向垂直且过 $P$。

---

## 8. Polygon Agent

### 8.1 职责
- 内接（Inscribed）：多边形顶点全在某圆上。
- 外切（Circumscribed）：多边形各边均与某圆相切。
- 相似（Similar）：两三角形对应角相等。
- 全等（Congruent）：两三角形对应边相等。
- 面积/周长：由顶点计算。

### 8.2 相似判定
两三角形 $\triangle ABC, \triangle DEF$：计算三对应角，若分别相等（容差内）→ Similar，记录对应关系。

---

## 9. Mark Agent

Mark Agent 将检测到的标注符号直接转换为高置信关系：

| 标注 | 转换 |
| --- | --- |
| EqualMark（小竖线） | 同一线段上小竖线计数相同 → Equal(线段组) |
| ParallelMark（箭头） | 同方向箭头关联线段 → Parallel(线段对) |
| RightAngleMark（小方框） | 关联顶点 → Perpendicular(顶点两边) |
| AngleMark（弧线+数字） | 关联顶点 → Angle=数字 |

Mark Agent 输出的关系标记 `source=mark`，confidence 高（如 0.9），但仍经 Verifier 数值复核（标注符号可能误检）。

---

## 10. Cross Agent

负责跨类联合判定，单类 Agent 无法独立完成的关系：

| 关系 | 涉及类 | 判定 |
| --- | --- | --- |
| 线圆相切 | Line × Circle | d ≈ r（与 Circle Agent 重叠，但 Cross 统一调度） |
| 点在圆弧上 | Point × Arc | On(圆) + 角度在弧范围内 |
| 椭圆切线 | Line × Ellipse | 过椭圆上点 + 与法向垂直 |
| 多边形内接 | Polygon × Circle | 顶点全在圆上 |

Cross Agent 作为"兜底"，确保跨类关系不遗漏。

---

## 11. 并行调度

```
                GeometryGraph(候选, 仅节点)
                         │
   ┌──────┬──────┬───────┼───────┬──────┬──────┐
   ▼      ▼      ▼       ▼       ▼      ▼      ▼
 Point  Line  Circle  Ellipse Polygon Mark  Cross
 Agent  Agent Agent   Agent   Agent   Agent Agent
   │      │      │       │       │      │      │
   └──────┴──────┴───────┴───────┴──────┴──────┘
                         │
                         ▼
              RelationCandidate 汇总
                         │
                         ▼
                   冲突解决 / 去重
                         │
                         ▼
                   Verifier 验证
```

- **并行**：7 个 Agent 无状态、无依赖，可并行执行（`asyncio` 或线程池）。
- **超时**：每个 Agent 设超时（如 5s），超时返回空候选并告警。
- **资源**：CPU 密集（解析计算）用进程池；若涉及 LLM 调用用异步。

---

## 12. 冲突解决

多个 Agent 可能对同一关系给出不同结论（如 Mark Agent 给 Parallel，Line Agent 数值判定不平行）：

| 冲突类型 | 解决策略 |
| --- | --- |
| 同关系不同 confidence | 取 confidence 最高者 |
| Mark vs 数值矛盾 | 降级为 `uncertain`，交 Verifier 复核 |
| 重复候选 | 去重（同 src/dst/rel） |
| 多假设（圆/椭圆） | 保留双候选，标记歧义 |

冲突解决输出统一的 `RelationCandidate` 列表，交 Verifier 做最终判定。

---

## 13. Agent 输出统一格式

```json
{
  "agent": "CircleAgent",
  "candidates": [
    {"src":"L_AB","dst":"C_O","rel":"Tangent",
     "evidence":"d=75.4, r=75.5, |d-r|=0.1<tol","confidence":0.95,
     "attrs":{"tangent_point":"P_A"}},
    {"src":"P_A","dst":"C_O","rel":"On",
     "evidence":"|dist-r|=0.2<tol","confidence":0.98}
  ]
}
```

---

## 14. 设计路线小结

Relation Extraction 的设计路线为：**"按对象类型划分 Agent → 统一接口 → 各 Agent 专精判定算法 → 并行调度 → 冲突解决 → 候选交 Verifier"**。Multi-Agent 架构使关系抽取既专注又可扩展，每个 Agent 的判定逻辑可独立优化与测试，为 Geometry Graph 提供高质量候选边。
