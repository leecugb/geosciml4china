# 三接口契约复审（2026-10-07 第二轮，GZBBGA 拟合落地后）

> 依据用户裁定原文复审：①接口一完整性检验+编码-地质语义标定→codebook
> （JSON 存映射表、允许用户修改）；②接口二按 codebook 转换、GeoSciML 完全
> 脱离 MapGIS 编码系统；③接口三渲染引擎完全基于 GeoSciML 地质语义、脱离
> MapGIS 编码体系。方法：当前 GML/lite/codebook 实测扫描 + 契约点逐项对账。

## 一、接口一 prepare：符合（本轮新增 GZBBGA 先验拟合）

| 契约点 | 实证 |
|--------|------|
| 完整性检验 | ⓪ preflight 11 文件契约（CORE 缺即中止） |
| 标定域 | 九域全包原生；**GZBBGA 已纳入先验拟合范畴**（宿主签名投票：registry/fitted/pending 三源；注册码零漂移；张力只登记不改码义） |
| codebook 生成 | `codebook_<key>.json`（schema v1，三族 GZEEB/GZBD/GZELD 在册） |
| 用户可改 | user_semantic/user_note 跨轮保留；`g4c codebook` 重生成 |
| 置信度与矛盾记录 | `codebook_confidence_<key>.json`：分域统计 + **逐段冲突明细**（segment_semantic 保持段级语义） |

## 二、接口二 convert：符合（全项目零编码残留）

**GML 标识扫描（当前态）**：

| 项目 | OFBA/OFBB 残留 | GZBBGA 码残留 | 判定 |
|------|---------------|--------------|------|
| y1 | 0 / 8474 | 0 | ✓ |
| y2 | 0 / 8157 | 0 | ✓ |
| y3 | 0 / 6562 | 0 | ✓ |
| td | 0 / 1048 | 0 | ✓ |

**lite 视图 genericSymbolizer（当前态）**：四项目三视图（SDS/Contact/SiteObs）
全为地质语义名（断层泛称/逆断层/整合接触/角度不整合/地层产状/片麻理产状），
无码值。Foliation 类型槽 = CGI foliationtype（bedding_fabric/schistosity/
foliation/gneissic_layering——宿主裁定分流精确落地）。转换严格按 codebook
（strict 模式，2026-10-07 拆盾后）：176 → conformable_contact。

## 三、接口三 render：符合

| 契约点 | 实证 |
|--------|------|
| 边界样式源 | **contactType 优先（接口二继承语义）**，sem_label 归一回退——176 按整合接触渲染；全图 0/1318 无样式键（归一扩展修复后） |
| 断层样式源 | structural_type（十月）/ **faultType + observationMethod（GeoSciML 原生通道，九月 GML 兼容）**：推覆齿/推测虚线/复活短线在任意纪元 GML 正确渲染 |
| 产状/测量点/叠加 | GML+lite 自足（specification/DV/movementSense/矛盾横幅/钩线） |
| GZEEB 码级回退 | 对 GeoSciML 帧不可达（记录在案，deprecated 候选） |

## 四、新发现 F-1（唯一未合项）

**GZBBGA 码级语义不在 codebook**：拟合标定产出 `code_sem`/`code_source`
存于 `_attitude_calibration.csv`，但 `codebook_<key>.json` 只有 GZEEB/GZBD/
GZELD 三族——「codebook 是转换唯一语义基础」原则对产状域**仅部分兑现**：
①接口二 Foliation 语义经 L1 sem_type 出站（正确，非 codebook）；
②用户想改 GZBBGA 码级语义**没有 codebook 编辑面**。
**建议**：codebook v1.1 增 GZBBGA 族——注册码义转录（source=registry）+
拟合提案入册（source=fitted，用户可改）；
同族扩展项：GZCE 褶皱（vocabulary_only，可一并收录）。

## 五、结论

三接口契约在本轮复审中**三项接口全部符合**；唯一未合项 F-1（GZBBGA 未入
codebook）已定性并给出 v1.1 收录方案。十月 GML 全链路零 MapGIS 编码残留；
九月库尔干 GML 属语义 id 化前构建（3177 OFBA 残留），消除需生产重基线（待批准）。
