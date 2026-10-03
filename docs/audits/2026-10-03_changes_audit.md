# 本轮改动全面审计（2026-10-03，用户指令「审计 geosciml4china」）

对象：2026-10-03 当日未提交改动——⑤⑥ 解耦（四域语义化）/ 01 码义门槛 /
褶皱标定域 / 缺口报告 / 样式迁移（库尔干裁定→标准样式）/ 活动断层样式 /
mapping 缓存修复 / 产状同码继承 / verdict 联动 / 推测断层渲染链路。

## 一、改动盘点

geosciml4china 工作区 14 文件（+286/−122）+ 2 新文件（calibrate/folds.py、
render/gap_report.py）+ 1 审计报告；pymapgis 侧 2 文件未跟踪（pdf_writer.py、
materialize.py——pymapgis 仓库这些文件本就未入库，属既有状态）。

## 二、测试闸门

| 套件 | 结果 | 备注 |
|---|---|---|
| geosciml4china | **107 passed / 3 skipped** | 全绿 |
| pymapgis | 110 passed / **1 failed** | test_console_script——Windows 环境壳（shell not found），与本轮无关 |
| jwss 全链 | **verify 29/29 PASS**（01 裁定生效版） | 渲染件 12:50 |

## 三、审计发现与处置

| # | 发现 | 严重度 | 处置 |
|---|---|---|---|
| F1 | **跨幅回归**：库尔干/英吉沙 structural_type 含裸名「断层」（156+130 段），SEMANTIC_TO_VOCAB 无此键——包路径渲染落默认红 0.5（应为 0.6） | 高 | **已修**：`"断层"→"fault"` 入表；三幅 structural_type 全量对账全命中 |
| F2 | **泛化缺口**：calibrate_folds 对缺褶皱层图幅无守卫（load_source_layer 抛错即断管线） | 中 | **已修**：LDZOFBA005 缺席优雅跳过（与 gzbd BB002 守卫同构） |
| F3 | mapping._cache 不随 init_sheet 重置（褶皱域首呼锁定 kurgan 词表 → jwss build 三联失败） | 高 | **已修**（12:20）：缓存按 VOCAB_MAPPING 路径键控；folds 先 init_sheet |
| F4 | 产状语义分支 4 处替换清点（202005→片理产状 / 202004→倒转层理 各 2 处） | — | 静态核对 4/4 已替换；语义色键 5 类齐 |
| F5 | 库尔干/英吉沙**包路径**下次渲染依赖 F3 自动重生（stylegen.py/stylegen_fault.py 在 inputs 清单内，mtime 触发）——无手工动作需求 | 低 | 自动生效；遗留 MapGIS 路径（码键回退）静态核对不受本轮影响 |
| F6 | E1 挂账复核：jwss `_inferred_fault_calibration.csv` 0 行=无 04 码如实空集 | — | 非缺陷，登记说明 |
| F7 | 兜底 CSV 归零时陈旧件残留（缺口报告误读 47 行） | 低 | **已修**：gzeeb 兜底 0 段时删除陈旧件 |

## 四、遗留回退核对（G4）

pdf_writer 内码键回退分支保留：遗留 MapGIS 调用方（render_strict_standard_map
等）静态核对——sem_label/structural_type 列缺席即走原码路径，行为不变；
geosciml 路径四域语义命中（实测 jwss 全链）。

## 五、结论

**通过**：测试双闸门全绿（环境性 1 失败除外）、三幅语义覆盖全命中、
跨幅回归 F1/F2/F3 三处发现并即修即验。遗留风险 F5 由 F3 自动重生消化。
建议提交。
