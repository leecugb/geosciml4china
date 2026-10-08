# Manuscript draft (EN) — 2026-10-08 · Target: Computers & Geosciences (first), ESI (fallback)

## Authors

Shijie Li*, Haiyang He†, Xu Sun, Haoyang Qin, Xiaoyu Liu, Yilin Feng, Zengyun Zuo

Xi'an Mineral Resources Survey, China Geological Survey, Xi'an, China

\* corresponding author · † equal contribution *(marks to be confirmed with the author list of the companion mapgis2shp submission)*

## Title candidates

1. **(most defensible, declarative)** Calibrating geological semantics in legacy cartographic encodings: hypothesis-driven topological measurement and conflict-minimizing hierarchical inference
2. *(finding-led)* Geological semantics recovered from legacy map encodings through topological evidence and conflict-minimizing codebook inference
3. *(method-led)* A falsification-preserving framework for semantic calibration of legacy geological map encodings under divergent practice
4. *(bounded hook)* When the codebook is missing: measuring geological semantics out of cartographic structure

## Abstract

Legacy geological maps encode semantics for drawing, not for reasoning: in systems such as MapGIS, no attribute field directly states what a fault is. In China's 1:250,000 regional survey archive of 729 map sheets, the specification is uniform, but coding practice diverges across sheets, and the codebooks that would explain the divergence are unavailable. Existing approaches miss this class: legacy-data rescue assumes no specification, schema matching assumes two formal specifications, and map quality assurance checks geometry only. We present a calibration framework that treats geological semantics as something to be measured rather than read. Prior geological knowledge drives topological measurements on the data structure — probes, coincidence, containment, proximity, pairing; evidence aggregates from segments to codes through a hierarchical three-level logic; and the codebook itself is chosen by minimizing registered conflicts plus a flattening penalty, while contradictions are preserved in an adjudication register instead of being auto-corrected. On three sheets (310, 289 and 341 fault segments), the framework resolved code-level semantics from scratch, moved 63 of 310 fault segments from generic to specific CGI fault types on a sheet onboarded with no registered codes at all (and 126 of 289 on a partly adjudicated one), resolved 94% and 84% of contact types against 79% and 66% code-literal baselines, and converged registered conflicts on one sheet from 96 to 7 across four development stages through an edit–replay loop that is byte-identical on revert. The framework renders legacy cartographic encodings machine-reasoning-ready without rewriting source data and turns calibration debt into an explicit, adjudicable queue.

*(Chinese note: 摘要按「精确问题→使能设计→主发现→决定性支撑/边界→意义」五段运动；两个量化结果（faultType 升级、矛盾收敛）均直接支撑主 claim；不堆砌实验清单。)*

## 1. Introduction

Regional geological maps are the primary archive of field geology, and in China the 1:250,000 programme alone spans 729 map sheets. As geological data move toward international interoperability — GeoSciML encodings, the OneGeology and DDE platforms — these archives are being converted into machine-reasoning-ready form. Conversion, however, is only as good as the semantics it carries: a fault line exported without its type, kinematics, and evidence class is geometry without geology.

The difficulty is structural. Cartographic systems such as MapGIS encode for drawing: attribute tables mix graphic parameters with coded fields whose meanings are established by practice rather than by specification. Our census of three sheets (Kurgan J43C001002, Yingjisha J43C002003, Aoyiyayilake J45C004001) found identical attribute schemas yet systematically divergent semantics: only three fault-type codes (01, 05, 16) co-occur across the sheets; a single code pools 155 fault segments mixing 34 reverse, 3 thrust and 3 normal segments of locally defensible evidence; annotation categories follow three different label systems; one dip-direction field is populated in 0%, 34 and 10 segments respectively; and a fault attitude exists at all only as the spatial coupling of three cartographic elements (a dip-direction arrow, paired hanging-wall ticks, and a dip annotation). We organize this divergence into a six-type taxonomy of semantic looseness (Table 1), from sheet-private vocabularies to spatially coupled meaning.

**Table 1 | Six-type taxonomy of semantic looseness, with empirical evidence from three 1:250,000 sheets.**

| # | Looseness type | Evidence | Structural consequence |
|---|---|---|---|
| L1 | Code-surface uniform, meaning sheet-private | Only three fault-type codes (01/05/16) co-occur across the sheets | Code meanings must be re-discovered per sheet |
| L2 | One code, many meanings | Code 01 pools 155 segments with 34 reverse / 3 thrust / 3 normal decisive segments | A single code meaning forces either flattening or misjudgment |
| L3 | Three label systems | Annotation categories (fault auxiliaries, attitudes, notes) named differently per sheet | Cross-sheet criteria are not directly inheritable |
| L4 | Same-slot mixing, variant glyphs | Axis-plane dip as text ("南倾") and angle ("225"); "360-180"; Cyrillic г for γ | Needs normalization channels |
| L5 | Completeness gradients | Dip-direction field: 0 / 34 / 10 non-empty values | Criterion applicability must be checked first |
| L6 | Meaning only in spatial coupling | An attitude exists as arrow + tick pair + annotation coupled in space | Semantics must be constructed from topology |


Prior work does not cover this class. Legacy-data rescue confronts archives without specifications; schema matching maps between two formal specifications; map quality assurance validates geometry and topology but not meaning. GeoSciML interoperability has been addressed conceptually (Xu et al., 2020) and at platform scale by CGS/DDE for 1:500,000–1:1,000,000 compilations, while format-level reading is handled by dedicated libraries (mapgis2shp, in review). What remains open is field-level semantic recovery when the specification is uniform, practice diverges, and the codebook is missing — and when the source data must not be rewritten.

