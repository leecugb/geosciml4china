# geosciml4china 管线流全面审计（2026-10-04）

**对象**：pipeline 全链（⓪预检→①convert→②标定七域→②a/②b 物化→②c 缺口报告→③stylegen→④build→④b stylegen_fault→⑤verify→⑥render）+ 全部生产者/消费者写出路径。
**方法**：三路并行读码审计（编排与写出纪律 / 标定域数据流契约 / 转换渲染验证链），全部结论附 file:line 证据；重复发现已合并。
**基线**：现行工作树（含 2026-10-04 今日裁定全部生效件）。

## 执行摘要

管线**主链路逻辑成立**（依赖图闭合、物化两相自洽、镜像核验同口径、影子通道大体成形），但审计发现 **5 项 P0 级缺陷**（正典污染/静默丢层/陈旧残留/混合时效/核对缺勤）+ **9 项 P1 级**（断链通道/死档域/守卫缺口）+ **12 项 P2 级**（工程卫生）。最重的三个教训形态与既往同源：**一个集合服务两个语义**（_unreg 主张宇宙案的孪生——legacy 文件消费/守卫错位）、**门卫用错变量**（化石物化丢层）、**清零与守卫的不对称**（登记册/映射表/样式生成件的写出-清理-守卫三件套口径不齐）。

## 审计矩阵（26 项，按严重度）

### P0 正典安全/数据完整性

| # | 位置 | 缺陷 | 证据 | 处置建议 |
|---|---|---|---|---|
| P0-1 | gzbd.py:1300-1307, 1344/1191 | **影子运行污染正典**：①冲突册 else 分支改写/unlink sh.root 正典册（影子零分歧即删册）；②边界映射表读写均 sh.root——影子覆盖正典映射表（gzeeb 17:09 案已修的同类，gzbd 侧漏修） | gzbd.py:1300 `_bcp = sh.root / ...`；1344/1191 `_bmap_p = sh.root / ...` | 读 sh.root、写 _outdir（gzeeb.py:190-191 同构修复）；影子下禁 unlink |
| P0-2 | pymapgis materialize.py:385 | **化石/泥火山物化门卫用错残留变量**：`if f.exists():` 的 f 指向上游循环残留（LDLYAAE002 水系面）而非 BB099——巴什库尔干无水系面，化石块**整体静默丢层**（当前被 specimen 期望=0 掩盖） | materialize.py:385（f 为 L340-343 循环残留） | 门卫改判 BB099 路径存在性；加回归测试 |
| P0-3 | gzeeb.py:1455-1463 | **冲突登记册无清零**：`if conflicts:` 才写册——本轮零冲突时旧册残留，pending 行不再代表最新计算（实证：库尔干校准件 10-03 23:53 新于冲突册 10-03 20:53） | gzeeb.py:1455 vs gzbd.py:1299-1307（有清零）与 gzeeb.py:1244-1246（fallback 有清理） | 补清零（对齐 gzbd/gzeeb-fallback 口径） |
| P0-4 | sheets.py:198-199 + sources.py:104/196 + build.py:213/521-523 | **库尔干 aux 双名漂移**：注册表/profile 指 legacy 件（`_fault_triplets_detail.csv` 9-27、`fault_aux_point_association.csv` 9-28），auxchain 产出新件（10-02 已分叉）；build 同一装配混用新 mp ids×旧三联体×旧 assoc **三个 vintage**，且 _stale_inputs 只看守新名——被消费的 legacy 件无时效闸 | sheets.py:198-199 vs auxchain.py:1417-1418；build.py:213-216/522-523；gzeeb.py:290（seg_dipaz 读 legacy） | 裁定正典名后统一注册（推荐切到 auxchain 产出件）；被消费件全入 _stale_inputs |
| P0-5 | gzeeb.py:1248 | **GZELD 运动学期望核对被 `if _unreg:` 静默门控**：统计推导+kin 核对+提案出站三块全在 `if _unreg:` 内——全码注册幅（库尔干 310/310）_unreg 为空 → `_kin_defer` 永不执行，GZELD×结构语义核对**静默缺勤**（库尔干册内 GZELD 冲突行为 10-03 旧件残存） | gzeeb.py:1248-1343；760 行入队点 | kin 核对移出门控（推导/提案保留在门控内） |

### P1 功能断链/死档域

