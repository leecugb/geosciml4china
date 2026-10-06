# 三接口契约审计（2026-10-07）

> 审计对象：geosciml4china 管线三接口（用户裁定 2026-10-06/07）——
> ① prepare：完整性检验 + 编码-地质语义标定 → codebook（JSON，用户可改）；
> ② convert：按 codebook 完成 MapGIS→GeoSciML，**GeoSciML 完全脱离 MapGIS 编码系统**；
> ③ render：渲染引擎**完全基于 GeoSciML 地质语义**，脱离 MapGIS 编码体系。
> 方法：接口逐条对账 + GML/lite 编码泄漏实测 + 渲染样式解析链审查。

## 一、接口一 prepare：符合

| 契约 | 实证 |
|------|------|
| 完整性检验 | ⓪ preflight 11 文件契约（CORE 缺即中止）——`preflight.py` |
| 编码-地质语义标定 | 九域全包原生（gzbd→entities→auxchain→fault_contact_activity→gzeeb→attitudes→fossils→folds→inferred_faults）+ 两相物化 + 缺口报告 |
| codebook 生成 | ②d 步产出 `codebook_<key>.json`（schema v1；四项目实测在盘） |
| JSON + 用户可改 | user_semantic/user_note 跨轮保留；`g4c codebook` 重生成；mtime 感知装载 |
| 说明 | codebook 以码为**键**是设计使然（它是被重建的词典——码是被定义的对象，不是下游携带的语义） |

## 二、接口二 convert：十月构建符合；九月 GML 属遗留（待重基线）

**实测：GML 标识 MapGIS 残留扫描**

| GML | OFBA/OFBB 图元 id 残留 | 判定 |
|-----|----------------------|------|
| kurgan_geosciml_full.gml（2026-09-29） | **3177 / 8513** | ✗ 遗留（语义 id 化 2026-10-02 裁定之前的构建） |
| y1_geosciml_full.gml（2026-10） | **0 / 8474** | ✓ 全语义 id（gu.C1w / sds.F065.1 / c.04.3 形态） |
| td_geosciml_full.gml（2026-10） | **0 / 1048** | ✓ 同上 |

**实测：lite 视图**

| 视图 | genericSymbolizer | 判定 |
|------|------------------|------|
| kurgan SDS（09-29） | '01','05','28','31'（MapGIS 码） | ✗ 遗留 |
| y1 SDS / td SDS（10月） | '断层泛称','逆断层','推覆体边界' | ✓ 纯地质语义 |
| y1 contact（10月） | '整合接触','角度不整合','第四系界线' | ✓ 纯地质语义 |
| 全部 lite（10月） | 无 FEATUREID 列；faultType/observationMethod（CGI 标准字段）实值在站 | ✓ |

**转换消费链**：L3 表驱动——build 经 codebook（注册表>用户编辑>全局先验>推导）解析码级语义，
GML 只出站 CGI 词表与地质语义（faultType/contactType/observationMethod），
单元代号（C1w/D2kz）为地层实体身份（地质内容，不属 MapGIS 属性编码系统）。

## 三、接口三 render：今日修复后符合；两处记录在案

| 契约点 | 实证 |
|--------|------|
| 断层样式解析 | **GeoSciML 原生链已立**：①structural_type（语义）→ ②faultType/observationMethod（CGI 标准字段，2026-10-06 修复）→ ③GZEEB（遗留回退，GeoSciML 帧无此列，实际不触发）→ ④默认。九月 GML 的推覆齿/推测虚线已正确渲染（F013 齿+虚线实证） |
| 面元/界线样式 | genericSymbolizer=语义名（十月 lite）→ stylegen 语义→样式单源；水系/冰雪经视图 role 分派 |
| 产状/测量点/钩线/矛盾叠加 | 数据全部来自 GML+lite（specification/DV/movementSense/矛盾横幅） |
| 记录在案 R1 | pdf_writer 保留 GZEEB 码级回退（`fault_types.get(type_val)`）——GeoSciML 帧无 GZEEB 列，该分支对 GeoSciML 渲染**不可达**，仅服务 legacy MapGIS 层；建议后续标注 deprecated |
| 记录在案 R2 | C1-C7 镜像核验以 L1（MapGIS 派生层）为对账基准——这是**验证旁路**而非渲染依赖；`--no-l1-check` 时渲染纯 GeoSciML 自足运行（kurgan 九月 GML 已实证） |

## 四、结论与遗留

**三接口契约成立**：接口一产 codebook（可改）→ 接口二以 codebook 为唯一语义基础转换，
十月 GML 全链路零 MapGIS 编码残留 → 接口三渲染解析链以 GeoSciML 标准字段为主键。

**遗留两项（均不阻塞契约，按纪律挂起）**：
1. 库尔干九月 GML 的 3177 个 OFBA 图元 id 与 lite 码值——属语义 id 化裁定前的构建，
   消除需 `g4c convert --sheet kurgan` 重建（**生产重基线，待用户批准**）；
2. pdf_writer 的 GZEEB 回退分支（对 GeoSciML 不可达）——建议代码标注 deprecated，不删（legacy 层仍用）。
