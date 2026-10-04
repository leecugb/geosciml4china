# 三层架构契约执行审计（2026-10-05）

**对象**：geosciml4china 对以下用户契约的执行情况——
> ①自支持判别逻辑用于段级别的编码值的地质语义标定；
> ②图幅在全局层面基于编码值与地质语义的统计关系，以最大似然原则最终标定
> 编码与地质语义的映射关系；
> ③所有数据按照全局标定的编码-地质语义映射表将数据转为基于地质语义的
> GeoSciML；
> ④渲染引擎完全基于地质语义（GeoSciML）。

**方法**：契约条款逐条对照现行代码（file:line 证据）；结合 2026-10-04
全面管线审计（三路）与 2026-10-05 今日修复后状态复核。
**基准**：现行工作树（含一致性抽象约束/GZELD 全局先验/属性优先通道
/主张宇宙修复全部生效）。

## 逐条核验

### 条款① 段级自支持标定 —— **合规（一处记录在案的例外）**

| 域 | 段级判别机制 | 证据 |
|---|---|---|
| gzbd（界线） | 两侧单元自适应探针（40/100/250m）+新老关系+接触规则+属性优先通道（QDUEAQ/QDUECD） | gzbd.py 探针循环/通用级联 |
| gzeeb（断层） | 段级 MLE 投票（码先验 3/名 2/签名 2/运动学 2+强档/dip 1/aux 2/覆盖 2-3/界线重合）+强证据即标定（老盖新/钩旋向/Q-界线三档） | gzeeb.py 投票循环 |
| auxchain（辅助点） | 距离带+中位数最近+a-b/a-b-a+臂隙+钩对空间识别+区间语义 | auxchain.py |
| attitudes/fossils | 宿主/类型约束/不变量通道 | attitudes.py/fossils.py |
| entities（归组） | 端点几何+走向+覆盖多级链接 | entities.py |
| fault_contact_activity | 断裂接触界线两侧探针 | fault_contact_activity.py |

**例外（记录在案）**：folds（褶皱 GZCE）**无段级证据通道**——码义命中词表即
标定，无投票（folds.py docstring 明示：褶皱无产状点/探针可构成 MLE 回归）。
性质：词表码义标定域，非自支持判别——契约①对褶皱不成立但属有意设计。

### 条款② 全局 MLE 映射表 —— **合规（两处已修，两处缺口）**

| 项 | 状态 |
|---|---|
| 三表产出（code_semantics_map / gzeld_semantics_map / boundary_semantics_map，全码一表） | ✓ |
| 主张宇宙=全部非注册非签名码（03/35 案修复） | ✓（2026-10-04） |
| 族义判定规则（≥25% 主导/逆断层一幅一码/复活签名/签名通道/泛称兜底） | ✓ |
| GZELD 统计推导+全局先验分层（注册表>全局先验>推导>不明） | ✓ |
| 编辑-再转化回路（user_semantic 列、跨轮保留、陈旧守卫、jwsss 16 案端到端实证） | ✓ |
| **缺口 G1**：GZELD 表 user_semantic 不进 MLE 投票（编辑-再转化半回路） | ✗（gzeeb.py 投票链缺 `_user_kin`；审计 P1-7） |
| **缺口 G2**：gzbd/gzeeb 两域"注册表 vs CSV 用户修改"优先级相反（gzbd：CSV>注册；gzeeb：注册>CSV） | ✗（gzbd.py:1234-1249 vs gzeeb.py:1103-1109；审计 B8） |

### 条款③ 按映射表转 GeoSciML —— **断层合规；界线走段级通道（设计差异）；两处断线**

断层链：映射表（L2）→ 全继承回填段级 structural_type（L1 落地）→ GML
（faultType 语义驱动/movementSense/description）✓。界线链：段级标定语义
（_gzbd_semantic_interpretation.csv）→ L1 → sem_label → CGI contactType
语义驱动（build.py:170-186）——**界线不经码级映射表强继承**（界线语义
本质段级：同码 01 各段可分别为整合/侵入/第四系接触）；映射表为 L2 工件
+用户编辑回授通道（user_semantic→下轮标定→段级刷新）。**设计差异合
理但契约字面只覆盖断层——建议文档明示界线走"段级语义+映射表回授"**。

| 断线 | 证据 | 后果 |
|---|---|---|
| **movementSense 不接 GZELD 映射表** | movementSense 两源=hooks CSV+triplets verdict（auxchain 产物）；materialize.py:227-228 内化白名单不含 gzeld/gzeld_sem；build 无 gzeld→slip_sense 回退（审计 P1-1） | 16×103 段应出 dextral、18×104 段应出 sinistral 而实际不出——GZELD 全局先验的最后一公里未通 |
| **folds 标定表死档** | `_fold_calibration_{key}.csv` 无消费方；build.py:493-508 直查词表（审计 D5） | 褶皱 L2 工件不入转换——条款③对褶皱形同虚设 |
| **inferred_faults 表死档** | `_inferred_fault_calibration.csv` 无消费方（审计 P1-6） | 推测断层标定结果不出站 |

### 条款④ 渲染完全基于地质语义（GeoSciML） —— **合规（含镜像核验）**

渲染输入全部为 GeoSciML 工件：lite 视图（单元/界线/断层/产状/标本/褶皱/
水系）+ GML 叠加（movementSense 钩线/矛盾横幅=GML description）+ lite
测量点视图（fault_measure）。样式单源=stylegen（语义→DZ/T 0179-2025 色库）
+断层样式自 lite SDS 视图。镜像核验 C1-C7 前置比对 L1 一致性（渲染前置
约束原则）。**无 MapGIS 原始数据直入渲染路径**（render.py 输入清点确认）。
例外（记录在案）：stylegen 的 WP 引导回退用于新幅首接（lite 未建时）；
gap_report 卡片读标定 CSV——属专家裁决报告而非成图。

## 结论与裁定建议

契约四条**主线全部成立**，机制级缺陷集中三处：

| 序 | 项 | 修复量 |
|---|---|---|
| 1 | movementSense 接 GZELD 链（materialize 白名单加 gzeld 列 + build 回退分支 + verify A24 画像随动） | 小（三处接线） |
| 2 | GZELD user_semantic 进投票链（gzeeb.py gzeld_sem_now 链补 `_user_kin`） | 极小（一行） |
| 3 | gzbd/gzeeb 用户编辑优先级对齐（择一口径并文档化） | 裁定项 |
| 4 | folds/inferred_faults 死档处置（接线消费或文档声明审计域） | 裁定项 |
| 5 | 契约文档补界线段级通道的明示（条款③的界线例外） | 文档 |

—— 审计执行：kimi-k3；证据可复算（全部 file:line 可直读复核）
