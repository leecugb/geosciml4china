# 编码-地质语义映射表的贝叶斯最优估计模型（2026-10-07 设计定版）

> 任务定义（用户）：**以 codebook 的编码-地质语义为变量，以先验知识为约束**，
> 设计贝叶斯最优化估计模型。本模型为三层逻辑 L2 的统计内核升级——
> 接入映射表的 `posterior` 列与决策阈值导出，确定性骨架与裁定教条不动。
>
> **本质过程（2026-10-08 用户裁定）**：以矛盾项为代价函数最优化 codebook
> ——码书选择 = 最小化证伪算子产出的登记总量（+压平罚防退化），见 §5。

---

## 1. 变量（估计对象）

$$\boldsymbol{\theta} = (\theta_c)_{c \in \mathcal{C}_u}, \quad \theta_c \in \Sigma$$

- $\mathcal{C}_u$：未注册码集（注册码不估计——硬钉，见 §2 C1）；
- $\Sigma$：语义词表 = $\Sigma_d$（决定性：正/逆/推覆/左行/右行/活动/复合/边界断裂…）∪ $\{\sigma_\varnothing$（断层泛称 null 语义）, 推测断层（证据轴）$\}$；
- 联合变量：运动学码义 $\boldsymbol{\kappa} = (\kappa_g)_{g \in \mathcal{G}_u}$（GZELD 未注册码，经成因联系与 $\theta$ 耦合估计，见 §3.3）。

**映射表即后验**：`code_semantics_map_<key>.csv` 的每行 = 一个变量的后验摘要
（MAP 点估计 + 后验分布 + 置信=最大后验）。

## 2. 约束体系（先验知识的形式化）

### C1 · 硬约束（点钉——裁定教条）

$$\theta_c = \sigma_c^{\text{reg}}, \quad c \in \mathcal{C}_{\text{reg}}
\qquad (\text{注册表/覆盖库裁定：后验恒为点质量 } \delta)$$

**注册码不进入优化**——「裁定>机器、永不自动改码」的数学形态：不是强先验，
而是变量消去（pinned variables）。

### C2 · 全局结构约束（变量耦合）

| 约束 | 形式 | 来源裁定 |
|---|---|---|
| 逆断层一幅一码 | $\sum_{c\in\mathcal{C}_u} \mathbb{1}[\theta_c = \text{逆断层}] \le 1$ | 2026-10-04（05/31 案） |
| 复活签名 | $n_c(\text{逆})\ge 3 \land n_c(\text{正})\ge 3 \land \min/\max \ge 0.5 \Rightarrow \pi(\theta_c{=}\text{活动断层})$ 提升 | 2026-10-04（31 案） |
| 可行性（兜底） | $\theta_c = \sigma_\varnothing$ 恒可行（管线畅通公理） | 2026-10-01 |

C2 使问题成为**约束联合优化**而非逐码独立 MAP——码与码通过唯一码规则耦合。

### C3 · 软约束（信息先验）

$$\pi(\theta_c) \propto \exp\!\bigl(\lambda_{\text{sig}} \mathbb{1}[\theta_c{=}\text{推测断层},\ c \in \text{签名集}] + \cdots\bigr)$$

- 签名通道（全段无倾角+真覆盖≥2）→ 推测断层方向的信息先验；
- 断层名性质词按实体聚合后入似然（非先验——名是观测不是约束）。

## 3. 似然模型（拓扑测量的统计化）

### 3.1 段级证据向量

段 $s$ 的证据由拓扑算子族产出（范式 §7.5）：

$$\boldsymbol{v}(s) = \bigl(v_{\text{probe}},\ v_{\text{aux}},\ v_{\text{hook}},\ v_{\text{cover}},\ v_{\text{coinc}},\ v_{\text{name}},\ v_{\text{kin}},\ v_{\text{dip}}\bigr)(s)$$

连续量（倾角/覆盖率/重合度）经期望集隶属二值化：
$v_{\text{dip}} = \mathbb{1}[\text{dip} \in [lo_\sigma, hi_\sigma]]$
（EXPECT 域即离散化边界——证伪算子与似然共享同一组期望集，模型自洽）。