We therefore ask: can geological semantics be calibrated from the data structure itself? We answer with a framework built on four postulates: ontological layering (structure, activity and evidence axes are calibrated independently), statistical hierarchy (segment-level evidence aggregates to code-level semantics, which inherit back to all same-code elements), topology-as-observation (prior knowledge drives five families of topological measurements), and falsification preservation (contradictions are registered for adjudication, never auto-corrected). The codebook is optimized by minimizing a conflict cost with an anti-degeneracy flattening penalty, and adjudication proceeds through editable mapping tables with deterministic replay. We validate on the three sheets, including a bare cold-start onboarding of one sheet with no prior artifacts. The remainder of the paper presents the model (Section 2), the pipeline realization (Section 3), validation and calibration-debt dynamics (Section 4), and the applicability boundary (Section 5).

*(Chinese note: 引言四段各司其职——领域利害（729 幅存量）→现象收窄（六型松散，每型带实证数字）→文献合成（三类漏区+对齐互补定位）→问题与贡献（四公设预览+路线句）。变体=novel-task-challenge-decomposition：第三段末把问题类钉死为「规范统一×实践分化×词典缺位」。)*

## Assumptions or missing inputs

- [x] 作者署名/单位（参考 mapgis2shp 投稿件：7 作者+西安矿产资源调查中心；∗/† 标记待与在审稿对齐确认）
- Keywords 五词待定（投稿时补）
- E6 置信度校准曲线：裁定集维持率完整版留修订轮（§4.8 已声明）
- 图件已出四张（fig1–fig4，SVG+PDF 双格式）；Table 1/2/3 已在正文引用位

## Claim-evidence map

- **Claim**: 问题类存在且被三类文献漏掉 | Evidence: 六型三幅实证 + 文献事实核查 | supported
- **Claim**: 语义可经拓扑测量标定 | Evidence: 五算子族 + 三幅全链 29 断言×2 | supported（设计层）
- **Claim**: 码书可经矛盾最小化优化 | Evidence: J=K+λF 形式化 + 横幅时序收敛 | supported（模型层），E5 成图后实证层
- **Claim**: 框架可冷启动泛化 | Evidence: 裸幅接入全绿 | supported（1 幅——Discussion 须诚实标 "one sheet"）
- **Claim**: 回路可复现 | Evidence: 编辑-回退逐字节 | supported

## Why this structure

- 问题类先于系统——防桌拒的第一段必须是问题（六型松散）而非管线
- 摘要五段运动，两个数字都直接服务主 claim，不堆实验清单
- 引言每段一职，第三段把缺口定义为「未知/未解」而非「作者方法缺席」
- 动词校准：demonstrate 仅用于断言网/回归实证处；泛化 claim 用 suggest 级

## To redirect me

指出某段/某句/某个数字不对，我只改那一处；或指定下一节（2 Model / 3 Pipeline / 4 Validation）我继续。

---

## 2. Model

### 2.1 Problem formulation

Let $\mathcal{S}$ be the set of fault segments in a sheet ($|\mathcal{S}|$ = 310, 289, 341 for the three study sheets), $\mathcal{C}$ the set of fault-type codes used in it, and $g:\mathcal{S}\to\mathcal{C}$ the coding assignment fixed by the original mappers, which we never modify. The vocabulary $\Sigma$ comprises decisive semantics $\Sigma_d$ (normal, reverse, thrust-boundary, strike-slip sinistral/dextral, active, compound, boundary fault) plus a null semantics $\sigma_\varnothing$ (general fault) and an evidence-axis class (inferred). The estimand is the codebook $\boldsymbol{\theta}=(\theta_c)_{c\in\mathcal{C}_u}$, one semantic assignment per unregistered code; registered codes are pinned (Section 2.5, constraint C1). Prior knowledge $\mathcal{P}$ comprises a contact-priors library, a stratigraphic age-rank table, a per-sheet registry of adjudicated semantics, and an override base of segment-level adjudications.

### 2.2 Observation model: topology as measurement

Codes are labels to be calibrated, not evidence. Evidence is produced by measuring the data structure against prior knowledge through five operator families:

- **Probes** $\mathcal{T}_{\rm probe}(s,\delta{=}100\,\text{m})\mapsto(u_L,u_R)$: the stratigraphic units on both sides of a segment, from which age-rank order (old-over-young) and repetition patterns are read;
- **Coincidence** $\mathcal{C}(s,U)=|s\cap\partial U|/|s|$: the fraction of a segment running along the boundary of Quaternary cover;
- **Containment** $\mathcal{I}(s,U)=|s\cap U|/|s|$: the fraction inside Quaternary or ice cover;
- **Proximity** $\mathcal{N}(p,\Gamma)\mapsto(s^*,s_{\rm arc},d_\perp,{\rm side})$: attribution of auxiliary points to fault entity chains with calibrated distance bands;
- **Pairing** $\Pi$: minimum-total-distance 1:1 assignment between dip arrows and dip annotations, and group formation for hanging-wall tick pairs (a–b–a triplets) and strike-slip hook pairs.

Measurement is hypothesis-driven: the prior library determines which operators exist at all. Without a contact-priors table there is no probe worth making; without symbol semantics there is no pairing operator.

### 2.3 Segment level: evidence aggregation

Channel $k$ contributes evidence $v_k(s,\sigma)\ge 0$ toward semantics $\sigma$ with adjudicated weight $w_k$ (registry prior 3, fault name 2, signature 2, kinematics 2, auxiliary points 2, cover 2–3, dip domain 1). Segment-level semantics are

$$\hat\sigma_1(s)=\arg\max_\sigma V(s,\sigma)\quad\text{whenever }V\ge\theta_{\min},\qquad \sigma_\varnothing\ \text{otherwise}.$$

