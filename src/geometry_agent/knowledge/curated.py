"""Local curated knowledge base: real middle/high-school geometry knowledge points
and solving methods, organized by the four subjects (plane_geometry,
triangle_solving, analytic_geometry, solid_geometry).

Method priorities:
  IN_CLASS  (1) - 课内常规方法, 推荐优先尝试
  ADVANCED  (2) - 高等几何方法 (射影/仿射/复数法/极坐标等)
  MACHINE   (3) - 机器证明 / 符号机器求解
"""
from __future__ import annotations

from ..types import GradeLevel, KnowledgeEntry, MethodEntry, MethodPriority, SubjectType

# =====================================================================================
# Plane geometry
# =====================================================================================

PLANE_ENTRIES: list[KnowledgeEntry] = [
    KnowledgeEntry(
        id="pg-tri-congruent",
        subject=SubjectType.PLANE_GEOMETRY,
        title="全等三角形判定 (SSS/SAS/ASA/AAS/HL)",
        content=(
            "三边对应相等 (SSS)、两边夹角对应相等 (SAS)、两角夹边对应相等 (ASA)、"
            "两角及一对边对应相等 (AAS)、斜边直角边对应相等 (HL, 仅直角三角形) "
            "则两三角形全等。全等三角形对应边、对应角相等。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["全等", "三角形", "SSS", "SAS", "ASA", "AAS", "HL", "全等判定"],
        applies_to=["证明线段相等", "证明角相等", "全等三角形"],
    ),
    KnowledgeEntry(
        id="pg-tri-similar",
        subject=SubjectType.PLANE_GEOMETRY,
        title="相似三角形判定 (AA/SAS/SSS)",
        content=(
            "两角对应相等 (AA)、两边对应成比例且夹角相等 (SAS)、三边对应成比例 (SSS) "
            "则两三角形相似。相似三角形对应边成比例, 对应角相等, 面积比等于相似比平方。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["相似", "三角形", "AA", "SAS", "SSS", "相似比", "成比例"],
        applies_to=["求线段比", "证明比例", "相似三角形"],
    ),
    KnowledgeEntry(
        id="pg-inscribed-angle",
        subject=SubjectType.PLANE_GEOMETRY,
        title="圆周角定理",
        content=(
            "同弧或等弧所对的圆周角相等, 且等于它所对圆心角的一半。直径所对的圆周角为直角。"
            "同弧圆周角相等是证明角相等的重要工具。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["圆周角", "圆心角", "弧", "圆", "直径", "直角"],
        applies_to=["圆周角", "圆上角相等", "直径"],
    ),
    KnowledgeEntry(
        id="pg-tangent",
        subject=SubjectType.PLANE_GEOMETRY,
        title="切线判定与性质定理",
        content=(
            "切线性质: 切线垂直于过切点的半径 (l⊥OA, A 为切点)。"
            "切线判定: 经过半径外端且垂直于该半径的直线是圆的切线。"
            "切线长定理: 从圆外一点引圆的两条切线, 切线长相等, 且这点与圆心连线平分两切线夹角。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["切线", "圆", "切线判定", "切线性质", "切线长", "半径垂直", "垂直"],
        applies_to=["切线", "求切线", "证明垂直", "切点", "切线长"],
    ),
    KnowledgeEntry(
        id="pg-chord-power",
        subject=SubjectType.PLANE_GEOMETRY,
        title="弦长定理与圆幂定理 (相交弦/割线/切割线)",
        content=(
            "相交弦定理: 圆内两弦 AB、CD 交于 P, PA·PB = PC·PD。"
            "割线定理: P 引两割线 PAB、PCD, PA·PB = PC·PD。"
            "切割线定理: P 引切线 PT 与割线 PAB, PT² = PA·PB。"
            "弦长公式: 弦长 = 2R·sin(弦所对圆心角/2)。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["弦", "弦长", "相交弦", "割线", "切割线", "圆幂", "圆"],
        applies_to=["弦长", "相交弦", "割线", "切线长", "圆幂"],
    ),
    KnowledgeEntry(
        id="pg-pythagorean",
        subject=SubjectType.PLANE_GEOMETRY,
        title="勾股定理",
        content=(
            "直角三角形两直角边 a、b 的平方和等于斜边 c 的平方: a² + b² = c²。"
            "逆定理成立: 若 a² + b² = c² 则该三角形为直角三角形。"
            "常用于求线段长度、判定垂直。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["勾股", "直角", "直角三角形", "弦", "勾股定理"],
        applies_to=["求长度", "直角三角形", "勾股", "证明直角"],
    ),
    KnowledgeEntry(
        id="pg-midsegment",
        subject=SubjectType.PLANE_GEOMETRY,
        title="三角形中位线定理",
        content=(
            "三角形中位线平行于第三边且等于第三边的一半。"
            "梯形中位线平行两底且等于两底和的一半。"
            "常用于建立平行与线段倍半关系。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["中位线", "平行", "三角形", "梯形"],
        applies_to=["中位线", "平行", "线段倍半"],
    ),
    KnowledgeEntry(
        id="pg-angle-bisector",
        subject=SubjectType.PLANE_GEOMETRY,
        title="角平分线性质定理",
        content=(
            "角平分线上点到角两边距离相等。"
            "三角形内角平分线分对边所得两段与邻边成比例: AD 平分 ∠BAC, 则 BD/DC = AB/AC。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["角平分线", "角平分", "距离相等", "成比例"],
        applies_to=["角平分线", "求比例", "角平分"],
    ),
    KnowledgeEntry(
        id="pg-perp-diameter",
        subject=SubjectType.PLANE_GEOMETRY,
        title="垂径定理",
        content=(
            "垂直于弦的直径平分这条弦, 且平分弦所对的两条弧。"
            "推论: 平分弦(非直径)的直径垂直于该弦; 弦的垂直平分线过圆心。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["垂径", "弦", "垂直", "直径", "圆", "平分弦"],
        applies_to=["垂径", "弦中点", "垂直", "弧"],
    ),
    KnowledgeEntry(
        id="pg-cyclic-quad",
        subject=SubjectType.PLANE_GEOMETRY,
        title="圆内接四边形性质",
        content=(
            "圆内接四边形对角互补, 任一外角等于其内对角。"
            "四点共圆判定: 对角互补, 或一点对外接两点张角相等。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["圆内接", "四边形", "共圆", "对角互补", "圆"],
        applies_to=["四点共圆", "圆内接四边形", "对角互补"],
    ),
    KnowledgeEntry(
        id="pg-menelaus",
        subject=SubjectType.PLANE_GEOMETRY,
        title="梅涅劳斯定理 (Menelaus)",
        content=(
            "直线截 △ABC 三边 BC、CA、AB (或其延长线) 于 D、E、F, "
            "则 (BD/DC)·(CE/EA)·(AF/FB) = 1 (有向线段)。"
            "用于证明三点共线或求共线线段比。属高等几何方法。"
        ),
        method_priority=MethodPriority.ADVANCED,
        tags=["梅涅劳斯", "Menelaus", "共线", "线段比", "高等几何"],
        applies_to=["三点共线", "线段比", "梅涅劳斯"],
    ),
    KnowledgeEntry(
        id="pg-ceva",
        subject=SubjectType.PLANE_GEOMETRY,
        title="塞瓦定理 (Ceva)",
        content=(
            "△ABC 内一点 O, AO、BO、CO 交对边于 D、E、F, "
            "则 (BD/DC)·(CE/EA)·(AF/FB) = 1。逆定理亦成立, 用于证明三线共点。"
        ),
        method_priority=MethodPriority.ADVANCED,
        tags=["塞瓦", "Ceva", "共点", "线段比", "高等几何"],
        applies_to=["三线共点", "线段比", "塞瓦"],
    ),
    KnowledgeEntry(
        id="pg-complex-method",
        subject=SubjectType.PLANE_GEOMETRY,
        title="复数法 (高等几何)",
        content=(
            "将平面几何图形置于复平面, 点用复数 z 表示, 利用复数运算刻画距离、角度、旋转。"
            "适合处理共点、共线、共圆、等角等约束。属高等几何方法。"
        ),
        method_priority=MethodPriority.ADVANCED,
        tags=["复数法", "复数", "高等几何", "旋转", "共圆"],
        applies_to=["复数法", "等角", "共圆", "旋转"],
    ),
    KnowledgeEntry(
        id="pg-analytic-method",
        subject=SubjectType.PLANE_GEOMETRY,
        title="解析法 / 坐标法 (高等几何)",
        content=(
            "建立坐标系, 把几何关系转化为代数方程求解。"
            "适合计算长度、角度、位置关系; 对纯几何问题可能使证明复杂化。"
        ),
        method_priority=MethodPriority.ADVANCED,
        tags=["解析法", "坐标法", "高等几何", "坐标系"],
        applies_to=["解析法", "坐标法", "计算长度", "计算角度"],
    ),
]

PLANE_METHODS: list[MethodEntry] = [
    MethodEntry(
        id="pm-congruent",
        subject=SubjectType.PLANE_GEOMETRY,
        name="全等三角形法",
        priority=MethodPriority.IN_CLASS,
        description="寻找或构造全等三角形, 用对应边/角相等完成证明。",
        steps=["标出待证相等的边/角", "寻找全等三角形 (SSS/SAS/ASA/AAS/HL)", "由全等得对应量相等"],
        applicable_when=["证明线段相等", "证明角相等", "全等三角形"],
        example="已知 AB=AC, AD=AE, ∠BAE=∠CAD, 求证 △ABD≅△ACE。",
    ),
    MethodEntry(
        id="pm-similar",
        subject=SubjectType.PLANE_GEOMETRY,
        name="相似三角形法",
        priority=MethodPriority.IN_CLASS,
        description="利用相似三角形建立线段比例关系求解。",
        steps=["找平行线或公共角构造相似", "写出相似比", "列比例式求未知量"],
        applicable_when=["求线段比", "证明比例", "相似三角形"],
        example="DE∥BC, D 在 AB 上, 求 AD/DB。",
    ),
    MethodEntry(
        id="pm-circle",
        subject=SubjectType.PLANE_GEOMETRY,
        name="圆的性质法",
        priority=MethodPriority.IN_CLASS,
        description="综合运用圆周角、切线、弦、圆幂等圆的性质。",
        steps=["识别切线/圆周角/弦位置关系", "应用相应定理(切线垂直半径/圆周角定理/圆幂)", "导出结论"],
        applicable_when=["切线", "圆周角", "弦长", "相交弦", "圆"],
        example="AB 切圆 O 于 A, 求证 OA⊥AB。",
    ),
    MethodEntry(
        id="pm-pythagorean",
        subject=SubjectType.PLANE_GEOMETRY,
        name="勾股定理法",
        priority=MethodPriority.IN_CLASS,
        description="利用直角三角形三边关系求长度或判定垂直。",
        steps=["确认或构造直角", "用 a²+b²=c² 求边或判定", "结合相似/全等"],
        applicable_when=["直角三角形", "求长度", "勾股", "证明直角"],
        example="直角三角形两直角边 3、4, 求斜边。",
    ),
    MethodEntry(
        id="pm-menelaus-ceva",
        subject=SubjectType.PLANE_GEOMETRY,
        name="梅涅劳斯/塞瓦法",
        priority=MethodPriority.ADVANCED,
        description="用 Menelaus/Ceva 定理处理共线、共点与线段比问题。",
        steps=["识别共线/共点结构", "套用 Menelaus 或 Ceva 等式", "解出未知比例"],
        applicable_when=["三点共线", "三线共点", "线段比", "梅涅劳斯", "塞瓦"],
        example="D、E、F 分别在 △ABC 三边上, 求证 D、E、F 共线。",
    ),
    MethodEntry(
        id="pm-complex",
        subject=SubjectType.PLANE_GEOMETRY,
        name="复数法",
        priority=MethodPriority.ADVANCED,
        description="用复数表示点, 通过复数运算处理角度与距离。",
        steps=["选原点建复平面", "写出关键点复数", "用旋转/模长条件列式"],
        applicable_when=["复数法", "等角", "共圆", "旋转"],
        example="用复数法证明三角形垂心性质。",
    ),
    MethodEntry(
        id="pm-analytic",
        subject=SubjectType.PLANE_GEOMETRY,
        name="解析法 / 坐标法",
        priority=MethodPriority.ADVANCED,
        description="建系后用代数方程求解几何量。",
        steps=["选合适坐标系建系", "写出关键点坐标与方程", "代数求解"],
        applicable_when=["解析法", "坐标法", "计算长度", "计算角度"],
        example="用坐标法证明中线定理。",
    ),
    MethodEntry(
        id="pm-machine",
        subject=SubjectType.PLANE_GEOMETRY,
        name="机器证明法",
        priority=MethodPriority.MACHINE,
        description="使用符号机器证明 (如吴方法/Gröbner 基) 验证几何命题。",
        steps=["命题代数化", "调用机器证明引擎", "输出 yes/no 与证明"],
        applicable_when=["机器证明", "复杂命题验证"],
        example="用吴方法验证 Simson 定理。",
    ),
]

# =====================================================================================
# Triangle solving
# =====================================================================================

TRIANGLE_ENTRIES: list[KnowledgeEntry] = [
    KnowledgeEntry(
        id="ts-sine",
        subject=SubjectType.TRIANGLE_SOLVING,
        title="正弦定理",
        content=(
            "在 △ABC 中, a/sinA = b/sinB = c/sinC = 2R (R 为外接圆半径)。"
            "用于已知两角及任一边, 或已知两边及一边对角时求解三角形。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["正弦", "正弦定理", "外接圆", "解三角形"],
        applies_to=["正弦定理", "已知两角一边", "已知两边对角", "解三角形"],
    ),
    KnowledgeEntry(
        id="ts-cosine",
        subject=SubjectType.TRIANGLE_SOLVING,
        title="余弦定理",
        content=(
            "a² = b² + c² − 2bc·cosA (及其轮换)。"
            "用于已知三边求角, 或已知两边及夹角求第三边。当 ∠A=90° 时退化为勾股定理。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["余弦", "余弦定理", "解三角形", "勾股"],
        applies_to=["余弦定理", "已知三边", "已知两边夹角", "解三角形", "求角"],
    ),
    KnowledgeEntry(
        id="ts-area",
        subject=SubjectType.TRIANGLE_SOLVING,
        title="三角形面积公式",
        content=(
            "S = (1/2)ab·sinC = (1/2)bc·sinA = (1/2)ac·sinB。"
            "亦可用底乘高之半、内切圆半径 r: S = (1/2)(a+b+c)r。"
            "用于结合正余弦定理求面积或反求角。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["面积", "三角形", "面积公式", "sin", "内切圆"],
        applies_to=["求面积", "面积公式", "三角形面积"],
    ),
    KnowledgeEntry(
        id="ts-projection",
        subject=SubjectType.TRIANGLE_SOLVING,
        title="射影定理",
        content=(
            "在 △ABC 中, a = b·cosC + c·cosB (及其轮换)。"
            "任一边等于其余两边在该边上射影之和。常与余弦定理配合使用。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["射影", "射影定理", "余弦", "解三角形"],
        applies_to=["射影定理", "射影", "解三角形"],
    ),
    KnowledgeEntry(
        id="ts-heron",
        subject=SubjectType.TRIANGLE_SOLVING,
        title="海伦公式",
        content=(
            "设 p=(a+b+c)/2, 则 S=√(p(p−a)(p−b)(p−c))。"
            "已知三边长度即可直接求面积, 无需角度。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["海伦", "海伦公式", "面积", "三边"],
        applies_to=["海伦公式", "已知三边求面积", "面积"],
    ),
    KnowledgeEntry(
        id="ts-angle-sum",
        subject=SubjectType.TRIANGLE_SOLVING,
        title="三角形内角和定理",
        content=(
            "三角形三内角之和为 180°。用于由两角求第三角, 或结合正弦定理求解。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["内角和", "三角形", "180", "角度"],
        applies_to=["内角和", "求角", "角度"],
    ),
    KnowledgeEntry(
        id="ts-large-side",
        subject=SubjectType.TRIANGLE_SOLVING,
        title="大边对大角",
        content=(
            "三角形中大边对大角, 等边对等角, 反之亦然。"
            "用于比较角度或边长大小, 判断解的取舍 (如已知两边对角可能有多解)。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["大边对大角", "边角", "三角形", "比较"],
        applies_to=["大边对大角", "比较边角", "解的个数"],
    ),
    KnowledgeEntry(
        id="ts-cosine-angle",
        subject=SubjectType.TRIANGLE_SOLVING,
        title="余弦定理求角公式",
        content=(
            "cosA = (b² + c² − a²) / (2bc) (及其轮换)。"
            "用于已知三边时求任一内角, 便于判断锐角/直角/钝角。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["余弦", "求角", "余弦定理", "cos", "解三角形"],
        applies_to=["求角", "余弦定理", "已知三边求角"],
    ),
]

TRIANGLE_METHODS: list[MethodEntry] = [
    MethodEntry(
        id="tm-sine",
        subject=SubjectType.TRIANGLE_SOLVING,
        name="正弦定理法",
        priority=MethodPriority.IN_CLASS,
        description="用 a/sinA=2R 建立边角关系求解。",
        steps=["列出正弦定理等式", "代入已知边角", "解出未知边或角, 注意多解"],
        applicable_when=["正弦定理", "已知两角一边", "已知两边对角", "解三角形"],
        example="已知 a=10, ∠A=30°, ∠B=45°, 求 b。",
    ),
    MethodEntry(
        id="tm-cosine",
        subject=SubjectType.TRIANGLE_SOLVING,
        name="余弦定理法",
        priority=MethodPriority.IN_CLASS,
        description="用 a²=b²+c²−2bc·cosA 求边或角。",
        steps=["列余弦定理等式", "代入已知量", "解出未知边或角"],
        applicable_when=["余弦定理", "已知三边", "已知两边夹角", "解三角形"],
        example="已知 a=7, b=5, c=8, 求 ∠A。",
    ),
    MethodEntry(
        id="tm-area",
        subject=SubjectType.TRIANGLE_SOLVING,
        name="面积法",
        priority=MethodPriority.IN_CLASS,
        description="利用 S=(1/2)ab·sinC 联系面积与边角。",
        steps=["写出面积公式", "结合正余弦定理", "解出未知量"],
        applicable_when=["求面积", "面积公式", "三角形面积"],
        example="已知 a=6, b=8, ∠C=60°, 求面积。",
    ),
    MethodEntry(
        id="tm-heron",
        subject=SubjectType.TRIANGLE_SOLVING,
        name="海伦公式法",
        priority=MethodPriority.IN_CLASS,
        description="已知三边直接套海伦公式求面积。",
        steps=["计算半周长 p", "套 S=√(p(p−a)(p−b)(p−c))", "化简"],
        applicable_when=["海伦公式", "已知三边求面积", "面积"],
        example="已知 a=13, b=14, c=15, 求面积。",
    ),
    MethodEntry(
        id="tm-machine",
        subject=SubjectType.TRIANGLE_SOLVING,
        name="机器求解法",
        priority=MethodPriority.MACHINE,
        description="用符号求解器对方程组求解并判定多解。",
        steps=["列出正余弦方程", "调用符号求解", "判定有效解"],
        applicable_when=["机器证明", "复杂三角形求解"],
        example="用 sympy 求解多解三角形。",
    ),
]

# =====================================================================================
# Analytic geometry
# =====================================================================================

ANALYTIC_ENTRIES: list[KnowledgeEntry] = [
    KnowledgeEntry(
        id="ag-line",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="直线方程 (点斜式/斜截式/两点式/一般式)",
        content=(
            "点斜式: y−y₀=k(x−x₀); 斜截式: y=kx+b; 两点式: (y−y₁)/(y₂−y₁)=(x−x₁)/(x₂−x₁); "
            "一般式: Ax+By+C=0。斜率 k=tanα (α 为倾角)。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["直线", "方程", "斜率", "点斜式", "斜截式", "两点式", "一般式"],
        applies_to=["直线方程", "斜率", "直线"],
    ),
    KnowledgeEntry(
        id="ag-circle",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="圆的方程 (标准式与一般式)",
        content=(
            "标准方程: (x−a)²+(y−b)²=r², 圆心 (a,b), 半径 r。"
            "一般方程: x²+y²+Dx+Ey+F=0 (D²+E²−4F>0), 圆心 (−D/2,−E/2), "
            "半径 r=½√(D²+E²−4F)。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["圆", "圆方程", "标准方程", "一般方程", "圆心", "半径"],
        applies_to=["圆方程", "圆心", "半径", "圆"],
    ),
    KnowledgeEntry(
        id="ag-ellipse",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="椭圆定义与标准方程",
        content=(
            "定义: 平面内到两定点 (焦点) 距离之和等于定长 2a (a>c) 的点的轨迹。"
            "标准方程 (焦点在 x 轴): x²/a² + y²/b² = 1 (a>b>0), c²=a²−b², 离心率 e=c/a。"
            "焦点在 y 轴时交换 a、b 位置。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["椭圆", "标准方程", "焦点", "离心率", "圆锥曲线"],
        applies_to=["椭圆", "椭圆方程", "焦点", "离心率"],
    ),
    KnowledgeEntry(
        id="ag-hyperbola",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="双曲线定义与标准方程",
        content=(
            "定义: 到两定点 (焦点) 距离之差的绝对值等于定长 2a (a<c) 的点的轨迹。"
            "标准方程: x²/a² − y²/b² = 1, c²=a²+b², 离心率 e=c/a>1, "
            "渐近线 y=±(b/a)x。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["双曲线", "标准方程", "焦点", "渐近线", "离心率", "圆锥曲线"],
        applies_to=["双曲线", "双曲线方程", "渐近线", "焦点"],
    ),
    KnowledgeEntry(
        id="ag-parabola",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="抛物线定义与标准方程",
        content=(
            "定义: 到定点 (焦点) 与定直线 (准线) 距离相等的点的轨迹。"
            "标准方程 y²=2px (p>0), 焦点 (p/2,0), 准线 x=−p/2。"
            "开口方向随方程形式变化。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["抛物线", "标准方程", "焦点", "准线", "圆锥曲线"],
        applies_to=["抛物线", "抛物线方程", "焦点", "准线"],
    ),
    KnowledgeEntry(
        id="ag-focal-chord",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="焦点弦性质",
        content=(
            "过圆锥曲线焦点的弦称为焦点弦。抛物线 y²=2px 的焦点弦长 |AB|=x₁+x₂+p "
            "= 2p/(sin²θ) (θ 为弦倾角)。椭圆/双曲线有相应焦点弦公式。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["焦点弦", "抛物线", "椭圆", "双曲线", "弦长", "焦点"],
        applies_to=["焦点弦", "弦长", "焦点"],
    ),
    KnowledgeEntry(
        id="ag-vieta",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="韦达定理应用 (弦长/中点/两根关系)",
        content=(
            "直线与圆锥曲线联立得二次方程 Ax²+Bx+C=0, 韦达定理: x₁+x₂=−B/A, x₁x₂=C/A (A≠0)。"
            "弦长 |AB|=√(1+k²)·|x₁−x₂|; 中点坐标 (½(x₁+x₂), ½(y₁+y₂))。"
            "判别式 Δ>0 保证两个交点。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["韦达", "韦达定理", "弦长", "中点", "联立", "圆锥曲线"],
        applies_to=["韦达", "弦长", "中点弦", "联立"],
    ),
    KnowledgeEntry(
        id="ag-midpoint-difference",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="点差法 (中点弦问题)",
        content=(
            "设弦两端点 (x₁,y₁),(x₂,y₂) 在圆锥曲线上, 中点 (x₀,y₀)。"
            "两式相减得 (x₁−x₂) 与 (y₁−y₂) 关系, 结合斜率 k=(y₁−y₂)/(x₁−x₂), "
            "可快速求中点弦斜率, 避免联立。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["点差法", "中点弦", "圆锥曲线", "斜率", "中点"],
        applies_to=["点差法", "中点弦", "中点"],
    ),
    KnowledgeEntry(
        id="ag-line-relation",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="两直线位置关系 (平行/垂直)",
        content=(
            "l₁: A₁x+B₁y+C₁=0, l₂: A₂x+B₂y+C₂=0。"
            "平行: A₁B₂=A₂B₁ 且 A₁C₂≠A₂C₁; 垂直: A₁A₂+B₁B₂=0; "
            "斜率形式: 平行 k₁=k₂, 垂直 k₁k₂=−1。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["直线", "平行", "垂直", "位置关系", "斜率"],
        applies_to=["两直线", "平行", "垂直", "位置关系"],
    ),
    KnowledgeEntry(
        id="ag-point-line-dist",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="点到直线距离公式",
        content=(
            "点 (x₀,y₀) 到直线 Ax+By+C=0 的距离 d=|Ax₀+By₀+C|/√(A²+B²)。"
            "用于求距离、平行线间距、面积等。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["距离", "点到直线", "公式", "直线"],
        applies_to=["点到直线距离", "距离", "平行线距离"],
    ),
    KnowledgeEntry(
        id="ag-conic-unified",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="圆锥曲线统一定义与离心率",
        content=(
            "统一定义: 到定点 (焦点) 与定直线 (准线) 距离之比 e 为常数, "
            "e<1 椭圆, e=1 抛物线, e>1 双曲线。"
            "准线方程: 椭圆 x=±a²/c, 双曲线 x=±a²/c, 抛物线 x=−p/2。"
        ),
        method_priority=MethodPriority.ADVANCED,
        tags=["圆锥曲线", "统一定义", "离心率", "准线", "焦点"],
        applies_to=["圆锥曲线统一定义", "离心率", "准线"],
    ),
    KnowledgeEntry(
        id="ag-line-conic",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        title="直线与圆锥曲线位置关系",
        content=(
            "联立直线与圆锥曲线方程得二次方程, 由判别式 Δ 判定: Δ>0 相交, Δ=0 相切, Δ<0 相离。"
            "切线条件、弦长、中点均由韦达定理导出。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["直线", "圆锥曲线", "位置关系", "判别式", "相交", "相切"],
        applies_to=["直线与圆锥曲线", "相交", "相切", "判别式"],
    ),
]

ANALYTIC_METHODS: list[MethodEntry] = [
    MethodEntry(
        id="am-vieta",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        name="韦达定理法",
        priority=MethodPriority.IN_CLASS,
        description="联立直线与曲线, 用韦达定理处理弦长、中点、两根关系。",
        steps=["联立方程消元", "写出韦达两根和与积", "用弦长/中点公式表达目标"],
        applicable_when=["韦达", "弦长", "中点弦", "联立", "直线与圆锥曲线"],
        example="求过椭圆焦点的弦长。",
    ),
    MethodEntry(
        id="am-midpoint-difference",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        name="点差法",
        priority=MethodPriority.IN_CLASS,
        description="用点差法快速求中点弦斜率。",
        steps=["设两端点及中点", "代入曲线方程相减", "用斜率表示"],
        applicable_when=["点差法", "中点弦", "中点"],
        example="求椭圆中点弦所在直线方程。",
    ),
    MethodEntry(
        id="am-coordinate",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        name="坐标法 / 方程法",
        priority=MethodPriority.IN_CLASS,
        description="设点坐标, 列方程求解。",
        steps=["设点或直线方程", "利用条件列方程", "求解"],
        applicable_when=["直线方程", "圆方程", "坐标法", "求轨迹"],
        example="求动点轨迹方程。",
    ),
    MethodEntry(
        id="am-focal-chord",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        name="焦点弦公式法",
        priority=MethodPriority.IN_CLASS,
        description="用焦点弦公式简化计算。",
        steps=["确认曲线类型与焦点", "套焦点弦公式", "结合韦达定理"],
        applicable_when=["焦点弦", "弦长", "焦点"],
        example="求抛物线焦点弦最小值。",
    ),
    MethodEntry(
        id="am-polar",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        name="极坐标法",
        priority=MethodPriority.ADVANCED,
        description="用极坐标处理焦点弦、离心率相关问题。",
        steps=["以焦点为极点建系", "写圆锥曲线极坐标方程 ρ=ep/(1−e·cosθ)", "求解"],
        applicable_when=["极坐标", "焦点弦", "离心率"],
        example="用极坐标推导焦点弦长公式。",
    ),
    MethodEntry(
        id="am-machine",
        subject=SubjectType.ANALYTIC_GEOMETRY,
        name="机器求解法",
        priority=MethodPriority.MACHINE,
        description="用符号求解器联立方程组求解。",
        steps=["列出方程组", "调用符号求解", "判定有效解"],
        applicable_when=["机器证明", "复杂解析几何计算"],
        example="用 sympy 求交点与弦长。",
    ),
]

# =====================================================================================
# Solid geometry
# =====================================================================================

SOLID_ENTRIES: list[KnowledgeEntry] = [
    KnowledgeEntry(
        id="sg-line-plane-parallel",
        subject=SubjectType.SOLID_GEOMETRY,
        title="线面平行判定与性质",
        content=(
            "判定: 平面外一条直线与平面内一条直线平行, 则该直线与此平面平行。"
            "性质: 一条直线与一平面平行, 过该直线的任一平面与已知平面相交, "
            "交线与该直线平行。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["线面", "线面平行", "平行", "判定", "立体几何"],
        applies_to=["线面平行", "证明平行", "平行"],
    ),
    KnowledgeEntry(
        id="sg-line-plane-perp",
        subject=SubjectType.SOLID_GEOMETRY,
        title="线面垂直判定与性质",
        content=(
            "判定: 一条直线与平面内两条相交直线都垂直, 则该直线与此平面垂直。"
            "性质: 垂直于同一平面的两直线平行; 直线垂直于平面, 则垂直于平面内任一直线。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["线面", "线面垂直", "垂直", "判定", "立体几何"],
        applies_to=["线面垂直", "证明垂直", "垂直"],
    ),
    KnowledgeEntry(
        id="sg-plane-plane-parallel",
        subject=SubjectType.SOLID_GEOMETRY,
        title="面面平行判定与性质",
        content=(
            "判定: 一平面内两相交直线分别平行于另一平面, 则两平面平行。"
            "性质: 两平面平行, 与第三平面相交所得交线平行。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["面面", "面面平行", "平行", "判定", "立体几何"],
        applies_to=["面面平行", "证明平行"],
    ),
    KnowledgeEntry(
        id="sg-plane-plane-perp",
        subject=SubjectType.SOLID_GEOMETRY,
        title="面面垂直判定与性质",
        content=(
            "判定: 一平面经过另一平面的一条垂线, 则两平面垂直。"
            "性质: 两平面垂直, 一平面内垂直于交线的直线垂直于另一平面。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["面面", "面面垂直", "垂直", "判定", "立体几何"],
        applies_to=["面面垂直", "证明垂直"],
    ),
    KnowledgeEntry(
        id="sg-dihedral-angle",
        subject=SubjectType.SOLID_GEOMETRY,
        title="二面角的定义与求法",
        content=(
            "二面角: 从一条直线出发的两个半平面所组成的图形。"
            "二面角的平面角: 在棱上取一点, 两半平面内分别作棱的垂线, 两垂线夹角即为平面角。"
            "求法: 定义法/三垂线法/面积射影法 (cosθ=S射影/S原)。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["二面角", "平面角", "棱", "射影", "立体几何"],
        applies_to=["二面角", "求二面角"],
    ),
    KnowledgeEntry(
        id="sg-three-perp",
        subject=SubjectType.SOLID_GEOMETRY,
        title="三垂线定理及其逆定理",
        content=(
            "三垂线定理: 平面内一直线与该平面一条斜线在此平面内的射影垂直, "
            "则该直线与此斜线垂直。逆定理亦成立。"
            "常用于证明异面直线垂直、求二面角的平面角。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["三垂线", "三垂线定理", "垂直", "斜线", "射影", "立体几何"],
        applies_to=["三垂线", "证明垂直", "异面直线垂直"],
    ),
    KnowledgeEntry(
        id="sg-space-vector",
        subject=SubjectType.SOLID_GEOMETRY,
        title="空间向量法",
        content=(
            "建立空间直角坐标系, 用向量表示点、方向。"
            "线段长 = |向量|; cos∠ = (a·b)/(|a||b|); "
            "线面角、二面角可用法向量求得。适合计算型立体几何问题。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["空间向量", "向量", "坐标", "法向量", "二面角", "立体几何"],
        applies_to=["空间向量", "求角度", "求距离", "二面角"],
    ),
    KnowledgeEntry(
        id="sg-pyramid-volume",
        subject=SubjectType.SOLID_GEOMETRY,
        title="棱锥的体积与表面积",
        content=(
            "棱锥体积 V=(1/3)·S底·h (h 为高)。"
            "正棱锥侧面积 S侧=(1/2)·C底·l (l 为斜高), 全面积=侧面积+底面积。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["棱锥", "体积", "表面积", "侧面积", "立体几何"],
        applies_to=["棱锥", "求体积", "求表面积"],
    ),
    KnowledgeEntry(
        id="sg-prism-volume",
        subject=SubjectType.SOLID_GEOMETRY,
        title="棱柱的体积与表面积",
        content=(
            "棱柱体积 V=S底·h。直接柱侧面积 S侧=C底·h, 全面积=侧面积+2·底面积。"
            "长方体 V=abc, 正方体 V=a³。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["棱柱", "体积", "表面积", "侧面积", "长方体", "正方体", "立体几何"],
        applies_to=["棱柱", "求体积", "求表面积", "长方体"],
    ),
    KnowledgeEntry(
        id="sg-sphere",
        subject=SubjectType.SOLID_GEOMETRY,
        title="球的体积与表面积",
        content=(
            "球体积 V=(4/3)πR³, 球表面积 S=4πR²。"
            "球面距离: 经过两点的大圆劣弧长。球内接几何体常用截面圆法求解。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["球", "体积", "表面积", "球面", "立体几何"],
        applies_to=["球", "求体积", "求表面积", "球面距离"],
    ),
    KnowledgeEntry(
        id="sg-euler",
        subject=SubjectType.SOLID_GEOMETRY,
        title="欧拉公式 (简单多面体)",
        content=(
            "简单多面体顶点数 V、棱数 E、面数 F 满足 V−E+F=2。"
            "用于分析多面体结构, 结合已知量求未知顶点/棱/面数。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["欧拉", "欧拉公式", "多面体", "顶点", "棱", "面", "立体几何"],
        applies_to=["欧拉公式", "多面体", "顶点棱面"],
    ),
    KnowledgeEntry(
        id="sg-inscribed-sphere",
        subject=SubjectType.SOLID_GEOMETRY,
        title="球内接/外切几何体",
        content=(
            "球内接几何体: 顶点在球面上, 常用截面圆法把空间问题转化为平面问题。"
            "正方体内切球半径=棱长一半, 外接球半径=½√3·棱长。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["球", "内切", "外接", "内接", "正方体", "立体几何"],
        applies_to=["内切球", "外接球", "球内接"],
    ),
]

SOLID_METHODS: list[MethodEntry] = [
    MethodEntry(
        id="sm-line-plane",
        subject=SubjectType.SOLID_GEOMETRY,
        name="线面关系判定法",
        priority=MethodPriority.IN_CLASS,
        description="用线面/面面平行与垂直的判定定理证明位置关系。",
        steps=["识别目标关系", "找判定定理所需条件", "完成证明"],
        applicable_when=["线面平行", "线面垂直", "面面平行", "面面垂直", "证明平行", "证明垂直"],
        example="证明棱锥中两直线平行。",
    ),
    MethodEntry(
        id="sm-dihedral-angle",
        subject=SubjectType.SOLID_GEOMETRY,
        name="二面角法",
        priority=MethodPriority.IN_CLASS,
        description="用定义法/三垂线法/面积射影法求二面角。",
        steps=["确定棱与半平面", "作出平面角(定义法/三垂线法)", "解三角形求角"],
        applicable_when=["二面角", "求二面角"],
        example="求正三棱锥侧面与底面所成二面角。",
    ),
    MethodEntry(
        id="sm-three-perp",
        subject=SubjectType.SOLID_GEOMETRY,
        name="三垂线定理法",
        priority=MethodPriority.IN_CLASS,
        description="用三垂线定理证明线线垂直或求二面角平面角。",
        steps=["找平面与斜线", "作射影", "应用三垂线定理"],
        applicable_when=["三垂线", "证明垂直", "异面直线垂直", "二面角"],
        example="证明棱锥中两异面直线垂直。",
    ),
    MethodEntry(
        id="sm-space-vector",
        subject=SubjectType.SOLID_GEOMETRY,
        name="空间向量法",
        priority=MethodPriority.IN_CLASS,
        description="建系后用向量与法向量求角度与距离。",
        steps=["建空间直角坐标系", "写出关键点与向量", "用点积/法向量求角"],
        applicable_when=["空间向量", "求角度", "求距离", "二面角"],
        example="用向量法求二面角。",
    ),
    MethodEntry(
        id="sm-volume",
        subject=SubjectType.SOLID_GEOMETRY,
        name="体积法 / 等体积法",
        priority=MethodPriority.IN_CLASS,
        description="用体积公式或等体积转换求高或距离。",
        steps=["选合适底面", "套体积公式", "必要时等体积转换求高"],
        applicable_when=["棱锥", "棱柱", "球", "求体积", "求高", "求距离"],
        example="用等体积法求三棱锥的高。",
    ),
    MethodEntry(
        id="sm-machine",
        subject=SubjectType.SOLID_GEOMETRY,
        name="机器证明法",
        priority=MethodPriority.MACHINE,
        description="用符号机器证明验证空间位置关系。",
        steps=["坐标化", "调用机器证明引擎", "输出结论"],
        applicable_when=["机器证明", "复杂立体几何命题"],
        example="用吴方法验证线面垂直命题。",
    ),
]


# =====================================================================================
# Function & derivative (函数与导数)
# =====================================================================================

FUNCTION_ENTRIES: list[KnowledgeEntry] = [
    KnowledgeEntry(
        id="fn-derivative-def",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="导数的定义与基本求导法则",
        content=(
            "导数定义: f'(x) = lim_{h→0} [f(x+h)-f(x)]/h。"
            "基本法则: (c)'=0, (x^n)'=nx^{n-1}, (e^x)'=e^x, (ln x)'=1/x, "
            "(sin x)'=cos x, (cos x)'=-sin x。"
            "四则运算: (u±v)'=u'±v', (uv)'=u'v+uv', (u/v)'=(u'v-uv')/v²。"
            "链式法则: [f(g(x))]'=f'(g(x))·g'(x)。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["导数", "求导", "链式法则"],
        applies_to=["求导数", "切线斜率", "单调性分析"],
    ),
    KnowledgeEntry(
        id="fn-monotonicity",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="用导数判断单调性",
        content=(
            "设 f(x) 在区间 I 上可导: "
            "f'(x)>0 ⟹ f 单调递增; f'(x)<0 ⟹ f 单调递减。"
            "f'(x)=0 的点为驻点, 需检查左右导数符号变化确定极值。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["单调性", "极值", "导数应用"],
        applies_to=["求单调区间", "求极值"],
    ),
    KnowledgeEntry(
        id="fn-extremum",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="极值与最值",
        content=(
            "极值必要条件: f'(x₀)=0 (或导数不存在)。"
            "极值充分条件: 一阶导数变号(第一充分条件) 或 f''(x₀)≠0 (第二充分条件)。"
            "闭区间最值: 比较驻点、端点、不可导点处的函数值。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["极值", "最值", "充分条件"],
        applies_to=["求极值", "求最值"],
    ),
    KnowledgeEntry(
        id="fn-tangent",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="切线方程",
        content=(
            "曲线 y=f(x) 在点 (x₀, f(x₀)) 处的切线方程: "
            "y - f(x₀) = f'(x₀)(x - x₀)。"
            "切线斜率 k = f'(x₀)。"
            "过外点 (a, b) 的切线: 设切点为 (x₀, f(x₀)), 联立 "
            "b - f(x₀) = f'(x₀)(a - x₀) 解出 x₀。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["切线", "斜率"],
        applies_to=["求切线方程", "切线条件"],
    ),
    KnowledgeEntry(
        id="fn-zero",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="零点问题",
        content=(
            "f(x₀)=0 ⟹ x₀ 是零点。"
            "零点存在定理: f 连续且 f(a)·f(b)<0 ⟹ (a,b) 内有零点。"
            "零点个数: 分析单调性 + 端点符号, 或用导数画出函数图像。"
            "分离参数法: f(x)-m=0 的零点个数 ⟺ m 与 g(x) 的交点个数。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["零点", "交点", "参数分离"],
        applies_to=["求零点个数", "零点存在性"],
    ),
    KnowledgeEntry(
        id="fn-construction",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="构造函数法",
        content=(
            "证明不等式 f(x)>g(x) 时, 构造 h(x)=f(x)-g(x), "
            "用导数分析 h(x) 的单调性/极值, 证明 h(x)>0。"
            "常见构造: h(x)=f(x)-kx (截距), h(x)=f(x)/x (比值), "
            "h(x)=e^x·f(x) (指数乘积), h(x)=ln x - ax (对数线性)。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["构造函数", "不等式证明"],
        applies_to=["不等式恒成立", "不等式证明"],
    ),
    KnowledgeEntry(
        id="fn-separation",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="分离参数法",
        content=(
            "含参数不等式恒成立: 将参数 a 分离到一侧, "
            "f(x,a)≥0 ⟺ a ≥ g(x) (或 a ≤ g(x)), "
            "再求 g(x) 的最值。"
            "a ≥ g(x)_{max} 或 a ≤ g(x)_{min} 即为所求范围。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["分离参数", "恒成立", "最值"],
        applies_to=["参数范围", "恒成立问题"],
    ),
    KnowledgeEntry(
        id="fn-integral",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="定积分与面积",
        content=(
            "牛顿-莱布尼茨公式: ∫_a^b f(x)dx = F(b) - F(a), F'(x)=f(x)。"
            "曲线围成面积: S = ∫_a^b [上(上) - 下(下)] dx。"
            "旋转体体积: V = π∫_a^b [f(x)]² dx。"
        ),
        method_priority=MethodPriority.IN_CLASS,
        tags=["积分", "面积", "体积"],
        applies_to=["求面积", "求积分", "旋转体体积"],
    ),
    KnowledgeEntry(
        id="fn-lhopital",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="洛必达法则",
        content=(
            "0/0 或 ∞/∞ 型极限: lim f(x)/g(x) = lim f'(x)/g'(x)。"
            "需 f,g 在去心邻域可导且 g'(x)≠0。可多次使用。"
        ),
        method_priority=MethodPriority.ADVANCED,
        tags=["极限", "洛必达"],
        applies_to=["求极限"],
    ),
    KnowledgeEntry(
        id="fn-taylor",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        title="泰勒展开",
        content=(
            "f(x) = f(x₀) + f'(x₀)(x-x₀) + f''(x₀)/2!(x-x₀)² + ... + f^(n)(x₀)/n!(x-x₀)^n + R_n。"
            "常用: e^x = 1+x+x²/2!+..., sin x = x-x³/3!+..., cos x = 1-x²/2!+..., "
            "ln(1+x) = x-x²/2+x³/3-...。"
            "竞赛中用于精确估计不等式。"
        ),
        method_priority=MethodPriority.COMPETITION if hasattr(MethodPriority, 'COMPETITION') else MethodPriority.ADVANCED,
        tags=["泰勒", "展开", "近似"],
        applies_to=["不等式证明", "极限计算"],
    ),
]

FUNCTION_METHODS: list[MethodEntry] = [
    MethodEntry(
        id="fn-m-derivative-analysis",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        name="导数分析法",
        priority=MethodPriority.IN_CLASS,
        description="求导 → 分析符号 → 确定单调性/极值/最值",
        steps=["求 f'(x)", "解 f'(x)=0 找驻点", "列表分析符号变化", "确定单调区间和极值"],
        applicable_when=["单调性", "极值", "最值"],
        example="求 f(x)=x³-3x 的单调区间和极值。",
    ),
    MethodEntry(
        id="fn-m-construction",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        name="构造函数法",
        priority=MethodPriority.IN_CLASS,
        description="构造辅助函数, 用导数证明不等式",
        steps=["构造 h(x)=f(x)-g(x)", "求 h'(x) 分析单调性", "求 h 的最值", "由最值符号得结论"],
        applicable_when=["不等式证明", "恒成立"],
        example="证明 e^x ≥ 1+x。",
    ),
    MethodEntry(
        id="fn-m-separation",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        name="分离参数法",
        priority=MethodPriority.IN_CLASS,
        description="分离参数 → 转化为求函数最值",
        steps=["将参数 a 移到一侧", "得到 a ≥ g(x) 或 a ≤ g(x)", "求 g(x) 最值", "得参数范围"],
        applicable_when=["参数范围", "恒成立问题"],
        example="若 f(x)=x²+ax+1≥0 恒成立, 求 a 范围。",
    ),
    MethodEntry(
        id="fn-m-tangent",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        name="切线分析法",
        priority=MethodPriority.IN_CLASS,
        description="利用切线条件求参数或证明相切",
        steps=["设切点 (x₀, f(x₀))", "切线斜率 k=f'(x₀)", "代入切线方程条件", "解方程"],
        applicable_when=["切线方程", "公切线"],
        example="求曲线 y=ln x 过原点的切线方程。",
    ),
    MethodEntry(
        id="fn-m-classification",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        name="分类讨论法",
        priority=MethodPriority.IN_CLASS,
        description="对参数取值分类, 分别分析函数行为",
        steps=["确定分类标准(参数零点)", "分区间讨论单调性", "汇总各情况结论"],
        applicable_when=["含参函数", "多情况讨论"],
        example="讨论 f(x)=x²-alnx 的单调性。",
    ),
    MethodEntry(
        id="fn-m-lhopital",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        name="洛必达法则",
        priority=MethodPriority.ADVANCED,
        description="求 0/0 或 ∞/∞ 型极限",
        steps=["验证是 0/0 或 ∞/∞", "对分子分母分别求导", "取极限", "必要时重复"],
        applicable_when=["极限计算", "未定式"],
        example="求 lim_{x→0} (sin x)/x。",
    ),
    MethodEntry(
        id="fn-m-taylor",
        subject=SubjectType.FUNCTION_DERIVATIVE,
        name="泰勒展开法",
        priority=MethodPriority.ADVANCED,
        description="用泰勒展开精确估计函数值, 证明不等式",
        steps=["选展开点 x₀", "写出泰勒展开式", "截断到适当阶数", "比较余项符号"],
        applicable_when=["不等式证明", "极限计算", "近似"],
        example="证明 ln(1+x) ≥ x - x²/2 (x>0)。",
    ),
]


# =====================================================================================
# Aggregated exports
# =====================================================================================

CURATED_ENTRIES: list[KnowledgeEntry] = (
    PLANE_ENTRIES + TRIANGLE_ENTRIES + ANALYTIC_ENTRIES + SOLID_ENTRIES
    + FUNCTION_ENTRIES
)
CURATED_METHODS: list[MethodEntry] = (
    PLANE_METHODS + TRIANGLE_METHODS + ANALYTIC_METHODS + SOLID_METHODS
    + FUNCTION_METHODS
)


# =====================================================================================
# Grade tagging: mark junior-high-applicable items as JUNIOR so the knowledge
# manager can scope retrieval by grade. Items not matched stay SENIOR default.
# =====================================================================================

# Keywords that indicate junior-high (初中) curriculum content.
_JUNIOR_KEYWORDS = {
    # plane geometry
    "全等", "相似", "勾股", "圆周角", "圆心角", "切线", "弦", "割线", "射影定理",
    "三角形内角和", "外角", "中线", "高线", "角平分线", "中位线", "平行线",
    "等腰", "等边", "直角三角形", "垂径", "切线长", "相交弦",
    # triangle solving (正弦/余弦定理在初中阶段部分接触, 高中正式)
    "海伦", "面积公式",
    # solid geometry basics introduced in junior high
    "柱", "锥", "台", "球", "体积", "表面积", "展开",
}
# Keywords that are strictly senior-high (高中) only.
_SENIOR_ONLY_KEYWORDS = {
    "向量", "坐标法", "解析", "极坐标", "参数方程", "椭圆", "双曲线", "抛物线",
    "射影几何", "仿射", "复数法", "重心坐标", "空间向量", "法向量", "二面角",
    "吴方法", "机器证明", "投影", "轨迹方程", "韦达定理",
    # function & derivative (all senior-only)
    "导数", "求导", "积分", "切线斜率", "极值", "最值", "单调性",
    "链式法则", "驻点", "拐点", "泰勒", "洛必达", "拉格朗日",
}
# Keywords that indicate competition-level (竞赛) content.
_COMPETITION_KEYWORDS = {
    "泰勒展开", "洛必达", "拉格朗日", "中值定理", "极坐标", "参数方程",
    "射影几何", "仿射", "复数法", "配点", "引理", "极端原理", "齐次化",
    "竞赛", "奥数", "imo",
}


def _tag_grade(item) -> None:
    """In-place tag an entry/method's grade based on its text content."""
    text = " ".join([
        getattr(item, "title", "") or getattr(item, "name", ""),
        getattr(item, "content", "") or getattr(item, "description", ""),
        " ".join(getattr(item, "tags", []) or []),
    ])
    is_competition = any(k in text.lower() for k in _COMPETITION_KEYWORDS) or \
                     any(k in text for k in _COMPETITION_KEYWORDS)
    is_senior_only = any(k in text for k in _SENIOR_ONLY_KEYWORDS)
    is_junior = any(k in text for k in _JUNIOR_KEYWORDS)
    if is_competition:
        item.grade = GradeLevel.COMPETITION
    elif is_senior_only:
        item.grade = GradeLevel.SENIOR
    elif is_junior:
        item.grade = GradeLevel.JUNIOR
    else:
        item.grade = GradeLevel.SENIOR


for _e in CURATED_ENTRIES:
    _tag_grade(_e)
for _m in CURATED_METHODS:
    _tag_grade(_m)


def entries_by_subject(subject: SubjectType) -> list[KnowledgeEntry]:
    return [e for e in CURATED_ENTRIES if e.subject == subject]


def methods_by_subject(subject: SubjectType) -> list[MethodEntry]:
    return [m for m in CURATED_METHODS if m.subject == subject]
