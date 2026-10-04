# 三层逻辑再审报告（2026-10-04）

> 用户指令：「再次审计三层逻辑，优化精炼 geosciml4china 管线流，测试」。
> 对象：三层逻辑跨域实现（GZEEB/GZELD/GZBD 三域）与管线流。

## 审计发现与处置（4 项缺口，全部当日闭环）

| # | 缺口 | 域间一致性 | 处置 |
|---|---|---|---|
| 1 | **gzbd 冲突册无裁定合并**——gzeeb 冲突册有「已裁定条目跨轮保留」合并逻辑（adjudicated 在前），gzbd 重跑会丢失已裁定行 | 一致性缺口 | [gzbd.py](D:/geosciml4china/src/geosciml4china/calibrate/gzbd.py) 补齐同口径合并+零新分歧时纯裁定册保留/无裁定行才清件 |
| 2 | **陈旧守卫只覆盖 GZEEB 映射表**——GZELD/GZBD 两张映射表编辑后无提醒 | 管线流缺口 | [pipeline.py](D:/geosciml4china/src/geosciml4china/pipeline.py) 守卫扩展为三表（各配对应标定域命令提示） |
| 3 | **L3 契约无自动断言**——「同码终态语义统一」这一三层逻辑核心保证只靠人工核验 | 验证缺口 | 新增 [test_three_level_contract_audit.py](D:/geosciml4china/tests/test_three_level_contract_audit.py)（4 类×双幅=8 用例：GZEEB/GZBD 唯一性、映射表覆盖与一致、own 留档达标） |
| 4 | **gzbd 码义全继承分歧无核验卡**——`_gzbd_conflicts_<key>.csv` 已产出但 gap_report 无配图，裁定工作台最后一环缺失 | 裁定闭环缺口 | [gap_report.py](D:/geosciml4china/src/geosciml4china/render/gap_report.py) 新增 2b 节（`cards/gzbd_inherit_conflicts.pdf`） |
| 5 | **②c 缺口报告仅全标定分支执行**——`--skip-calibrate-stages` 路径从不刷新 gap report，编辑-再转化回路迭代裁定时核验卡必然陈旧（jwss 管线两轮未产出 2b 卡暴露） | 管线流缺口 | [pipeline.py](D:/geosciml4china/src/geosciml4china/pipeline.py) ②c 提升到两路径汇聚点（物化后统一执行）；jwss 管线内 `gzbd_inherit_conflicts: 4` 卡产出验证 |

修复过程捕获 1 处自身回归（gzbd.py 缺 `import os`，由 gzbd_rules_audit 测试即时捕获）——测试网有效性实证。

## 复核通过的既有设计（无偏离项）

- **三层数据流**：L1 段级（gzeeb 投票/gzbd 解释）→ L2 码级判定（`_mle_sem_by_code`/`_code_sem`）→ L3 全继承+映射表+语义出站，三域同构；
- **优先级链**：注册表 > CSV user_semantic > 签名 > MLE（GZEEB）；用户裁定级 > MLE精化 > 注册先验（GZBD）；canon/disp 双层标签口径防变体假分歧；
- **继承例外**：覆盖库/裁定行绝对（GZEEB verdict=裁定（覆盖库）/制图误差；GZBD 状态=用户裁定改码/分歧未裁定/制图误差剔除）；
- **核对后置**：期望核对对继承后终态语义执行，一段一条去重（`._conf_by_seg`）；
- **两相物化**：基线 L1（实体/辅助链消费源）→ 终态 L1（语义写回）——管线 ② 阶段序不动；
- **guard 链**：build 前置新鲜度守卫（entities/gzbd 新于 L1 即拒）+ pipeline 映射表陈旧守卫（三表）。

## 测试

- 测试套件 **115 passed / 3 skipped**（107→115：+8 三层契约用例）；
- gzbd 双幅重跑：jwsss 70 段静默继承/0 冲突、jwss 4 段让位登记保留（合并逻辑验证）；
- 双管线终验（materialize→build→verify→render+gap_report）：jwsss PASS 29/29（A07 80/80、A23 22/22）、jwss PASS 29/29（A07 192/192、A23 7/7）；
- 缺口 5 修复后 `--check-only` 双幅复验：②c 汇聚点在 skip 模式下正常刷新 gap report，jwss `gzbd_inherit_conflicts: 4` 卡管线内产出，verify 双幅 PASS 29/29 不变。
