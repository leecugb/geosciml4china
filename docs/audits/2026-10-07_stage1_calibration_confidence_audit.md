# 一阶标定逻辑与置信度设计审计（2026-10-07）

> 对象：接口一（prepare）标定逻辑链 + 置信度设计（S×I×F 框架、codebook
> 置信度文件聚合口径）。方法：y1 全域标定件逐域实测 + 聚合逻辑审查。

## 一、标定逻辑链：成立

阶段序 `gzbd → 基线物化 → entities → auxchain → 写回 → fault_contact_activity
→ gzeeb → attitudes → fossils → folds → inferred → 终态物化 → gap → codebook →
confidence` 依赖正确：fault_contact_activity 置 entities 后（需 fault_entities
归因）、gzeeb 消费 aux 裁决、inferred 消费 gzeeb 的 04 候选、两相物化为实体/
辅助链供基线 L1。证据级别层实测/推测/部分覆盖十月纪元一致。

## 二、置信度设计：四项发现与处置

**F1 裁决词汇七分治，全局关键字匹配漏判（已修）**
各域词汇互不相同：界线=标定通过/断层标定/特殊码/未覆盖/分歧未裁定；
断层=consistent/verified/兜底/标定（活动先验）/标定（矛盾保留）；
产状=通过/裁定（Pt1 时代规则）/违反 R2'（待裁定）；褶皱=decided；
化石=verified/违反（待裁定）；辅助点（无 verdict 列）。
原 `_established_pct` 全局关键字（未覆盖/兜底/分歧/存疑）漏掉 attitudes/fossils
的「违反（待裁定）」→ 覆盖率虚高（attitudes 100%→99.7%、fossils 100%→97.9%）。
**处置**：分域规范分类器（pending_kw/fallback_kw 显式声明），
established/pending/fallback 三键出站。

**F2 verdict 与 conf_band 语义双轴（文档化+双轴出站）**
断层域 111 段 verdict=consistent 但 band=unassessed——verdict 答「语义能否继承」，
band 答「有无独立核验」：继承段（01 码全继承）语义成立但零核验。
非缺陷但易误读。**处置**：置信度文件新增 `band_consistent_pct`
（consistent+verified 占比）与 coverage_pct 并列——建立率与评价率双轴显形
（y1 faults：91.0% 建立 / 评价率另计）。

**F3 褶皱域置信带缺席=设计（显式标注）**
褶皱=词表码义标定域（2026-10-03 裁定：先验知识驱动、无段级证据通道），
conf_band/confidence 列按设计缺席。**处置**：folds 域标注
`mode: vocabulary_only` + 注记，替代空值。

**F4 辅助点域无裁决/置信聚合（已修）**
fault_aux_<key>.csv 只有 kind 计数；判别裁决在三联体件。
**处置**：聚合 `_fault_triplets_<key>.csv` 的 verdict（逆/正断层产状点/存疑）
与 form（a-b-a/a-b）分布入 aux_points.triplets。

**F5 界线特殊码独立标定**：315 段「特殊码（独立标定）」带 consistent 带
（码表独立标定，不参与地层接触先验）——口径正确，无处置。

## 三、优化后实机数字（y1）

| 域 | total | 建立率 | pending/队列 | 备注 |
|----|-------|--------|-------------|------|
| boundaries | 2222 | 91.8% | 59（分歧未裁定） | unsettled=182（含未覆盖 123） |
| faults | 310 | 91.0% | 3（矛盾保留） | fallback=25（兜底） |
| attitudes | 305 | **99.7%** | 1（违反 R2'） | 修正前虚报 100% |
| fossils | 48 | **97.9%** | 1（违反） | 修正前虚报 100% |
| folds | 4 | — | — | vocabulary_only（设计） |
| aux_points | 299 | — | — | triplets 逆 54/正 5 |
| polygons | 713 | — | — | 空码 1（剔除通道） |

## 四、遗留建议（不阻塞）

1. gzeeb 的「consistent×unassessed」继承段可考虑独立 verdict 词
   （如「继承（未评）」）——词汇层优化，涉及 gzeeb.py 改写，待裁定；
2. faults 的 conf_band 与 verdict 交叉表可入置信度文件（当前各列独立计数）；
3. aux verdict 通道（entities.aux_verdict）与 triplets 的统一视图。