| # | 位置 | 缺陷 | 处置建议 |
|---|---|---|---|
| P1-1 | materialize.py:227-228 + build.py:289-300 | **gzeld→movementSense 通道不存在**：movementSense 两源（hooks 旋向+triplets verdict）与 GZELD 链零接线；materialize 内化白名单不含 gzeld/gzeld_sem 列——103=右行/104=左行的全局先验永远到不了 GML movementSense（16 码 5 段应出 dextral、18 码 8 段应出 sinistral 而实际不出） | materialize 白名单加 gzeld/gzeld_sem；build.py 增 gzeld_sem→slip_sense 回退（钩对优先，GZELD 兜底）；verify A24 画像随动 |
| P1-2 | gzbd.py:932 vs gap_report.py:117 | **缺口候选文件名断裂**：写 `_gzbd_gap_candidates.csv`（无 key）读 `_gzbd_gap_candidates_{key}.csv`（带 key）——**任何图幅的先验缺口配图永不触发** | 择一后缀口径（建议带 key） |
| P1-3 | gap_report.py | **docstring 承诺的 gzeeb 冲突册节未实现**：第 3 项「断层冲突/待裁定」无对应读码——码义未注册/码义全继承/证据冲突 pending 行永不入缺口报告 | 补该节读码 |
| P1-4 | gml_overlay.py:300 | **render 矛盾横幅 expected=7 硬编码**（库尔干残留）——verify A23 按幅画像（aoy=37），render 侧常量化仅打印；用户目击的 hit=37 vs expected=7 差异全由此 | expected 改从 sheets 注册表/verify.EXPECT 单源取数 |
| P1-5 | calibrate/folds.py:60 + build.py:493-508 | **folds 标定 CSV 无消费方**：`_fold_calibration_{key}.csv` 产出后无任何读者（build 直查词表）——褶皱"标定"目前只产审计件；且无 mkdir、CLI 无 --out | 接线消费（materialize/build）或降级为审计域并在文档声明；补 mkdir+--out |
| P1-6 | build.py:529-530 + materialize | **inferred_faults CSV 是死档**：`_inferred_fault_calibration.csv` 在 _stale_inputs 有时效对但从不被物化/消费——重跑 materialize 刷 mtime 即空过闸 | 接线内化或从 _stale_inputs 移除 |
| P1-7 | gzeeb.py:552-554 | **GZELD 用户映射表编辑不进投票**：`_user_kin` 只接期望核对与出站表，MLE 投票无——编辑-再转化回路对 GZELD 只兑现一半（与 GZEEB 侧 _user_sem 进继承链不对称） | gzeld_sem_now 链补 `_user_kin.get` |
| P1-8 | build.py:511-544 | **build 陈旧守卫三漏洞**：folds/hooks/contact_activity_conflicts 三对不在守卫；`if not src.exists() or not tgt.exists(): continue` 缺失对被静默放行（断链场景在 sources 处原生崩而非守卫信息） | 补三对+缺失对硬失败 |
| P1-9 | stylegen→build | **style 新于 lite 的反向守卫缺失**：build._stale_inputs 不含 style_generated；verify 无检查；render F3 只单向。唯一拦截=render 前置 C3 硬失败（stylegen 后漏跑 build 即中止——本次实测发生） | build 增 style vs lite 守卫（或 pipeline 顺序自动链） |

### P2 工程卫生（12 项，择要）