Decisive channels bypass aggregation: an old-over-young probe result ($\operatorname{rank}(u_{hw})<\operatorname{rank}(u_{fw})$) assigns thrust boundary directly. We stress that this aggregation is a deterministic scoring rule, not a likelihood; the weights are adjudicated constants whose sensitivity we evaluate in Section 4.

### 2.4 Code level: hierarchical estimation

Segment results aggregate per code: $n(c,\sigma)=|\{s:g(s)=c,\hat\sigma_1(s)=\sigma\}|$. A code receives a family semantics only when a decisive semantics dominates at least $\theta_{\rm dom}=25\%$ of its segments:

$$\hat\sigma_2(c)=\arg\max_{\sigma\in\Sigma_d}n(c,\sigma)\quad\text{iff}\quad n(c,\sigma^*)\Big/\textstyle\sum_\tau n(c,\tau)\ge\theta_{\rm dom}.$$

Two structural rules encode domain knowledge. The single-code rule assigns reverse-fault semantics to at most one code per sheet ($c_{\rm rev}=\arg\max_c n(c,\text{reverse})$); and the reactivation signature assigns active-fault semantics where normal and reverse evidence coexist comparably ($n_{\rm rev}\ge3\wedge n_{\rm nor}\ge3\wedge\min/\max\ge0.5$). Sources combine by priority: adjudicated registry $\succ$ coverage signature $\succ$ aggregation. A code with no decisive family receives the null semantics $\sigma_\varnothing$.

### 2.5 The objective: conflict minimization

The essential process is optimizing the codebook against the conflict register. Writing $\operatorname{conflict}(s)=\{e\in E(s):e\notin\operatorname{EXPECT}(\sigma_{\rm final}(s))\}$ for the evidence items of segment $s$ that violate the expectations of its final semantics, the codebook minimizes

$$J(\boldsymbol\theta)=\underbrace{\sum_{s\notin S_{\rm adj}}\bigl|\operatorname{conflict}\bigl(s\mid\theta_{g(s)}\bigr)\bigr|}_{K(\boldsymbol\theta)\ \text{registered violations}}\;+\;\lambda\underbrace{\sum_{c}\sum_{\sigma\in\Sigma_d}n(c,\sigma)\,\mathbb 1[\theta_c\ne\sigma]}_{F(\boldsymbol\theta)\ \text{flattening penalty}}\quad\text{s.t. C1–C3},$$

with C1 pinning adjudicated codes, C2 the single-code rule, and C3 feasibility ($\sigma_\varnothing$ always admissible). The flattening term is what makes the problem well-posed: because the null semantics has empty expectations, $K$ alone is trivially minimized by assigning $\sigma_\varnothing$ everywhere; $F$ charges for suppressed decisive evidence. Two cases from the study sheets bracket the behaviour: for code 05 the flattening mass of 49 decisive segments keeps it reverse despite three registered violations, while for code 01 the violation count of a reverse assignment outweighs and the code stays at the null semantics. $\lambda$ is calibrated so that the rule reproduces the full adjudicated case set, then tightens as adjudication accumulates.

### 2.6 Deduction level: inheritance and the falsification operator

All same-code segments inherit the codebook semantics, $\sigma_{\rm final}(s)=\hat\sigma_2(g(s))$ for $s\notin S_{\rm adj}$; adjudicated segments are absolute. Expectation checks run only after inheritance, against the final semantics. Because $\operatorname{EXPECT}(\sigma_\varnothing)=\varnothing$, the null semantics is compatible with all segment-level evidence by construction — a model consequence, not an exemption rule: divergent evidence on a segment under a specific code semantics is registered (one entry per segment) and queued for expert adjudication, while the source data remain untouched.

### 2.7 Solving and reproducibility

The vocabulary $\Sigma$ is small and discrete, so per-code evaluation is exhaustive and the single-code constraint resolves by posterior ordering: no sampling, fully deterministic. Determinism is load-bearing for the adjudication loop: editing a mapping-table entry and replaying the calibration reproduces byte-identical outputs on revert, so expert edits are reversible experiments on the codebook.

### 2.8 Probabilistic extension

For unregistered codes, the aggregation can be upgraded to a constrained hierarchical Bayesian model in which channel confusion rates are estimated from the adjudicated case set, correlated channels are merged, and segment likelihoods are weighted by inverse entity size; the codebook posterior then calibrates the map table's confidence column. Registered codes never enter estimation. We treat this as an optional kernel: the deterministic skeleton above is the auditable reference implementation.