### 3.2 通道混淆矩阵（待估参数）

每通道×语义一对速率（灵敏度/特异度）：

$$\alpha_k(\sigma) = P(v_k{=}1 \mid \sigma), \qquad \beta_k(\sigma) = P(v_k{=}0 \mid \neg\sigma)$$

**经验贝叶斯估计**（标注集现成）：用户裁定案例（~50 例）+ verified 段
（jwsss 124 / jwss 117）+ 冲突册裁定回溯——

$$\hat\alpha_k(\sigma) = \frac{\#\{v_k{=}1,\ \sigma\} + \tfrac12}{\#\{\sigma\} + 1}
\quad(\text{Laplace 平滑，薄证据格如实大方差})$$

**相关通道合并**（F1 裁定同构，谱系同源不双计）：探针-重复-老盖新同源于
单元对测量 → 复合特征；aux 判别×GZECE 值匹配同源 → 单计。
**实体聚类折权**：实体 $f$ 含 $m_f$ 段，段似然幂次 $1/m_f$
（F001 型 12 段实体不再投 12 票）。

### 3.3 成因联系耦合（GZEEB×GZELD 联合估计）

应力体制映射为软约束（2026-10-03 裁定）：

$$\kappa_g \mid \theta_c \sim \text{Categorical}\bigl(\phi(\theta_c)\bigr),
\qquad \phi:\ \text{逆/推覆}\mapsto\text{压性},\ \text{正}\mapsto\text{张性},\ \text{走滑}\mapsto\text{剪切}$$

$\phi$ 退化（一点集中）时模型退化为现行推导通道；保留方差项使
「推覆×张性」型真实张力可被后验看见而非抹平。

## 4. 后验与约束最优化

$$\max_{\boldsymbol{\theta},\boldsymbol{\kappa}}\
\underbrace{\sum_{c\in\mathcal{C}_u} \log \pi(\theta_c)}_{\text{软约束}}
+\underbrace{\sum_{c}\sum_{s:\,g(s)=c}\sum_{k} \tfrac{1}{m_{f(s)}} \log P\bigl(v_k(s)\,\big|\,\theta_c\bigr)}_{\text{段级似然（实体折权）}}
+\underbrace{\sum_{g}\sum_{s:\,h(s)=g} \log P\bigl(\kappa_g \mid \theta_{g(s)}\bigr)}_{\text{运动学耦合}}$$

$$\text{s.t.}\quad \theta_c = \sigma_c^{\text{reg}}\ (c\in\mathcal{C}_{\text{reg}});\qquad
\sum_c \mathbb{1}[\theta_c{=}\text{逆断层}] \le 1;\qquad
\theta_c \in \Sigma \ (\sigma_\varnothing \text{ 恒可行})$$

**求解**（精确，无需采样）：逐码后验解析计算（$\Sigma$ 离散小集）→
逆断层唯一码约束以「后验最大者主张、余者剔除逆分量后重取」消解
（现行逻辑的贝叶斯对应物）——全局结构保持**确定性**。

## 5. 贝叶斯最优决策（损失函数导出阈值——裁定常数的理论化）

### 5.1 本质过程裁定（2026-10-08 用户）：以矛盾项为代价函数最优化 codebook

**矛盾册不是下游报告，而是目标函数本身**。码书 $\boldsymbol{\theta}$ 的
选择 = 使证伪算子产出的登记总量最小化：

$$J(\boldsymbol{\theta}) = \underbrace{\sum_{s \notin S_{\text{adj}}}
\Bigl|\operatorname{conflict}\bigl(s \mid \theta_{g(s)}\bigr)\Bigr|}_{K(\boldsymbol{\theta})\ \text{矛盾项——段级证据对终态语义的违反计数}}
\;+\; \lambda \underbrace{\sum_{c} \sum_{\sigma \in \Sigma_d}
n(c,\sigma)\,\mathbb{1}\bigl[\theta_c \ne \sigma\bigr]}_{F(\boldsymbol{\theta})\ \text{压平罚——被码义压制的段级决定性证据量}}$$

**防退化分析（良态性）**：纯 $K$ 退化——$\operatorname{EXPECT}(\sigma_\varnothing)=\varnothing$
使全泛称码书 $K=0$ 平凡最优。$F$ 项（压平证据量）是使问题良态的
**必要对手项**：泛称不付矛盾但付压制。
- $\lambda=0$：全泛称退化；$\lambda\to\infty$：现行主导规则（泛称仅当无族义）；
- 现行系统 = 词典序实现（先主导合格性约束、再登记 $K$ 不重优化）——
  有限 $\lambda$ 是其软化与可校准化。

**两案验证**：
- jwsss 05：纯 $K$ 会错选泛称（零违反），$F$=49 段决定性证据压住 → 逆断层 ✓；
- jwsss 01：$K(\text{逆}){>}0$ vs $F(\text{泛称})$=41 段压平 → 现行泛称结论 ✓。

**$K$/$F$ 会计恒等式**：违反（具体语义被证据违反）+ 压制（证据被非具体语义
压制）= 语义收紧的全部代价——泛称是「付压制以避违反」的合法态，
兼容定理（EXPECT$(\sigma_\varnothing)=\varnothing$）保持为 $K$ 分量性质。

### 5.2 收敛观的重述

人机协同循环 = 对 $J$ 的下降迭代：映射表 `user_semantic` 编辑与覆盖库裁定
是**人工下降步**；贝叶斯层是**自动下降提议器**；横幅时序
（jwsss 130→66→22、jwss 96→32→15→7）即 $J$ 的实测下降轨迹；
verify 的 A23 基线 = $J$ 的数值闸（回归门禁）。

### 5.3 决策规则（保留阈值形态，阈值由 $J$ 校准）

$$\hat\theta_c = \arg\min_{\sigma \in \Sigma}\ \underbrace{K_c(\sigma)}_{\text{该码置 }\sigma\text{ 的全段违反数}} + \lambda\,\underbrace{F_c(\sigma)}_{\text{压平量}}$$

——逐码独立可解（C2 唯一码约束照旧消解）；$\lambda$ 初值由现行判例
回校（使规则在全部已裁定案例上与裁定一致），其后随裁定积累单调精化。

## 6. 与现系统的接口（不动骨架）

| 现行机制 | 贝叶斯模型中的位置 | 变更 |
|---|---|---|
| 映射表 semantic 列 | MAP 点估计 $\hat\theta_c$ | 不变 |
| 映射表 confidence 列 | **真后验概率** $P(\hat\theta_c \mid E_c)$ 替换手工分档 | 升级 |
| 提案表分布列 | 后验分布全形（$\Sigma$ 各值概率） | 新增列 |
| 压平证据量 | $F_c(\hat\theta_c)$——目标函数的压制分量（§5.1） | 新增列（盲区显性化） |
| 继承/核对后置/冲突册 | 不变（证伪层独立） | 不动 |
| 确定性重放 | 模型工件（通道混淆矩阵表）版本化即可保持 | 版本化 |
| 注册表/覆盖库 | C1 点钉 | 不动 |

## 7. 验证协议

1. **校准性**：裁定案例集上的可靠性曲线（后验 0.9 的码 ≈90% 被裁定维持）；
2. **对照**：贝叶斯 MAP vs 现行主导规则的逐码一致率（jwsss 9 码/jwss 7 码逐格对照，分歧清单入冲突册备裁）；
3. **灵敏度**：混淆矩阵 Laplace 平滑参数与实体折权开关的扰动分析；
4. **回退**：模型工件缺失/不一致时退回现行规则（管线畅通公理）。

## 8. 边界声明

- **注册码域不进入估计**（C1）——贝叶斯只作用于未注册码（冷启动域）；
- 薄证据码后验如实宽（16 码 1 段 → 后验贴近先验）——**不确定性的
  定量化本身就是产出**（映射表从"判定书"变"证据状态报告"）；
- 通道混淆矩阵依赖裁定集规模——首批估计值粗糙，随裁定积累单调精化；
- 模型不改变「语义由先验×拓扑涌现」的范式定位——它把涌现过程从
  裁定常数评分升级为可校准的概率推断，骨架（拓扑测量/继承/证伪）不动。
