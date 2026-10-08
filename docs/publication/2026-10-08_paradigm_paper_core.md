# 编码制图遗产数据的地质语义标定：假设驱动拓扑测量与矛盾最小化分层推断（论文核心框架，2026-10-08）

> **一句话论点**：在「规范统一 × 实践分化 × 词典缺位」的编码制图遗产数据中，
> 我们以假设驱动的拓扑测量构造语义证据，以分层证据聚合完成码级语义标定，
> 并以矛盾项最小化为目标函数最优化编码-语义码书——矛盾如实登记交专家裁定、
> 原始数据永不改写——三幅 1:25 万图幅（310/289/341 断层段）全链验证。

候选题名（中）：**面向编码制图遗产数据的地质语义标定框架：假设驱动的拓扑测量与矛盾最小化的分层推断**
候选题名（英）：*Calibrating geological semantics in legacy cartographic encodings: hypothesis-driven topological measurement with conflict-minimizing hierarchical inference*

---

## 1. 问题类（Problem class）

编码制图系统（以 MapGIS 为例）的数据结构为**成图**服务：地质语义分散在
编码值、图形符号、注记文本与空间关系之中，**没有一个字段直接陈述语义**。
三幅 1:25 万图幅（库尔干/英吉沙/奥依亚依拉克）实证归纳六型松散：

| # | 松散类型 | 实证 | 结构性后果 |
|---|---|---|---|
| L1 | 码面同构、码义随幅 | 断层类型码三幅共现锚码仅 {01,05,16} | 码义必须本幅重新发现 |
| L2 | 一码多义 | 某码 155 段中 逆断层×34/推覆×3/正断层×3 真实混杂 | 单一码义必压平或必错判 |
| L3 | 类目标签多体系 | 辅助点类目三幅三套中文标签 | 判据不可直接跨幅继承 |
| L4 | 同槽混用/格式漂移 | 轴面倾向「南倾」×「225」；西里尔 г=γ 误录 | 需规范化通道 |
| L5 | 完备度梯度 | 倾向字段填充率 0%/35/10 值 | 判据适用域必先验 |
| L6 | 语义依赖空间耦合 | 产状概念=三元素空间耦合才成立 | 语义须从拓扑关系构造 |

**问题类陈述**：规范层统一（国家标准）、数据层系统性偏离、解释偏离所需的
词典不可得——遗产数据救援（无规范老数据）、schema matching（两个形式化
规范）、地图 QA（只管几何）三类文献共同漏掉此类。

## 2. 框架公设

**P1 本体分层**：语义按证据独立性分解为正交轴（结构 ⊥ 活动 ⊥ 证据），
各层独立标定、互不污染——山前推覆前锋段（结构=推覆体边界 ∧ 活动=活动）
两层同真不冲突，正因正交。

**P2 统计分层**：推断三级——样本级（段证据聚合）→ 总体级（码级最大
主导）→ 演绎级（同码全继承）；上级对下级最高优先级（类别编码值裁定）。

**P3 关系即观测**：编码值是待标定标签；语义证据来自**拓扑关系与先验的
对照测量**——先验决定测量什么（假设驱动观测）。

**P4 证伪保持**：矛盾是产出而非故障——期望核对后置、如实登记、
永不自动改码；缺陷走「发现→裁定→覆盖库→复检」闭环。

## 3. 数学模型

### 3.1 对象与记号

段集 $\mathcal{S}$（$|\mathcal S|$=310/289/341）；码集 $\mathcal C$；
编码映射 $g:\mathcal S\to\mathcal C$（原编图者赋予，不改）；
语义词表 $\Sigma=\Sigma_d\cup\{\sigma_\varnothing\}$（决定性语义 ∪ 泛称 null 语义）；
证据通道集 $K$；先验库 $\mathcal P$（接触表/时代序/注册表/覆盖库）。

### 3.2 观测模型：拓扑测量算子族

先验知识构造五类测量（假设驱动观测）：

$$\begin{aligned}
\mathcal T_{\rm probe}&:\ s \mapsto (u_L, u_R) &&\text{面元-线双侧探针（100 m）}\\
\mathcal C&:\ (s,U) \mapsto |s \cap \partial U|/|s| &&\text{线-界线重合}\\
\mathcal I&:\ (s,U) \mapsto |s \cap U|/|s| &&\text{线-面包含}\\
\mathcal N&:\ p \mapsto (s^*, s_{\rm arc}, d_\perp, {\rm side}) &&\text{点-链邻近归属}\\
\Pi&:\ \text{最小总距 1:1 指派} &&\text{点-点配对（注释依附/钩对/三联体）}
\end{aligned}$$