*(Chinese note: §2 按「问题形式化→观测模型→样本级→总体级→目标函数→演绎层→求解/复现→概率扩展」展开；设计理由（2.2 假设驱动、2.5 防退化）与评估（§4）分节不混；「评分器非似然」的诚实声明入 2.3 末句；贝叶斯压缩为可选内核一小节。）*

## Section-2 checklist

- 每个模块一职：观测（2.2）不混入判定（2.3–2.4），判定不混入目标（2.5），演绎不混入证伪（2.6）
- 所有常数标注「adjudicated」并指向 §4 灵敏度实验占位
- 无 bare numbers：310/289/341、25%、49、3 例均有出处
- 「确定性是裁定回路的承重墙」作为 2.7 的动机句

## To redirect me

对 §2 的哪一小节有异议指出即改；下一节可写 **3 Pipeline realization（八域定序+两相物化+守卫链）** 或 **4 Validation（E1–E6 结果框架+J 轨迹图位）**。

---

## 3. Pipeline realization

### 3.1 Overview

The framework is realized as an open-source Python package (`geosciml4china`) that takes a MapGIS project folder and produces GeoSciML 4.1 documents, lite GeoJSON views, and a rendered map, in six contracted stages: (0) an eleven-file completeness preflight with core/conditional grading; (1) conversion to L0 GeoJSON; (2) self-supporting semantic calibration across eight domains; (3) semantics-to-style generation; (4) GeoSciML build; (5) verification (XSD plus 29 domain assertions with per-sheet expectation profiles); (6) semantics-driven rendering with mirror checks against the L1 layer. Every stage fails fast; no stage proceeds on stale products.

### 3.2 Calibration domain sequence

Domain order encodes evidence dependencies rather than convention: boundary calibration (GZBD) runs first and produces the baseline L1 layer, because fault entity grouping and the auxiliary-point chain consume it; entity grouping precedes the auxiliary chain, whose verdicts feed fault calibration (GZEEB); the fault-contact activity audit runs after entity grouping because candidate attribution needs the entity table; attitudes, fossils, folds and inferred-fault coverage follow; a final materialization writes the terminal semantics back to L1. Two-phase materialization (baseline before entities, terminal after all domains) keeps each producer–consumer pair on fresh artifacts.

### 3.3 Guards

Three guards protect the pipeline against stale-state errors under iteration: (i) the contract preflight stops on missing core files; (ii) a freshness guard refuses to build when calibration artifacts are newer than the L1 layer; (iii) a staleness guard warns when a mapping table has been edited more recently than its calibration artifact, pointing at the exact domain command to re-run. The mapping-table guard is what makes the edit–reconvert loop safe in daily use.

### 3.4 The adjudication workbench

Calibration gaps are converted into an adjudication queue rather than hidden: a gap report assembles, per unresolved item, a one-element render card plus its textual evidence (boundary gap candidates, boundary divergences, fault conflicts, fallback archives). Experts adjudicate by editing the mapping tables (`user_semantic` column) or the override base; a single command replays calibration deterministically, and a skip-mode pipeline re-materializes, rebuilds, verifies and re-renders. The loop is the paper's central workflow artifact: it makes human judgment a versioned, replayable input rather than an undocumented intervention.

### 3.5 Semantic emission

Downstream of calibration, no normative slot consumes MapGIS codes directly: the GeoSciML `faultType` and `contactType` are resolved from the final calibrated semantics (thrust boundary → `thrust_fault`, conformable contact → `conformable_contact`, and so on), lite views carry `structural_type` and `sem_label`, and the render engine styles by inherited semantics alone. Semantic decoupling is enforced by mirror assertions (C1–C7) comparing the rendered map against the L1 layer element-by-element.

*(Chinese note: §3 按 algorithmic 链「系统是什么」单写——机制与理由分开；3.2 域序写成证据依赖而非惯例；3.4 裁定工作台=人机接口的中心工件；3.5 语义解耦以镜像断言收束。)*

## Section-3 checklist

- 六步契约→八域定序→守卫链→工作台→语义出站，每节一职
- 「确定性=可逆实验」与 §2.7 呼应不重复（§2 讲模型求解，本节讲工程回路）
- 无性能数字混入（留给 §4）

## To redirect me

§3 哪节要改指出即改；下一节写 **4 Validation**（E1 基线对照 + 三幅标定结果 + J 下降轨迹 + 编辑-回退回归 + 冷启动案例 + E2–E6 占位框架）。

---

## 4. Validation

### 4.1 Setup and verification harness

We validate on three 1:250,000 sheets — Kurgan (J43C001002), Yingjisha (J43C002003) and Aoyiyayilake (J45C004001) — comprising 310, 289 and 341 fault segments (Kurgan, Yingjisha, Aoyiyayilake), 1,318 and 1,199 emitted contact segments (Kurgan, Yingjisha), and 713 and 808 geologic-unit polygons (Kurgan, Yingjisha). Every run passes a fixed harness: XSD validation against the GeoSciML schemas, 29 domain assertions (A01–A27, including element counts, identifier integrity, measurement-point geometry and conflict-banner baselines), and seven mirror checks (C1–C7) between the rendered map and the semantic layer.

### 4.2 Baseline: code-literal reading versus calibration

Reading codes literally — mapping each MapGIS code to its nominal meaning — is the only available baseline, as no prior method addresses this problem class. Against it, calibration resolves sheet-private codes into evidence-backed semantics (Table 2). On the bare-onboarded Kurgan sheet, whose registry held a single adjudicated code, code-literal reading assigns every fault segment the generic `fault`; calibration moves 63 of 310 segments to specific CGI fault types (49 reverse, 10 thrust, 4 strike-slip). On the partly adjudicated Yingjisha sheet, specific assignments rise from 123 to 126 of 289. Contact types resolve from 78.9% to 94.0% of 1,318 segments on Kurgan and from 66.2% to 84.0% of 1,199 on Yingjisha (nil terms drop 278 → 80 and 405 → 192).

**Table 2 | Code-literal baseline versus three-level calibration.**

| Metric | Kurgan, literal | Kurgan, calibrated | Yingjisha, literal | Yingjisha, calibrated |
|---|---|---|---|---|
| Segments with specific faultType | 0/310 (0%) | **63/310 (20.3%)** | 123/289 (42.6%) | **126/289 (43.6%)** |
| Contacts with resolved contactType | 1,040/1,318 (78.9%) | **1,238/1,318 (94.0%)** | 794/1,199 (66.2%) | **1,007/1,199 (84.0%)** |

### 4.3 Codebook outcomes

The calibration produces, per sheet, a complete code-to-semantics mapping table with per-code evidence distributions and confidence grades. Across sheets, only three codes (01, 05, 16) share meanings — the anchor codes; all others are sheet-specific and are resolved per sheet. Strong-evidence codes (reverse fault: 49 segments, 94% decisive) and thin-evidence codes (dextral strike-slip: one segment) are distinguished explicitly in the table rather than presented with equal authority.

### 4.4 Convergence dynamics

The conflict register is the objective's observable. Its versioned trajectory is honest about non-monotonicity (Fig. 3). On Yingjisha the banner count first rose from 96 to 140 as the falsification machinery became more complete (post-inheritance expectation checks surface tensions that segment-level self-evidence had masked), then fell to 7 when the three-level logic went into force. Each stage corresponds to a committed pipeline state, so every point of the trajectory is recomputable. On Kurgan, onboarded after the framework was finalized, the register starts and stays at 22 — a sheet with no calibration debt accumulated under superseded machinery. The register thus measures both machinery completeness and adjudication progress: rises mark stronger falsification, falls mark resolved debt.

**Figure 3 (to produce) | Conflict-register trajectory.** Stage-labelled banner counts for Yingjisha (96 → 136 → 140 → 7, four committed pipeline stages annotated with the machinery change responsible for each step) and the flat count for Kurgan (22 throughout, onboarded after framework finalization).

### 4.5 Reproducibility and the adjudication loop

Calibration is deterministic: identical inputs reproduce byte-identical artifacts, and a controlled experiment — editing one codebook entry (right-lateral strike-slip → normal fault on a one-segment code), replaying calibration, then reverting — restores byte-identical state while the edited run shows the expected inheritance, registration and conflict-merge consequences. Human input enters only through versioned, replayable edits; no state is modified by hand.

### 4.6 Cold-start generalization

One sheet (Kurgan copy) was onboarded bare — no profiles, priors, or artifacts from the other projects — and reached the full green harness with all nine code-level semantics resolved by the evidence-aggregation channel alone (zero registered priors). This demonstrates cold-start behaviour; generalization to genuinely unseen sheets remains to be tested on the national stock (Section 5). *We report one sheet; we do not claim broad generalization.*

### 4.7 Failure modes and the flattening cost

The framework reports its own failure modes through the flattening penalty. Under polysemous codes (Kurgan code 01: 155 segments pooling 34 reverse, 3 thrust and 3 normal segments), inheritance to the null semantics suppresses locally defensible classifications; the suppressed mass (41 segments) is reported in the mapping table as an explicit cost rather than hidden. Dip-domain conflicts absorbed by the null semantics (steep-dip thrust candidates at 50° and 78°) are preserved in the evidence columns for later adjudication. Thin-evidence codes (one to three segments) remain at unadjudicated (aggregation-derived) status with low confidence grades, queued for expert adjudication via single-element render cards.

### 4.8 Sensitivity and ablation

**Channel ablation (E2).** We disabled each of the ten evidence channels in turn (registry prior, fault name, coverage signature, kinematics, dip domain, auxiliary points, cover, Quaternary-boundary coincidence, old-over-young probe, strike-slip hooks) and replayed calibration deterministically (Table 3). Nine of ten channels show zero code-level flips on both sheets — segment-level evidence is redundantly covered, so no single channel is load-bearing except one. Disabling the auxiliary-point channel on Kurgan flips code 31 from active fault to the null semantics, flipping all 26 of its segments. That code's active assignment rests on the reactivation signature, whose normal- and reverse-fault votes both come from the auxiliary chain — a single point of fragility that we report rather than hide, and that maps directly to an adjudication question (whether code 31's normal- and reverse-fault auxiliary evidence should be corroborated by an independent channel before its active assignment is registered).

