# geosciml4china 全链范围（2026-10-02 用户对齐定版）

## 用户对齐链（2026-10-02 定版）

> geosciml4china 首先检查 mapgis 文件的完整性，转为 L0 geojson；
> 然后使用自支持地质语义判别逻辑完成解析，生成基于地质语义的 L1 geojson；
> 转为 geosciml 格式；使用基于地质语义的 geosciml 渲染引擎，渲染成图。

| 对齐链 | 管线阶段 | 实现 |
|---|---|---|
| ① 完整性检查 | ⓪ preflight | 11 文件契约（CORE 缺即中止） |
| ② 转 L0 geojson | ① convert | pymapgis.semantics.convert_sheet + validate_l0 |
| ③ 自支持地质语义判别解析 → L1 | ②+②b | geosciml4china.calibrate 五域全包原生：gzbd（界线）→ entities（断层归组）→ auxchain（辅助点判别）→ gzeeb（断层三维）→ attitudes（产状）→ fossils（化石）→ materialize L1 |
| ④ 转 GeoSciML | ③+④+⑤ | stylegen（语义→样式）→ build（GML+Lite+pending）→ verify（XSD+断言） |
| ⑤ 语义渲染成图 | ⑥ | render（基于地质语义的 GeoSciML 渲染引擎+叠加层） |

登记缺口：推测断层标定（_calibrate_inferred_faults）未入包——挂账。
# 全链范围裁定（2026-09-29，用户裁定）

> 「geosciml4china 的输入是 MapGIS 工程文档（文件夹），它完成对 MapGIS 地质语义的
> 标定、解析，及后续的转换和渲染功能。」

## 架构分层

```
MapGIS 工程文件夹（sheet root）
  │  ① convert_sheet            MapGIS 原生 → geojson/L0（pymapgis，格式层）
  │  ② calibrate_semantics      L0 + 先验/裁定登记 → 标定阶段链 → geojson/L1
  │     （pymapgis 编排器 + geosciml4china.calibrate 标定规则库——渐进迁入）
  │  ③ stylegen / stylegen_fault 语义→样式（DZ/T 0179-2025 色库，包）
  │  ④ build                    L1 → GeoSciML GML + Lite 七视图 + pending（包）
  │  ⑤ verify                   XSD + 业务断言（包）
  │  ⑥ render                   渲染 + L1 镜像核验（包）
```

- **先验库随包**：`data/boundary_contact_priors.json`（新疆区域界线接触关系先验库，
  双料最高知识源主本）迁入包数据 `geosciml4china/data/`；图幅扩展册通道 =
  `<sheet_root>/data/boundary_contact_priors_<key>.json`（裁定追加，合并装载）。
  JWD 冻结侧副本供未迁移脚本消费，切换后单源化（防分叉登记在案）。
- **标定脚本迁移路线**（逐域、影子先行、双幅逐字节复现为准入闸）：
  gzbd（界线，P-GAP-1 急迫）→ gzeeb（断层三维+活动性先验）→ attitudes → fossils →
  aux 链（association/pairs/triplets/entities，库尔干 v5+英吉沙变体归一）。
  未迁移阶段由编排器照旧跑 profile `l1_stages` 列出的既有脚本——全链今天即可跑通。
- **码义随幅**：标定规则入包=规则通用化；图幅特异值（char_dists/remap/豁免集/码义册）
  留在图幅剖面/登记册，规则代码零图幅分支。

## CLI

`g4c pipeline --sheet <key> [--skip-convert] [--skip-calibrate-stages] [--skip-render] [--check-only]`