### 3.3 样本级：证据聚合（evidence aggregation）

$$V(s,\sigma)=\sum_{k\in K} w_k\, v_k(s,\sigma), \qquad
\hat\sigma_1(s)=\arg\max_\sigma V(s,\sigma)\ \ (V\ge\theta_{\min})$$

权重 $w_k$ 与门槛 $\theta_{\min}$ 为专家裁定常数（灵敏度分析见 §6）；
决定性通道免聚合直判（如老盖新 $\operatorname{rank}(u_{hw})<\operatorname{rank}(u_{fw})\Rightarrow$ 推覆体边界）。
*注：本模型是确定性的证据聚合评分器，非概率似然——其概率化扩展见 §3.7。*

### 3.4 总体级：码级分层估计

$$n(c,\sigma)=|\{s: g(s)=c,\ \hat\sigma_1(s)=\sigma\}|;\qquad
\hat\sigma_2(c)=\arg\max_{\sigma\in\Sigma_d} n(c,\sigma)
\ \ \text{iff}\ \ \frac{n(c,\sigma^*)}{\sum_\tau n(c,\tau)}\ge\theta_{\rm dom}$$

结构约束：逆断层一幅一码（$\sum_c\mathbb 1[\theta_c{=}\text{逆}]\le 1$）；
复活签名（正逆共存且可比 $\Rightarrow$ 活动断层）；
三源优先级：注册裁定 $\succ$ 签名通道 $\succ$ 聚合主导；
无族义 $\Rightarrow \sigma_\varnothing$。

### 3.5 目标函数：矛盾项最小化（本质过程）

码书选择 = 最小化证伪算子产出的登记总量 + 压平罚：

$$J(\boldsymbol\theta)=\underbrace{\sum_{s\notin S_{\rm adj}}\bigl|\operatorname{conflict}\bigl(s\mid\theta_{g(s)}\bigr)\bigr|}_{K\ \text{矛盾项（违反计数）}}\;+\;\lambda\underbrace{\sum_{c}\sum_{\sigma\in\Sigma_d}n(c,\sigma)\,\mathbb 1[\theta_c\ne\sigma]}_{F\ \text{压平罚（被压制的段级决定性证据）}}$$

- **防退化**：$\operatorname{EXPECT}(\sigma_\varnothing)=\varnothing$ 使全泛称码书 $K{=}0$
  平凡最优——$F$ 项是良态性的必要对手（泛称付压制以避违反）；
- $\lambda{=}0$ 退化为全泛称；$\lambda{\to}\infty$ 退化为纯主导规则；
  有限 $\lambda$ 由已裁定案例集回校；
- 约束：注册码点钉（$\theta_c=\sigma_c^{\rm reg}$，裁定>机器）、
  唯一码约束、泛称恒可行（管线畅通）。

### 3.6 演绎级：继承与证伪算子

$$\sigma_{\rm final}(s)=\hat\sigma_2\bigl(g(s)\bigr)\ (\forall s\notin S_{\rm adj});\qquad
\operatorname{conflict}(s)=\{e\in E(s): e\notin\operatorname{EXPECT}(\sigma_{\rm final}(s))\}$$

**兼容定理**：$\operatorname{EXPECT}(\sigma_\varnothing)=\varnothing \Rightarrow
\forall e:\ \neg\operatorname{conflict}(e,\sigma_\varnothing)$——一般断层兼容一切段级证据；
兼容性是期望集为空的模型推论，非豁免规则。

### 3.7 概率化扩展（贝叶斯内核，可选升级）

未注册码域的约束分层贝叶斯：
$$\max_{\boldsymbol\theta}\ \sum_c\log\pi(\theta_c)+\sum_{c,s,k}\tfrac{1}{m_{f(s)}}\log P\bigl(v_k(s)\mid\theta_c\bigr)
\quad\text{s.t. 注册钉/唯一码/可行性}$$

通道混淆矩阵经经验贝叶斯从裁定集回估（Laplace 平滑、相关通道复合、
实体折权 $1/m_f$）；决策阈值由 $J$ 校准导出而非裁定。
注册码域不进入估计（点钉=裁定教条）。

### 3.8 收敛：矛盾最小化的下降轨迹

人机协同 = 对 $J$ 的下降迭代：映射表编辑与覆盖库裁定=人工下降步；
自动提议器=机器下降步。实测下降轨迹（矛盾横幅时序）：
jwsss 130→66→22、jwss 96→32→15→7。收敛判据 $J_{t+1}-J_t\to 0$
（回归断言闸在案）。