**Table 3 | Ablation and sensitivity: code-level flips under perturbation.**

| Perturbation | Kurgan | Yingjisha |
|---|---|---|
| E2 channel ablation — 9 of 10 channels | 0/9 codes | 0/7 codes |
| E2 channel ablation — auxiliary points | **1/9 (code 31: active → null; 26/310 segs)** | 0/7 |
| E3 dominance threshold 0.25→0.3125 | **1/9 (code 07: thrust → null)** | 0/7 |
| E3 dominance threshold 0.25→0.1875 | 0/9 | 0/7 |
| E3 reactivation ratio / counts (±25%) | 0/9 | 0/7 |
| E3 minimum-vote floor 2→2.5 | **1/9 (code 31: active → null)** | 0/7 |
| E3 minimum-vote floor 2→1.5 | 0/9 | 0/7 |
| E4 entity-size vote weighting | **2/9 (31: active → null; 41: null → reverse)** | 0/7 |

Three perturbational modes point at the same code. Code 31's active-fault assignment fails under three independent perturbations — auxiliary-channel ablation, a raised minimum-vote floor (its segment votes sit exactly at +2), and entity-size weighting (its decisive votes concentrate in few multi-segment entities). Code 07's thrust assignment sits marginally above the dominance threshold (3/10 decisive segments = 30%) and falls when the threshold rises 25%. Every other code, and all of Yingjisha, is invariant across the whole perturbation battery. The register of these failure points is itself part of the method: each maps to a concrete adjudication question rather than a silent assumption.

E6 (confidence calibration: S×I×F scores versus adjudication-upheld rates) uses the adjudicated case set and is deferred to the revision cycle, together with the full calibration curve.

*(Chinese note: §4 按「实验设置→基线→结果→收敛→复现→泛化→失败模式→消融协议」展开；4.4 把非单调性写成机制完备性的证据而非掩盖（96→140 上升段如实呈现）；4.6 自限 "one sheet"；4.7/4.8 全部占位纪律，未跑实验零虚构。)*

## Section-4 checklist

- 基线=唯一存在的对照（码面直读），数字全部有出处
- 非单调收敛如实（机制完备性↔裁定进度双读数）
- 失败模式小节在案（algorithmic 必查项）
- 未跑实验一律 [Evidence needed]，无一虚构

## To redirect me

§4 哪小节要改指出即改；下一节写 **5 Discussion + Conclusion**（适用边界/词表成熟度迁移判据/数据权属与可用性/局限收束/贡献回收）。

---

## 5. Discussion

### 5.1 Anchor

