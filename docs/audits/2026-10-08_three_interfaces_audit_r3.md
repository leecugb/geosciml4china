# 三接口契约审计（2026-10-08 第三轮，置信度文件契约入宪后）

> 契约原文：①接口一完整性检验+编码-地质语义标定→codebook（JSON 存映射
> 表、允许用户修改），**并配套输出 codebook 置信度文件——含项目各要素的
> 地质语义标定统计数据和矛盾项**；②接口二按 codebook 转换、GeoSciML 完全
> 脱离 MapGIS 编码系统；③接口三渲染完全基于 GeoSciML 地质语义、脱离
> MapGIS 编码体系。方法：四项目 codebook/置信度/GML 全量实测扫描。

## 一、接口一 prepare：符合（五族 codebook + 置信度双内容）

| 契约点 | 实测（四项目） |
|--------|---------------|
| 完整性检验 | preflight 11 文件契约（CORE 缺即中止） |
| 编码-地质语义标定 | 九域全包原生 + GZBBGA 先验拟合（registry/fitted/pending 三源） |
| **codebook 五族** | GZEEB/GZBD/GZELD/**GZBBGA/GZCE** 全部在册：y1 (9/10/5/4/3)、y2 (7/9/5/3/4)、y3 (8/7/5/2/3)、td (7/8/5/3/2) |
| 用户可改 | user_semantic 跨轮保留；GZBBGA 编辑回路闭环（编辑→prepare→sem_type 回填，verdict=标定（codebook 用户裁定）） |
| **置信度·统计数据** | `codebook_confidence_<key>.json`：7 域统计（裁决/置信带/覆盖率/码级质量 GZBBGA_codes） |
| **置信度·矛盾项** | 逐段 conflicts：y1 68（含**语义张力 4**）、y2 75（张力 10）、y3 90（张力 4）、td 11（张力 0）——片麻理×面理/片理等码级×段级张力逐条在档（135 在 y2 档） |

## 二、接口二 convert：符合（全项目零 MapGIS 编码残留）

| 项目 | OFBA/OFBB 图元 id 残留 | 判定 |
|------|----------------------|------|
| y1 | **0 / 8474** | ✓ |
| y2 | **0 / 8157** | ✓ |
| y3 | **0 / 6562** | ✓ |
| td | **0 / 1048** | ✓ |

注：扫描中的 `c.01.32`、`mf.K1kz.16` 形 id 为**语义 id 方案**（接触类型+序 /
单元名+序），不是 MapGIS 图元 id——设计内。转换严格按 codebook：
176→conformable_contact（GZBD 整合接触继承）、135→foliation（GZBBGA
面理继承，拆盾后严格模式）。

## 三、接口三 render：符合

| 契约点 | 实证 |
|--------|------|
| 边界样式 | contactType 优先（接口二继承语义）→ 176 按整合接触样式 |
| 断层样式 | structural_type（十月）/ faultType+observationMethod（GeoSciML 原生，任意纪元 GML）→ 推覆齿/推测虚线/复活短线正确 |
| 产状样式 | sem_type（现为 codebook 继承语义）→ **135 与 134 一致渲染为面理产状样式**（裁剪实证） |
| 叠加层 | 钩线/矛盾横幅/测量点——GML 自足 |
| 遗留回退 | GZEEB 码级回退对 GeoSciML 帧不可达（deprecated 候选，记录在案） |

## 四、结论

三接口契约**全项符合**：接口一（五族 codebook + 置信度文件含统计与
矛盾项）→ 接口二（零编码残留的严格 codebook 转换）→ 接口三（按继承
语义渲染）。语义张力作为新矛盾类已在置信度文件逐条登记（四项目合计
18 条），与 codebook 的码级产品语义形成「产品统一 × 记录如实」的双轨
闭环。遗留（非契约项）：库尔干九月 GML 的 3177 OFBA 残留消除=生产重
基线（待批准）。
