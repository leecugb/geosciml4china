# geosciml4china 界线语义标定 · 地质接触关系先验知识使用审计

**日期**：2026-09-29　**审计问题**：geosciml4china 对地质界线的地质语义标定是否使用地质接触关系先验知识？
**范围**：先验库→标定链→L1→geosciml4china 包（build/stylegen/render）全链 × 三幅（库尔干/英吉沙/奥依亚依拉克）

## 1. 先验知识架构（在案）

**载体**：`data/boundary_contact_priors.json`——《新疆区域界线接触关系先验库》（`_meta.title`：
"支持新疆各图幅转换渲染"，**区域级设计，非单幅私有**）。
- 内容：unit_pair_rules ×346（单元对接触关系，源=《新疆区域地质志》memoir/用户核验 adjudicated，含 region/page 溯源）、generic_rules ×6（如"任一侧第四系→第四系界线"，priority 分级）、age_order_priors（新老关系）、alias_map、gaps_pending、quaternary_exclude；
- **权威分级（2026-09-20 用户定）**：本库=接触关系+新老关系**双料最高知识源**（adjudicated 用户核验居首 > memoir 志书 > inferred > generic_rules > GZBD 兜底）；色库 `stratigraphic_contacts`/`group_composition` 两节=本库**派生镜像**（`_check_knowledge_sync.py` 一致性校验）。

**消费链**（先验 → 产品的完整路径）：
```
boundary_contact_priors.json
  ├─ _calibrate_gzbd.py（单元对规则双索引：名称对+码对；段级码结构解析）
  ├─ _audit_gzbd_pipeline.py（GZBD 码×两侧单元×先验规则 → verdict/GZBD_eff/年轻侧/置信度）
  ├─ _audit_gzeeb.py（断层域互证）/ _audit_map_coherence.py（图面一致性）
  ├─ _build_dzt0179_color_library.py（派生镜像同步）→ stylegen 组间分色消费
  └─ _audit_priors_integrity.py（先验库自体检校）
        ↓ 标定产物（_gzbd_semantic_interpretation.csv / gzbd_overrides.json / _gzbd_calibration_report.csv）
  materialize_sheet → geojson/L1/boundaries.geojson（GZBD_eff/sem_label/verdict/confidence 三列/younger_side/status）
        ↓ 包侧只消费
  geosciml4china：build（contacttype/relations）→ stylegen（色库镜像）→ render
```

## 2. 执行实况核验（量化）

### 库尔干（先验全量接入）— L1 界线 2222 段

| 指标 | 值 | 先验作用 |
|---|---|---|
| verdict 分布 | 标定通过 1129 / 断层标定 593 / 特殊码 315 / **未覆盖（先验缺口）123** / 用户裁定改码 61 / 制图误差剔除 1 | 先验驱动 verdict 分类；缺口如实登记 |
| **生效码≠原码** | **58 段** | 先验纠正原始编码（标定的核心产出） |
| younger_side 非空 | **1383 段** | 先验年轻侧方向证据（04/24 渲染与 relations 数据源） |
| conf_band | suspect 1118 / consistent 909 / unassessed 123 / verified 72 | S×I×F 框架在册 |
| GML 产品 | GeologicFeatureRelation **160 对**（A25 断言）+ contactType 分布与先验一致 | 先验知识进产品 |

### 英吉沙（先验全量接入）— 2541 段

标定通过 918 / 特殊码 735 / 断层标定 695 / 未覆盖 127 / 用户裁定 49；修正 36 段；younger_side 165；relations 23 对入 GML。

### 奥依亚依拉克（新幅首接基线）— 1538 段

verdict 全 None、younger_side 0、confidence 0.6 平铺——**先验未消费**（本幅未跑 gzbd 标定链）。基线=恒等生效码+词表转录 decided（带 transferred 注记+pending 裁定单 20 项）。

## 3. 包侧合规（铁律：只消费不重判）

**geosciml4china 包内对先验库直接消费 = 0**（全仓扫描证实）。包消费的边界语义全部来自 L1 标定列（GZBD_eff/sem_label/verdict/confidence/younger_side）与色库派生镜像（stylegen 组间分色的 order_records/group_composition）——即**先验知识经标定链与色库镜像两条合法通道进入产品，包本身不越权直读先验**。「管线只消费不重判」铁律在界线域严格执行。

## 4. 发现与处置建议

| # | 级别 | 发现 | 处置建议 |
|---|---|---|---|
| P-OK-1 | — | 库尔干/英吉沙界线标定充分使用先验（修正 58/36 段、年轻侧 1383/165、缺口如实登记 123/127、双料权威分级执行） | — |
| P-OK-2 | — | 包侧零直接先验消费；先验经 L1 标定列+色库镜像双通道合法入产品（relations 160/23 入 GML 有 A25 断言） | — |
| **P-GAP-1** | **中** | **新幅界线标定未消费先验**。先验库系区域级设计（generic_rules/age_order_priors 本幅即可用；unit_pair_rules 需本幅单元对扩展）。当前基线诚实（恒等+pending），但 493 段 02 的转录 decided **未经本幅先验佐证**（库尔干 02 的 945 段是先验核验定版的） | gzbd 标定链接入新幅：generic_rules 即开火（第四系通则验证 02×493/第四系单元接触）；unit_pair 未覆盖行登记入册；转录 decided 行升级为"先验互证"或打回 pending |
| P-GAP-2 | 轻 | 新幅界线 confidence=0.6 平铺（无标定行应为 unassessed）——与保真度审计 F2 联动 | 随 F2 处置一并修复 |
| P-NOTE-1 | 登记 | 先验库 unit_pair_rules 的 region 字段以库尔干/英吉沙区域为主；新幅（东昆仑/巴颜喀拉区）单元对覆盖率低属预期——缺口登记制（gaps_pending）同样适用于新幅 | 标定链运行时未覆盖对入 gaps_pending |

## 5. 结论

**库尔干/英吉沙：界线语义标定充分、正确地使用了地质接触关系先验知识**（最高知识源地位、verdict 分类、编码修正、年轻侧方向、置信度分级、缺口登记全链在案，产品侧 relations/渲染均兑现）。
**geosciml4china 包：架构合规**——包不直接消费先验，先验经标定链（L1 列）与色库镜像两通道进入产品，符合「只消费不重判」铁律。
**奥依亚依拉克：先验通道存在但未接入**（覆盖缺口 P-GAP-1，非违反）——基线诚实，转录语义待本幅先验佐证；gzbd 标定链接入是下一必然动作。

—— 审计执行：kimi-k3；证据可复算（本报告计数均可由 L1 geojson 直接复算）