| # | 缺陷 | 位置 |
|---|---|---|
| P2-1 | pipeline rc 压扁（build rc=2→1，剖面未注册与守卫失败不可区分）；三处 sys.argv 注入无异常兜底 | pipeline.py:140-141, 137-176 |
| P2-2 | --skip-calibrate-stages 守卫警告级（编辑映射表后物化照常）；--skip-convert 无 L0 预检 | pipeline.py:59-60, 70-83 |
| P2-3 | gml_overlay.py:255 潜伏 NameError（`code` 未定义，draw_marks=True 即崩——现被 False 屏蔽） | gml_overlay.py:255 |
| P2-4 | 空表无头写→下游 EmptyDataError（auxchain anomalies/review/triplets 无表头兜底；实证 anomalies_kurgan.csv 仅 5 字节）；零辅助点幅 auxchain 即崩 | auxchain.py:1417-1421, 325 |
| P2-5 | build.py:295 hooks sense `else "dextral"`——脏数据归右行，无校验 | build.py:295 |
| P2-6 | **entities Q 覆盖硬编码 1300 且不排除 Qp1X**——西域组计入 L3 覆盖证据，与 gzbd/gzeeb 口径矛盾；inferred_faults 同样硬编码+无箭头归一 | entities.py:84-86, inferred_faults.py:54-58 |
| P2-7 | QDUECD 兜底链 `_age_rank_of` 跨域未接线（gzeeb/fault_contact/entities/inferred/attitudes 全裸 _unit_age_rank——г/∑ 前缀码在这些通道静默丢证据） | gzbd.py:151-171 vs gzeeb.py:251/278/459 等 |
| P2-8 | gzbd/gzeeb 两域"注册表 vs CSV 用户修改"优先级相反（gzbd：CSV>注册用户裁定；gzeeb：JSON>CSV）——单源优先级链不唯一 | gzbd.py:1234-1249 vs gzeeb.py:1103-1109 |
| P2-9 | entities 单域重跑冲掉 aux 写回两列（CLI triplets=None→空映射全清）；"混合判别（交检核）"只消费不生产（死分支） | entities.py:682-693, 690 |
| P2-10 | 镜像 C1-C7 未覆盖 fold/specimen/water 双视图/gap_report；expect_counts 仅 4 元组 | mirror.py:43-204, sheets.py:57 |
| P2-11 | auxdisc.py=auxchain 陈旧克隆且写同五件（单源纪律破口）；verify.EXPECT.compositions 死字段；materialize 异常册无裁定过滤（与 auxchain 两种排除语义） | auxdisc.py:292-297, verify.py, materialize.py:281-283 |
| P2-12 | 文档陈旧（fault_contact docstring 称追加 gzeeb 册/pipeline docstring 称 inferred 未入包——均与实现矛盾）；测试侧 kurgan 分支不读 profile（jws 类幅找错文件）；entities.py:573 段数硬编码打印 | 各处 |

## 闭环确认（审计验证无缺陷项，勿动）

- 写出路径纪律整体良好：gzeeb 映射表已修（写 _outdir/读 sh.root）、auxchain 全部产物 outdir、attitudes/fossils/inferred/fault_contact 全部 outdir
- 依赖图闭合：entities 写回环（auxchain→entities→gzeeb）全管线序下闭环；hooks 同名双消费（gzeeb/build）一致
- profile 通道五处消费一致（entities/auxchain/gzeeb/fault_contact/inferred/materialize），无残留 key 分支（jws 先例已修复）
- stylegen_fault 的 lite SDS 假设在 pipeline 序中恒成立（④b 恒在 ④ build 后）
- 镜像 C1-C7 数据源/豁免逻辑同口径（CONTACT_CODES 注册表化、status=excluded 双侧一致）
- materialize 各域回退基线自洽（--skip-calibrate-stages 混合态按域独立回退）
- 非库尔干各幅注册名=auxchain 产出名（无 A3 漂移）

## 优先级建议（修复序）

| 序 | 项 | 理由 |
|---|---|---|
| 1 | P0-1 gzbd 影子污染（与 gzeeb 已修同构，半小时内可修） | 正典安全风险，每次影子 calibrate-gzbd 都可能删册/覆盖映射表 |
| 2 | P0-3 gzeeb 册清零 + P0-5 kin 核对移出门控 | 陈旧 pending 行污染消费方（build 横幅/专家队列）；库尔干 GZELD 核对缺勤 |
| 3 | P0-2 化石门卫（pymapgis 侧，1 行）+ P0-4 库尔干 aux 双名裁定 | 静默丢层/混合 vintage——数据完整性 |
| 4 | P1-1 gzeld→movementSense 接线（materialize 白名单+build 回退） | 今日裁定的 GZELD 全局先验的最后一公里 |
| 5 | P1-2/P1-3 gap_report 断链两节 + P1-4 expected 硬编码 | 缺口报告/渲染统计的可信度 |
| 6 | P1-7 GZELD user 编辑进投票 + P1-8 守卫三漏洞 + P1-9 style 反向守卫 | 编辑-再转化回路与守卫链完整性 |
| 7 | P1-5/P1-6 死档域处置（接线或声明）+ P2 批次 | 架构整洁 |

—— 审计执行：三路并行（编排/标定域/转换渲染链），证据可复算（全部 file:line 可直读复核）
