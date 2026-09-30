# geosciml4china 执行自支持地质语义判别逻辑 · 保真度审计

**日期**：2026-09-29　**对象**：geosciml4china 0.1.0 包全链（convert/render）+ pymapgis 语义层新幅基线分支 + 奥依亚依拉克基线脚本
**基准**：自支持判别逻辑核心原则 v2（09-27 裁定）+ 方法论五条（分层/独立/闭环/优度/整体）+ 管线铁律（只消费不重判、矛盾交人工裁定永不自动改码、置信度统一 S×I×F 框架、登记制）
**方法**：全链消费点取证（文件:行）+ 新幅 L1/产出实测抽查 + 双幅回归复核
**触发**：包化迁移 + 第三幅（奥依亚依拉克）首接新增 12 处泛化分支后，验证执行不变形

## 1. 合规确认（主链严格执行，证据在案）

| 契约 | 证据 | 结论 |
|---|---|---|
| 转换只消费判别产物（生效码/标定列），不重判 | build.py:144 `row["GZBD_eff"]`、:248 `row["gzeeb_eff"]`、:340 `row["sem_type"]`；原生码仅作映射缺行回退（build.py:343，设计内通道） | ✓ |
| 生效码写入唯一（标定合并/覆盖库路径） | 全仓扫描：gzeeb_eff/GZBD_eff 写入点仅 materialize.py 两处（标定合并分支 + 新幅基线恒等分支），无第三写入点 | ✓ |
| B1/B2/B3 裁定执行 | 新幅 build 自动执行：status=excluded 剔除通道、`_clean_optional_str` NaN 清洗、verdict 违反注记通道（本幅 verdict=None→零注记，诚实） | ✓ |
| 未评估=诚实沉默 | 新幅 faults L1：structural_type/activity/verdict/checks/confidence 全 None（无标定即空载，不虚构）；活动性强先验未评估→零发射（保守正确） | ✓ |
| 矛盾/未定交人工 | 新幅：GZEEB 02/03/35/40、GZCE 01 pending（73+44 段 nil 在册）；样式未分类单元占位灰+pending；互验冲突 7 例入审查册；全程零自动改码 | ✓ |
| 码义随幅 | 转录行全部带 `transferred` 注记且入 pending 裁定单待图例确认（非静默采信） | ✓ |
| 样式单源（F1 语义→样式） | stylegen 消费 lite 视图语义字段（unit_norm/layer_role/src_file，stylegen.py:151-156）；from-wp 仅作 bootstrap 且与 from-lite 逐字节同构 | ✓ |
| 渲染只读 | 镜像 C1-C7 仅比对；叠加层消费 GML 语义；F9 闸门在案 | ✓ |
| 命名空间闸 | A19 PASS（占位串+FINAL=False）×新幅 | ✓ |
| 双幅回归 | 全部新幅修复后：库尔干/英吉沙 20/20 文件 sha256 逐字节一致 + 镜像 C1-C7×2 全过 | ✓ |

## 2. 偏差发现（分级）

### 违反（直接违背已定框架）

**F1［中］aux 基线置信度自创标签，统一框架旁路。**
新幅 assoc/三联体基线脚本写 `confidence="low"` 字符串，不经 `confidence.py evaluate()`；L1 fault_aux 主题实况：`confidence={"low"}×159`，**conf_breakdown/conf_band 缺列**——违反 SEMANTICS_VERSION 1.1.0「L1 统一三列」契约与「禁止自创尺度」铁律。
**根因**：lint 守卫（_confidence_reconcile.py:153）扫描面只含 ROOT+YJS 的 `_*.py`，新幅目录脚本未入扫描；且其模式只捕浮点字面量，漏字符串标签。
**处置建议**：基线脚本接 evaluate()（source_tier=code_read、independence=single、F=1.0 → C=0.18→band 落 suspect/pending）；lint 扩面（图幅目录+字符串标签模式）。

**F2［轻］界线基线置信值不自洽。**
materialize 界线无解释 CSV 时 `_bnd_conf(None,None,None)`→0.6（旧标签映射尾端默认），而 conf_breakdown/conf_band=None——数值 0.6 与空带并存。按 D2 裁定，未评估行应 unassessed（confidence=None）。
**处置建议**：无标定行 evaluated=False→confidence=None、band=unassessed。

### 程序偏差（未走裁定/登记通道）

