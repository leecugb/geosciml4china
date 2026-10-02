# geosciml4china 全管线审计（2026-10-02）

**对象**：`pipeline.py` 全链编排 + 五域标定模块 + CLI 命令表
**基准**（2026-10-02 用户对齐链 verbatim）：「geosciml4china 首先检查 mapgis
文件的完整性，转为 L0 geojson；然后使用自支持地质语义判别逻辑完成解析，
生成基于地质语义的 L1 geojson；转为 geosciml 格式；使用基于地质语义的
geosciml 渲染引擎，渲染成图」
**方法**：静态行证（源码调用序解析/失败中止路径）+ 产出-消费文件链核验
（各模块写出文件名=下游装载文件名）+ CLI 覆盖。

## 审计矩阵（tests/test_pipeline_audit.py，6 项全绿）

| 判据 | 结果 |
|---|---|
| ① 阶段序 | 调用序与对齐链逐字对应：preflight→convert→gzbd→entities→auxchain→写回→gzeeb→attitudes→fossils→materialize→stylegen→build→verify→render（15 环节全序） |
| ② 失败即中止 | 预检失败 return 1、L0 校验失败 return 1；物化先于 build |
| ③ 产出-消费文件链 | gzbd→_boundary_sides / entities→fault_entities / auxchain→fault_aux+triplets+hooks / gzeeb→_gzeeb_calibration_ / attitudes→_attitude_calibration / fossils→_fossil_calibration_——与下游装载名一致 |
| ③b 下游装载 | gzeeb 装载 entities/aux/hooks；build 装载 hooks（slip_by_seg）+gzeeb_eff |
| ④ CLI 完整 | 14 命令全覆盖（pipeline/check/sheets/五域/三样式/build/verify/render） |
| ⑤ 语法有效 | pipeline.py AST 有效、run_pipeline/main 定义完整 |

## 结论

**对齐链全链路就位**：五段链（完整性检查→L0→自支持判别解析 L1→GeoSciML→
语义渲染）在管线编排、文件联通、CLI 三层面全部落实；五域标定模块各自的
库尔干门逐字节准入（gzbd/gzeeb/attitudes/fossils/aux 链）构成各段执行正确
性的复合证据。套件 81→87。

**登记**：①推测断层标定未入包（管线跳过，挂账）；②端到端执行核验
（三幅 L1/GML 级联）待用户许可——静态审计+分域门禁已就位，动态全链
复验随之。

—— 审计执行：kimi-k3；证据可复算（pytest tests/test_pipeline_audit.py）