## 4. 证据状态（现成实证）

| 证据 | 内容 | 对应环节 |
|---|---|---|
| 双幅全链验证 | 29 断言×2 幅全绿；镜像 C1–C7；测试套件 115 | 全链正确性 |
| 裸幅冷启动 | 一幅零先验接入至全绿（码义全 MLE 态） | 泛化能力 |
| 编辑-回退回归 | 映射表修改→重放→回退逐字节一致 | 可复现性 |
| 语义升级量化 | faultType 由泛称升级 108/310 与 24/289 段；contactType nil 278→80/405→192 | E1 基线素材 |
| 矛盾下降时序 | 130→66→22 / 96→32→15→7 | J 收敛证据 |
| 裁定案例集 | ~50 例人工裁定 + 124/117 verified 段 | 回估标注集 |

## 5. 边界与局限（先于审稿人写出）

1. **聚合器非似然**：权重为裁定常数；概率化扩展（§3.7）待回估校准——
   当前模型声称为确定性证据聚合，不声称贝叶斯最优；
2. **实体聚类**：段间条件独立假设在实体内部被破坏（同实体多段相关）——
   折权修正在扩展模型中，主线结果以段为单位；
3. **超参数**：$\theta_{\rm dom}$/$\theta_{\min}$/复活比为专家裁定——
   灵敏度分析为投稿前实验（E3）；
4. **泛称信息汇**：码义唯一性压平真实多样性——压平罚 $F$ 使该代价显性化，
   图面表达力与码义一致性的权衡由专家经映射表裁定；
5. **无外部真值**：验证为内部一致性+专家裁定回路——这是标定问题的本性，
   不确定性经结构化登记（冲突册/兜底档案/置信度）如实呈现。

## 6. 投稿前实验清单（全部纯计算，工件现成）

| # | 实验 | 作用 |
|---|---|---|
| E1 | 基线对照：码面直读 vs 三层标定（语义丰富度/nil 收敛） | 实证强度 |
| E2 | 通道消融：单通道关停的语义翻转率 | 模块贡献 |
| E3 | 超参数灵敏度：三阈值 ±25% 扰动翻转数 | 稳健性 |
| E4 | 实体聚类折权对照 | 独立性缺口 |
| E5 | J 下降轨迹图（横幅时序） | 收敛证据 |
| E6 | 置信度校准曲线（S×I×F vs 裁定维持率） | 校准 |

## 7. 与相关工作的关系

- **mapgis2shp**（在审预印本）：格式读取与几何保真——本文讲读取之后的语义标定，引用不复用；
- **GeoSciML 互操作概念论文**（Xu 等 2020）与 **CGS/DDE 平台化发布**：
  概念互操作/省级小尺度平台——本文为图幅级字段级语义保真，对齐互补；
- **遗产数据救援 / schema matching / 地图 QA**：三类文献共同漏掉
  「规范统一×实践分化×词典缺位」问题类——本文的问题定位。

## 8. 术语表（Terminology Ledger，锁定）

| Canonical | 首用定义 | 禁用变体 |
|---|---|---|
| three-level logic | L1 段级/L2 码级/L3 继承 | 三层体系/三级结构 |
| codebook（编码-语义码书） | 码→语义映射表 | 码表/对照表 |
| evidence aggregation | 证据聚合评分器 | ~~MLE 投票~~ |
| conflict register | 矛盾登记册 | 冲突表/异常表 |
| falsification operator | 证伪算子（期望核对后置） | 验证器 |
| null semantics（$\sigma_\varnothing$） | 断层泛称 null 语义 | 一般断层（正文） |
| adjudication | 专家裁定（注册表/覆盖库/user_semantic 三入口） | 人工干预 |
| compatibility theorem | 兼容定理（EXPECT(σ∅)=∅） | — |

## 9. 投稿路线

```
首投 Computers & Geosciences（IAMG 官方刊，方法论对口，一审约两周）
  ├─ 防桌拒：首段立问题类（勿现"某幅清洗"）；E1 数字进摘要；对照图（nature-figure）
  └─ 被拒转 Earth Science Informatics；IAMG 年会先行试水
并行：《地球信息科学学报》中文稿（范式文档为骨架，3–4 周）
条件：E1–E6 实验完成（2–4 周纯计算）
AI 披露：投稿期刊若涉 Nature Portfolio 或同等规范，按现行政策在
        Methods 披露 LLM 辅助范围与人工核验方式（诚实边界）
```