**F3［中］时代可定脉岩取色规则扩充未登记。**
dike_*→岩族真表（t10/t6/t12）为本次断链修复中新增的分类规则（库尔干/英吉沙从未触发该分支）。更严重的是产出报告给这些单元挂 **0.85/consistent**（表命中档）——未裁定规则扩充不应直达 verified 档语义。另注：复合时代后缀在两分支处理不一致（t6 精确世/纪键未命中→pending ✓ 诚实；t9/t10 代群 startswith 命中 Pz2——O-D2 归 Pz2 的解析序未经裁定）。
**处置建议**：该规则以 pending 项登记（或用户裁定后播种 overrides）；规则未经裁定前，行经此分支的单元 conf 降 pending/draft 档。

**F4［轻］F9 norm 异形码合并无登记。**
'→J↓3→k'/'→J↓3→k  '（尾空格变体，库孜贡苏组）按「rgb/name/pattern 全同」合并——消费侧处置正确，但尾空格变体属数据编码缺陷，应入面元缺陷修复闭环册（polygon_attribution_overrides 候选）而非仅渲染侧静默合并。

**F5［中］新幅 aux 语义登记册未建。**
P-AUX-REMAP（倾向公式 offset=0 暂定）、1882/1883 码义、互验冲突 7 例现居审查册 CSV——非正典登记册（库尔干/英吉沙的 `fault_aux_code_semantics.json` 体制）。裁定项居无定所即有丢失风险。
**处置建议**：建新幅 aux 语义登记册，三项迁入；P-AUX-REMAP 由用户目视裁定后转 decided。

### 覆盖缺口（应做未做，当前诚实沉默）

**F6［轻］活动性强先验未评估**（gzeeb 审计链未接入，checks=None→零发射）。行为正确，但作为最新规则覆盖缺口登记：新幅接入清单应含「活动性先验评估」一项。

**F7［轻］官方合规 T1-T15 未覆盖新幅**（audit_geosciml_conformance.py 在 JWD 冻结侧、只认双幅 SHEET_PARAMS）。29 断言已过；T 系待移植入包后补审。

### 登记项（泛化债，v0.2）

**F8** 库尔干/英吉沙味硬编码残余：verify.py A02 `dyke_pending` 豁免集、A20 分支结构；mirror.py C6 kept-code 清单（新幅恰为子集而侥幸通过）；gml_overlay.py:296 `"expected": 7` 字面量。v0.2 统一泛化（词表驱动/注册表驱动）。

## 3. 结论

**主链严格执行**（第一节十条契约全部在案）；偏差集中在本轮**新幅首接新增的基线分支**——基线通道的登记纪律（pending/审查册/占位）总体遵循，但**置信度统一框架**（F1/F2）与**规则扩充裁定通道**（F3/F4/F5）各有一处真违反/程序偏差。无一项影响库尔干/英吉沙已验收产出（回归逐字节一致）；无一项构成自动改码或矛盾静默。

**处置优先级**：F1（统一三列补全+lint 扩面）→ F3（规则登记/降级）→ F5（建册）→ F2/F4 → F6/F7（随三审接入消解）→ F8（v0.2）。

—— 审计执行：kimi-k3；证据可复算（`g4c verify --sheet aoyiyayilake` 29/29 + 本报告文件:行引用）

## 4. 附：用户补获偏差（审计未逮，2026-09-29 同日）

**F9［违反·中，已修复］褶皱类型判别渲染侧硬编码二分。**
用户指出「没有正确区分褶皱要素的类型」。实情三层：①渲染器 `render_fold_layer` 以
`gzce != "03"` 硬编码二分——01（向斜）落入背斜分支（实线透镜+背向箭头），英吉沙
2 条+奥依亚依拉克 44 条向斜全部画反（库尔干无 01 码而从未暴露）；②词表 GZCE=01
全幅 pending（库尔干无此码所致盲区），新幅 44 条 nil profileType；③second-digit
（01/03、02/04 两对）区分语义未解析。
**裁定与修复**：01=向斜由名称自证定版（英吉沙 2 条+新幅 44 条名称全为向斜系、零反例；
注记入三幅词表映射 decided 行）；render_fold_layer 向斜类参数化（默认 {01,03}）+
fold_class 词表语义列优先（语义单源）；第二位数区分（单式/复式候选）入 pending
（P-GZCE-COMPOUND）。修复后：英吉沙/新幅 verify 29/29，库尔干 GML+lite 回归 8/8
逐字节一致+check-only 全过。**教训**：渲染侧的码值硬编码（`gzce=="03"`）与 F8 同类——
码义判别的唯一合法载体是词表登记册，渲染器只消费判别结果。
