# GeoSciML 转换对账报告（库尔干幅副本（J43C001002）全管线测试）

生成: 2026-10-02 · GML: `jws_geosciml_full.gml` · Lite: `D:\jws\output\geosciml\lite`

## 断言汇总

PASS 29 / WARN 0 / FAIL 0

| ID | 级别 | 内容 |
|---|---|---|
| XSD | PASS | full document validates against geoSciMLExtension.xsd (0 errors) |
| A01 | PASS | 57 GeologicUnit (got 57); duplicate gml:id: [] |
| A02 | PASS | events lacking any age (non-exempt): [] |
| A03 | PASS | regional dual-track issues: [] |
| A04 | PASS | eventProcess mismatches: [] |
| A05 | PASS | composition units: 12 (mapping expects 12); bad lithology URIs: [] |
| A06 | PASS | polygon MFs: 713/713; unresolved: 0; orphan units: 0 [] |
| A07 | PASS | contacts: 1316/1316; nil contactType: 0/0 |
| A08 | PASS | SDS: 310/310; nil faultType: 0/0（pending 码）; issues: [] |
| A09 | PASS | 产状块: 93/93（stSD 总 190）; azimuth out of range: []; dip: [] |
| A10 | PASS | polarity occurrences: 2 (expect 2, 202004 only) |
| A11 | PASS | folds: 4/4; nil profileType: 0/0; bad URIs: [] |
| A12 | PASS | axis round-trip (GML flipped == L1 source): axis flip mismatches: 0 |
| A12b | PASS | Lite axis passthrough (unflipped): lite first ring == source: True |
| A13 | PASS | illegal URIs: []; unresolved internal: [] |
| A14 | PASS | QuantityRange issues: [] |
| A15 | PASS | empty elements found: [] |
| A16 | PASS | members: 4733/4733 |
| A17 | PASS | Lite issues: [] |
| A18 | PASS | load-time drift: [] |
| A19 | PASS | placeholder present=True, NAMESPACE_FINAL=False |
| A20 | PASS | spot checks: ok |
| A21 | PASS | 配对待裁定标记: 0/0; pending 无 P-PAIR 残留: True |
| A22 | PASS | 六类标签: (51, 5, 3, 0, 29, 5) vs 期望 (51, 5, 3, 0, 29, 5)（合计 93/93） |
| A23 | PASS | 矛盾横幅 SDS 数: 7/7 |
| A24 | PASS | DisplacementValue: 97/97; movementSense 分布 {'no_movement_sense': 34, 'reverse': 54, 'normal': 5, 'sinistral': 3, 'dextral': 1} vs {'reverse': 54, 'normal': 5, 'no_movement_sense': 34, 'dextral': 1, 'sinistral': 3}; hangingWallDirection trend: 93/93 越界 [] |
| A25 | PASS | GeologicFeatureRelation: 160/160; 非法 target: 0; 非 contacttype relationship: 0; 自指: [] |
| A26 | PASS | 测量点 MF: 93/93; specification 未解析: 0; 垂足错位/缺失: 0; 离线: 0; 出特征带: 1; 端点钳制: 0 |
| A27 | PASS | 标本视图: 48/48; 结构违规: 0[]; 违反标记: 1/1 |

## 源-目标计数

| 主题 | 源(L1) | 目标 | 说明 |
|---|---|---|---|
| 单元 GeologicUnit | 57 | 57 | 概念对象 |
| 图斑 MappedFeature | 713 | 713 | {'LDZOFBB001.WP': 608, 'LDZOFBB002.WP': 10, 'LDZOFBB003.WP': 46, 'LDZOFBB004.WP': 49} |
| 界线 Contact | — | 1316 | 剔 GZBD=10/81 后为 1316 |
| 断层 SDS | 310 | 310 | |
| 断层产状描述 stStructureDescription | 93 箭头 | 190 | 含 DisplacementValue 块 |
| 产状 Foliation | 305 | 305 | |
| 褶皱 Fold | 4 | 4 | Lite 不出 |
| member 总数 | — | 4733 | 期望 4733 |

## pending 状态

映射文件 pending 节: 14 项 → `D:\jws\output\geosciml\pending_review.md`
nil contactType: 0（期望 0）