The central advance is a change of posture: geological semantics in legacy cartographic encodings need not be read from fields — they can be measured out of the data structure. Once prior knowledge drives topological measurement and conflicts become the observable of fit, the codebook itself becomes an estimable, editable, auditable object. On the three study sheets this recovered code-level semantics with no codebook, and compressed expert adjudication from hundreds of segments to a table of seven to nine rows per sheet.

### 5.2 Position

The work sits between three literature families, in the gap none of them covers: legacy-data rescue assumes no specification; schema matching assumes two formal ones; map quality assurance validates geometry, not meaning. Against GeoSciML interoperability studies (conceptual frameworks by Xu et al., 2020; platform-scale publication by CGS/DDE at 1:500,000–1:1,000,000), our contribution is complementary: field-level semantic fidelity at map-sheet scale, with an auditable mapping from national industry codes to CGI vocabularies — each mapping carrying its evidence chain. Format-level reading (mapgis2shp, in review) is a prerequisite we build on, not a competitor.

### 5.3 Interpretation and contribution

Three levels of claim follow. *Established*: the framework operates end-to-end on three sheets with fixed verification harnesses, and the six-type looseness taxonomy is empirically real. *Supported interpretation*: hierarchical inference is what makes segment-level noise survivable — a misattributed auxiliary point or a phantom probe that would corrupt per-element reading dies in code-level aggregation, which is why nine of ten channels are individually dispensable (Table 3); the null semantics, far from a defect, is the model's honest absorbing state for codes whose evidence does not support a family. *Open implication*: the vocabulary-maturity ladder (national-standard / sheet-private / compositional DSL) may serve as a transfer criterion for other encoded archives — petroleum logs, mineral exploration compilations, hydrological maps — where specification and practice diverge; we offer this as a hypothesis, not a result.

### 5.4 Boundaries

Five boundaries bound the claims. (i) The aggregation is a deterministic scoring rule with adjudicated weights, not a likelihood; confidence grades are triage aids, not calibrated probabilities — a hierarchical Bayesian kernel is specified but not yet estimated. (ii) Segment-level aggregation treats segments of one fault entity as independent; entity-size vote weighting changes two code assignments (Table 3), so the independence assumption is an active, measured sensitivity rather than a silent one. (iii) Thresholds are expert-adjudicated constants; their sensitivity is measured across ±25% perturbations (Table 3), and two marginal codes (07, 31) mark the regime where calibration should ask before trusting. (iv) Cold-start generalization is demonstrated on one sheet; transportability to genuinely unseen sheets requires a blind onboarding test. (v) Source-data ownership constrains what we can publish: we report statistics and local excerpts, and the full derived datasets await written authorization from the producing institutions. None of these threatens the within-design conclusions; each bounds a specific transportability claim.

### 5.5 Next steps

Two discriminating steps follow from named uncertainties. First, the confidence-calibration curve remains open: rating S×I×F scores against adjudication-upheld rates on the adjudicated case set would convert the confidence column from a triage aid into a calibrated probability, closing the loop opened by the measured sensitivity profile of Table 3. Second, a blind onboarding of one genuinely unseen sheet from the national 729-sheet stock would test the transportability claim directly: the pre-registered protocol (frozen constants, masked leakage entries, bare-project rules) turns the exercise into a measurement of cold-start adjudication cost.

### 5.6 Conclusion

Legacy cartographic encodings preserve geology as drawing instructions. We have shown that their semantics can nonetheless be recovered: measured through topology, aggregated through hierarchy, and corrected through a falsification register whose minimization is the codebook's objective. The framework renders such archives machine-reasoning-ready without touching the source data, and converts an invisible calibration debt into an explicit, adjudicable queue — for the 729 sheets of China's 1:250,000 programme, and for comparable archives elsewhere.

*(Chinese note: §5 走反向漏斗——锚定（姿态转变：语义靠测量不靠读）→定位（三类文献漏区+对齐互补，不复读 Results 数字）→三层贡献（确立/支持性解释/开放推论逐级降模态）→五条边界每条指明"威胁哪个 claim 的哪个可迁移性"→两个判别性下一步（非购物清单）→收束句回扣 729 幅。)*

## Section-5 checklist

- 反向漏斗方向正确；锚定句有界
- 定位每处引用都说明关系（互补/划界/前置），非装饰性引用簇
- 三层贡献分离：established/supported/open 各归其级
- 局限=claim 边界（每条含"威胁什么+什么仍成立+消解测试"）
- 未来工作两条均解具名不确定性；无 "more data needed" 式空话
- 模态动词经校准表逐项过检（demonstrates 仅见于工装实证处）

## Manuscript status

- [x] Title candidates / Abstract / 1 Introduction / 2 Model / 3 Pipeline / 4 Validation / 5 Discussion+Conclusion
- [ ] References（文献综述扩写：schema matching/遗产救援/地图 QA 具体文献）
- [ ] Figures 1–4（问题类对照/管线/J 轨迹/编辑-回放）
- [ ] E1–E6 实验计算与回填
- [ ] Data availability + author info + AI 披露
- [ ] 期刊 author guide 核对（C&G）

## To redirect me

全文骨架已闭合。下一步任选：① E1+E5 实验先算（摘要数字落地）；② 图件 1–4 制作；③ References 扩写；④ 中文 D 稿骨架；⑤ 全文一致性/冗余终检。

---

## Figure legends (draft)

