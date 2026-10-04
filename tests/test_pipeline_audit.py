# -*- coding: utf-8 -*-
"""geosciml4china 全管线审计（2026-10-02 用户指令「审计 geosciml4china 全管线」）。

基准（2026-10-02 用户对齐链 verbatim）：检查 MapGIS 文件完整性 → 转 L0
geojson → 自支持地质语义判别逻辑解析生成 L1 → 转 GeoSciML → 基于地质
语义的 GeoSciML 渲染引擎成图。

方法=静态行证+联通性核验：
  ① 阶段序与对齐链逐字对应（源码调用序解析）；
  ② 逐段失败即中止（每阶段失败 return 非零）；
  ③ 产出-消费文件链（各标定模块产出文件名=下游装载文件名）；
  ④ CLI 命令表覆盖全部阶段。
"""
import ast
import inspect
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "geosciml4china"


def _func_src(module, name):
    return inspect.getsource(getattr(module, name))


def test_pipeline_stage_order():
    """① 阶段序：preflight→convert→五域→materialize→stylegen→build→verify→render。"""
    from geosciml4china import pipeline
    src = _func_src(pipeline, "run_pipeline")
    chain = [
        ("preflight.check_scope_files", "check_scope_files"),
        ("convert_sheet", "convert_sheet"),
        ("gzbd.calibrate_boundaries", "calibrate_boundaries"),
        ("entities.calibrate_entities", "calibrate_entities"),
        ("auxchain.calibrate_auxchain", "calibrate_auxchain"),
        ("entities writeback", "triplets_csv"),
        ("gzeeb.calibrate_faults", "calibrate_faults"),
        ("attitudes.calibrate_attitudes", "calibrate_attitudes"),
        ("fossils.calibrate_fossils", "calibrate_fossils"),
        ("materialize_sheet", "materialize_sheet"),
        ("stylegen.generate", "_sg.generate"),
        ("build.main", "_build.main"),
        ("verify.main", "_verify.main"),
        ("render.main", "_render.main"),
    ]
    pos = -1
    for label, needle in chain:
        i = src.find(needle, pos + 1)
        assert i > pos, f"阶段缺序：{label}（{needle}）不在 pipeline 调用序中"
        pos = i


def test_pipeline_fail_stop():
    """② 逐段失败即中止：每关键阶段失败路径 return 非零。"""
    from geosciml4china import pipeline
    src = _func_src(pipeline, "run_pipeline")
    assert "!! 预检失败（CORE 层缺失），中止" in src
    assert "return 1" in src
    assert "!! L0 校验失败，中止" in src
    # 五域阶段块后仍有物化与后续阶段（非空跳过）
    i_mat = src.index("materialize_sheet")
    i_build = src.index("_build.main")
    assert i_mat < i_build, "物化须先于 build"


def test_producer_consumer_files():
    """③ 产出-消费文件链：各标定模块写出的文件名=下游装载文件名。"""
    from geosciml4china.calibrate import (attitudes, auxchain, entities,
                                          fossils, gzeeb, gzbd)

    def _writes(mod_src, names):
        for n in names:
            assert n in mod_src, f"{n} 未写出"

    # gzbd → 五表（materialize 消费）
    _writes(inspect.getsource(gzbd), ["_boundary_sides.csv"])
    # entities → fault_entities_<key>.csv（auxchain/gzeeb 装载）
    es = inspect.getsource(entities.calibrate_entities)
    assert "fault_entities" in es
    # auxchain → assoc/triplets/hooks（写回/gzeeb/build 装载）
    as_ = inspect.getsource(auxchain.calibrate_auxchain)
    for n in ("fault_aux_", "_fault_triplets_", "_fault_hooks_"):
        assert n in as_, f"auxchain 未写 {n}"
    # gzeeb → _gzeeb_calibration_<key>.csv
    gs = inspect.getsource(gzeeb.calibrate_faults)
    assert "_gzeeb_calibration_" in gs
    # attitudes → _attitude_calibration.csv
    ats = inspect.getsource(attitudes.calibrate_attitudes)
    assert "_attitude_calibration.csv" in ats
    # fossils → _fossil_calibration_<key>.csv
    fs = inspect.getsource(fossils.calibrate_fossils)
    assert "_fossil_calibration_" in fs


def test_downstream_loads():
    """③b 下游装载：gzeeb/build 消费的文件名与上游产出一致。"""
    from geosciml4china.calibrate import gzeeb
    gs = inspect.getsource(gzeeb.calibrate_faults)
    # gzeeb 装载 entities 表 + aux 表 + hooks 表
    assert "entities_csv" in gs or "fault_entities" in gs
    assert "fault_aux_" in gs
    assert "_fault_hooks_" in gs
    # build 消费 hooks 表 + 段级 se 列
    from geosciml4china.convert import build as _b
    bs = inspect.getsource(_b.assemble_faults)
    assert "_fault_hooks_" in bs
    assert "slip_by_seg" in bs
    # build 消费 gzeeb 表（经 L1 faults gzeeb_eff/checks 列）
    assert "gzeeb_eff" in bs


def test_cli_commands_complete():
    """④ CLI 命令表覆盖全部阶段与五域。"""
    from geosciml4china import cli
    src = Path(cli.__file__).read_text(encoding="utf-8")
    for cmd in ("pipeline", "check", "sheets", "calibrate-gzbd", "entities",
                "auxchain", "calibrate-gzeeb", "calibrate-attitudes",
                "calibrate-fossils", "stylegen", "stylegen-fault", "build",
                "verify", "render"):
        assert cmd in src, f"CLI 缺命令 {cmd}"


def test_pipeline_ast_valid():
    """pipeline.py 语法有效且 run_pipeline 定义完整。"""
    tree = ast.parse((SRC / "pipeline.py").read_text(encoding="utf-8"))
    fns = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert "run_pipeline" in fns and "main" in fns