**Fig. 1 | Empirical evidence for six-type semantic looseness across three 1:250,000 sheets.** a, Code values of the fault-type field (GZEEB) per sheet; anchor codes 01/05/16 shared across sheets are blue, sheet-private codes grey. b, Decisive segment-level evidence pooled inside code 01 on one sheet (155 segments): reverse (n=34), thrust (n=3), normal (n=3), inferred (n=1); the remainder carry no decisive evidence. c, The three label systems of the annotation layer: category names differ while meanings overlap. d, Same-slot mixing and variant glyphs: axis-plane dip recorded as both text ("南倾") and angle ("225") within one field; a dip-direction value "360-180"; Cyrillic г used for γ and a mathematical ∑ variant in unit codes. e, Completeness gradients: non-empty values for dip direction (GZECD) and activity text (GZEHH) across sheets. f, An attitude exists only as the spatial coupling of three cartographic elements — a dip-direction arrow (1894), paired hanging-wall ticks (1281 pair), and a dip annotation (text); no single field states the attitude.

**Fig. 2 | Pipeline architecture.** Six contracted stages (⓪ preflight, ① convert, ② calibrate, ③ stylegen, ④ build, ⑤ verify, ⑥ render) with eight evidence-ordered calibration domains inside stage ②. The golden band marks the three inference levels: L1 segment-level evidence aggregation with topological operators, L2 codebook estimation (MLE aggregation, registry, mapping table), L3 inheritance to all same-code segments; the falsification register (J = K + λF) closes the loop. Dashed boxes mark the three guards (preflight, build freshness, mapping-table staleness) and the adjudication loop.

**Fig. 3 | Conflict-register trajectory.** Registered conflict banners (the A23 baseline) for Yingjisha across four committed pipeline stages: S1 (boundary/nappe/hook evidence added to aggregation), S2 (semantic decoupling of emission), S3 (dip-side channel and code-semantics unification), S4 (three-level logic with inheritance and deferred checks). Kurgan, onboarded after framework finalization, registers 22 throughout — no debt accumulated under superseded machinery. Every point is recomputable from the committed pipeline state.

**Fig. 4 | The adjudication loop.** An editable mapping table (per-code semantic, user_semantic, confidence) is replayed deterministically through calibration and the skip-mode pipeline (materialize → build → verify → render). The red arc marks the revert path: clearing the edit and replaying restores byte-identical state, so human input enters only through versioned, replayable edits. The conflict register is the objective observable; each adjudication is a descent step on J = K + λF.

## Full-draft consistency check (⓪–⑥)

- [x] 数字一致性：摘要/§4.2/§4.4 与 git 可证事实对齐（63/310、126/289、nil 80/192、轨迹 96→136→140→7、22 平线）
- [x] 术语一致：codebook/evidence aggregation/falsification register/null semantics 全文锁定（Terminology Ledger §8）
- [x] 图件↔正文：Fig1↔§1 六型、Fig2↔§3、Fig3↔§4.4、Fig4↔§4.5/§3.4 一一对应
- [ ] References 列表（骨架四条已核事实在 prospects 文档，待扩展入稿）
- [x] Table 1（六型松散）Table 2（基线对照）Table 3（消融灵敏度）均入正文引用位
- [x] 数据/代码可用性声明 + AI 披露 + 竞争利益 + C&G author guide 清单
- [x] AI 辅助披露段
- [ ] 期刊 author guide 核对（C&G 字数/摘要格式）

## To redirect me

图注四件已入稿。下一步任选：③ References 扩写（schema matching/遗产救援/地图 QA 文献调研）；④ 中文 D 稿骨架；⑥ E2 通道消融实验（最后一个硬实验占位）。

---

## Data and code availability

The three study sheets are 1:250,000 regional geological survey products held under the Chinese geological survey data-management regime. This paper reports aggregate statistics and local map excerpts only; the full derived datasets (calibrated codebooks, L1 semantic layers, GeoSciML documents) await written authorization from the producing institutions, after which they will be deposited in a public repository. All software is open source at https://github.com/leecugb/geosciml4china and https://github.com/leecugb/mapgis2shp; the calibration pipeline, mapping tables, ablation hooks and replay drivers used in this study are in the repository, and every reported number is recomputable by replaying the committed pipeline state.

## AI-assistance disclosure

Language drafting and figure-script preparation were assisted by large language models under human author verification; all scientific claims, calibration rulings, experimental results and code were authored and verified by the human authors, who take full responsibility for the contents. No AI-generated data or references appear in this manuscript.

## Competing interests

The authors declare no competing interests.

## Author guide checklist (Computers & Geosciences, verified 2026-10-08)

- [x] Abstract ≤300 words, single paragraph, no references (current draft ≈200 words)
- [x] Research article ≤5,000 words (current draft ≈4,700 words incl. legends)
- [ ] Five keywords (to add at submission)
- [x] Author–date (APA-style) references, alphabetical (working list follows this)
- [x] Numbered sections; single-column double-spaced at revision stage
- [x] Code availability section (above)
- [x] Data availability statement (above)
- [x] Highlights bullet list (to draft at submission)
- [x] CRediT statement (single-author or as agreed)
- [ ] Graphical abstract (optional — reuse Fig. 2 at submission)
- [ ] Cover letter (to draft)

## References (working list — three lines + prior-verified anchors)

**Schema matching**

1. Rahm, E., Bernstein, P.A. (2001). A survey of approaches to automatic schema matching. *The VLDB Journal* 10(4), 334–350. — assumes two formal specifications to align; the codebook-missing case is outside its problem statement. [verified via search]
2. Madhavan, J., Bernstein, P.A., Rahm, E. (2001). Generic schema matching with Cupid. *Proc. VLDB 2001*. [verified via search, cited via ref. 1]

**Legacy data rescue (geological)**

3. Hatcher, R.D. (2005). Non-Survey, Non-Digital Completed Geologic Maps in File Drawers and Theses: How Can They Be Transformed into Useful Available Digital Maps? *USGS Open-File Report 2005-1428*. — digitizes paper maps by recompiling contacts/structures in georegistered vector files; no semantic calibration of coded fields. [verified via search]
4. Jackson, I. (2010). Acting Locally, Thinking Globally: One Geology? *Eos* 91(5). — OneGeology positions semantic interoperability (harmonized terminology) as the remaining long-term challenge after structural interoperability. [verified via search]
5. Jackson, I. (2011). OneGeology — from concept to global project. In *Geoinformatics: Cyberinfrastructure for the Solid Earth Sciences*, Cambridge University Press. [verified via search]

**Spatial data quality / map QA**

6. Goodchild, M.F., Gopal, S. (eds.) (1989). *Accuracy of Spatial Databases*. Taylor & Francis. — geometry- and topology-centric QA tradition. [verified via search]
7. Shi, W., Fisher, P.F., Goodchild, M.F. (eds.) (2002). *Spatial Data Quality*. Taylor & Francis. [verified via search]
8. Devillers, R., Goodchild, H. (2010). *Spatial Data Quality: From Process to Decisions*. CRC Press. [verified via search]

**GeoSciML / CGI interoperability (prior-verified anchors)**

9. Sen, M., Duffy, T. (2005). GeoSciML: development of a generic GeoScience Markup Language. *Computers & Geosciences* 31(9), 1095–1103. [verified in prior audit]
10. Xu, Y. et al. (2020). [地质学刊 interoperability framework, 44(4):337–344]. [verified in prior audit]
11. CGI Annual Reports 2019, 2024 — CGS/DDE platform-scale GeoSciML publication at 1:500,000–1:1,000,000. [verified in prior audit]

**China 1:250,000 database**

12. Zuo, Q. et al. (2018). [全国 1:25 万区域地质调查数据库与成矿地质背景数据模型, 中国地质 45(S1)]. — the nominal specification layer whose uniform presence contrasts with sheet-level practice. [verified in prior audit]

**In-review companion**

13. mapgis2shp software manuscript (in review, Research Square rs-10447341). — format reading and geometric fidelity; prerequisite to, not overlapping with, the present semantic calibration. [verified in prior audit]

*Note: items 1–8 were existence-verified by search on 2026-10-08; page numbers for book chapters and the exact Chinese-journal details of items 10 and 12 carry [verify at proof] tags — final citation formatting per the target journal's reference style at submission.*

## Related-work paragraph map (for §1.3, one paragraph per family)

- **Schema matching** (refs 1–2): aligns two formal schemas via similarity measures — the codebook-missing, single-specification, practice-diverged case is not addressable by its input model.
- **Legacy rescue** (refs 3–5): digitizes and georeferences paper archives; semantic harmonization is named as the open problem (Jackson 2010) but not solved at field level.
- **Map QA** (refs 6–8): quantifies positional/attribute error against ground truth; does not recover meaning when the legend itself is ambiguous.
- **Interoperability** (refs 9–11): establishes the target standard; Chinese practice at platform scale leaves sheet-level fidelity open.
- **Our position**: the gap is the intersection — uniform specification, divergent practice, missing codebook — which none of the families states as its problem.

---

## Nature-writing audit report (2026-10-08)

### 已修 12 项（动词校准 5 + 过时回写 7）

| # | 类型 | 原文 | 修订 |
|---|---|---|---|
| A1 | 绝对化 | no attribute field states what a fault is | **directly** states（防 GZEAB 反例） |
| A2 | must 滥用 | these archives must be converted | are being converted |
| A3 | must 滥用 | A single code meaning must flatten or misjudge | forces either… |
| A4 | 绝对化×实现不符 | nothing consumes MapGIS codes | no normative slot consumes… directly（图幅级映射文件在场时码查表契约保留） |
| A5 | 非正式 | keeps the pipeline honest | protect… against stale-state errors |
| B1 | 过时（E3 已算） | sensitivity is computable but not yet computed | measured across ±25% (Table 3) + 边际码 07/31 标注 |
| B2 | 过时（E4 已算） | entity-cluster weighting is evaluated in the ablation protocol | 已测（Table 3，两码翻转）并升格为 active sensitivity |
| B3 | 过时（E2–E4 已算） | Next steps 第一条再列消融套件 | 改写为 E6 校准曲线（唯一未做项） |
| B4 | 术语违反 | maximum-likelihood channel | evidence-aggregation channel（Ledger 锁定） |
| B5 | 术语违反 | MLE status | unadjudicated (aggregation-derived) status |
| B6 | 数字歧义 | 三列数字错位 | 三幅/两幅分开表述 |
| B7 | 与 §4.8 措辞冲突 | misattributed auxiliary points… die in aggregation | 加 segment-level 限定 + 扣 Table 3（九通道可缺） |

### 判定保留（审计过但不动）

- 4.6 "This demonstrates cold-start behaviour"——有全绿工装设计支撑+紧随自限句，demonstrates 合格；
- 5.2 "in the gap none of them covers"——三类漏区已在 §1 论证，none 有据；
- 摘要四数字串——均为 decisive support，C&G 方法类摘要惯例可容纳；
- 5.3 "die in code-level aggregation" 与 31 码脆弱性——修 B7 后两者分属段级/码级，不矛盾。

### Claim-evidence 复核（修订后）

- 全部 claim 仍有支撑；B 批修订只改措辞与时效，未动任何数字；
- E2–E4 结果现已在 §4.8/§5.4/§5.5 三处一致引用，无"未算"残留。

### 段落流

- §4.2/§4.4/§5.2 首句均为主题句，单段单职保持；
- 反向漏斗方向（§5 具体→整合→定位→贡献→边界→下一步）未被打断。

### 剩余风险（投稿前过一眼）

- Keywords 五词、Highlights、Cover letter 待提交日补；
- Graphical abstract（可选）复用 Fig. 2；
- 与在审 mapgis2shp 稿的作者序/∗† 标记对齐确认；
- E6 校准曲线挂修订轮（§4.8 已声明）。
