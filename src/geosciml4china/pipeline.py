"""管线三接口（2026-10-06 用户裁定）：geosciml4china 管线整体分三个接口。

  **接口一 prepare**  检验项目文件完整性（11 文件契约预检）+ 完成地质语义
      标定（L0 转换 → 九域自支持标定 → 两相物化 → 缺口报告），生成
      **codebook**（编码-地质语义映射表 JSON，用户可改）。
  **接口二 convert**  按照 codebook 完成 GeoSciML 转换（stylegen → build
      → verify：GML + Lite 六视图 + pending，XSD + 29 业务断言）。
  **接口三 render**   完成 GeoSciML 渲染（DZ/T 0179-2025 样式 + 叠加层 +
      C1-C7 L1 镜像核验）。

接口正交可独立执行（codebook 编辑后只需重跑接口二；产品重建后只需重跑
接口三）；``run_pipeline`` = 三接口顺序编排（向后兼容原 g4c pipeline）。

CLI:
  g4c prepare --sheet K [--skip-convert] [--skip-calibrate-stages]
  g4c convert --sheet K [--accept-portrait]
  g4c render  --sheet K [--dpi N] [--no-pattern] [--no-overlay] [--full-extent]
  g4c pipeline --sheet K [全链，参数兼容]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .sheets import get_sheet, list_sheets


def prepare(sheet_key: str, *, skip_convert=False,
            skip_calibrate_stages=False) -> int:
    """接口一：完整性检验 + 地质语义标定 + codebook 生成。"""
    sh = get_sheet(sheet_key)
    print(f"=== g4c prepare：{sh.title}（{sh.root}）===")

    # ⓪ 图幅预检（2026-09-29 用户裁定：处理图幅前先查 11 文件完整性；
    # CORE 缺即中止，CONDITIONAL 缺声明登记继续）
    from .preflight import check_scope_files, format_report
    ok, rows = check_scope_files(sheet_key)
    print(format_report(sheet_key, rows))
    if not ok:
        print("!! 预检失败（CORE 层缺失），中止")
        return 1

    # ① convert：MapGIS → L0（profile 须在——pymapgis PROFILES 注册驱动）
    if not skip_convert:
        from pymapgis.semantics import convert_sheet, validate_l0
        from pymapgis.semantics.profile import PROFILES, write_profile
        if sh.key not in PROFILES:
            print(f"!! 图幅剖面未注册（pymapgis.semantics.profile.PROFILES 缺 "
                  f"{sh.key!r}）——先注册剖面再跑 prepare")
            return 2
        # 增量跳过（2026-10-05 泛化提速）：L0 全部产物新于全部源文件时
        # 免转——check-only 重跑/回填画像二跑的转换阶段零成本
        _l0dir = sh.root / "geojson" / "L0"
        _raws = [p for p in sh.root.iterdir()
                 if p.is_file() and p.suffix in (".WL", ".WP", ".WT")]
        _l0s = list(_l0dir.glob("*.geojson")) if _l0dir.exists() else []
        _stale = (not _raws or not _l0s
                  or min(p.stat().st_mtime for p in _l0s)
                  < max(p.stat().st_mtime for p in _raws))
        if _stale:
            print("① MapGIS → L0 转换")
            convert_sheet(sh.root)
            write_profile(sh.key, sh.root)
            if not validate_l0(sh.root):
                print("!! L0 校验失败，中止")
                return 1
        else:
            print("① 跳过（L0 新于源文件——增量通道；--skip-convert 同效）")
    else:
        print("① 跳过（--skip-convert）")

    # ② 自支持地质语义判别解析（geosciml4china.calibrate 六域全包原生，
    # 2026-10-02 用户对齐定版）——两相物化：基线 L1（实体/辅助链消费源）
    # → 实体/辅助链 → gzeeb/产状/化石/推测断层 → 终态 L1
    from pymapgis.semantics.materialize import materialize_sheet
    if skip_calibrate_stages:
        print("② 跳过（--skip-calibrate-stages）")
        # 映射表陈旧守卫（2026-10-04 修改-再转化回路）：用户编辑映射表后
        # 须先重跑对应标定域使编辑生效——物化前检测并提醒
        for _map_name, _cal_name, _cmd in (
                (f"code_semantics_map_{sh.key}.csv",
                 f"_gzeeb_calibration_{sh.key}.csv", "calibrate-gzeeb"),
                (f"gzeld_semantics_map_{sh.key}.csv",
                 f"_gzeeb_calibration_{sh.key}.csv", "calibrate-gzeeb"),
                (f"boundary_semantics_map_{sh.key}.csv",
                 f"_gzbd_semantic_interpretation.csv", "calibrate-gzbd")):
            _map_p = sh.root / _map_name
            _cal_p = sh.root / _cal_name
            if _map_p.exists() and _cal_p.exists() \
                    and _map_p.stat().st_mtime > _cal_p.stat().st_mtime + 60:
                print(f"⚠ {_map_name} 新于校准件——若刚编辑映射表，"
                      f"请先重跑 g4c {_cmd} --sheet {sh.key} 再继续"
                      f"（否则本次物化沿用旧语义）")
        print("②b L1 物化")
        materialize_sheet(sh.root)
    else:
        from .calibrate.gzbd import calibrate_boundaries
        from .calibrate.entities import calibrate_entities
        from .calibrate.auxchain import calibrate_auxchain
        from .calibrate.gzeeb import calibrate_faults
        from .calibrate.attitudes import calibrate_attitudes
        from .calibrate.fossils import calibrate_fossils
        from .calibrate.folds import calibrate_folds
        from .calibrate.inferred_faults import calibrate_inferred_faults
        print("② 自支持地质语义判别解析")
        calibrate_boundaries(sh.key)               # 界线（GZBD）
        print("②a 基线 L1 物化（实体/辅助链消费源）")
        materialize_sheet(sh.root)
        calibrate_entities(sh.key)                 # 断层归组（实体）
        calibrate_auxchain(sh.key)                 # 辅助点实体链判别
        calibrate_entities(sh.key,                 # aux 写回（A1）
                          triplets_csv=f"_fault_triplets_{sh.key}.csv",
                          triplet_attitude_csv=f"_fault_triplets_{sh.key}.csv")
        from .calibrate.fault_contact_activity import \
            calibrate_fault_contact_activity
        calibrate_fault_contact_activity(sh.key)   # 断裂接触审计兜底（活动断层判别；
        # 2026-10-02 A7：置于实体归组之后——候选归因需 fault_entities 表）
        calibrate_faults(sh.key)                   # 断层三维（GZEEB）
        calibrate_attitudes(sh.key)                # 产状类型
        calibrate_fossils(sh.key)                  # 化石/泥火山
        calibrate_folds(sh.key)                    # 褶皱（词表码义标定域，
        # 2026-10-03 六步架构第三步正式化：先验知识驱动，无段级证据通道
        # 不构成 MLE 回归——码义命中即标定，未注册码待裁定）
        calibrate_inferred_faults(sh.key)          # 推测断层（覆盖度核定）
        print("②b 终态 L1 物化（语义标定写回 geojson/L1）")
        materialize_sheet(sh.root)

    # ②c 缺口报告（2026-10-03 用户裁定：缺口兜底保障管线 + 文字报告
    # + 单要素渲染配图，供后期专家裁决）——两条路径汇聚点统一执行
    # （2026-10-04 再审修复：原仅全标定分支调用，--skip-calibrate-stages
    # 路径从不刷新——编辑-再转化回路迭代裁定时核验卡陈旧）
    from .render.gap_report import build_gap_report
    build_gap_report(sh.key)

    # ②d codebook（2026-10-06 用户裁定：校准完成后以 JSON 输出编码-地质
    # 语义映射表；用户可改 JSON；后续 GeoSciML 转换建立在 codebook 上——
    # 这个 JSON 就是 codebook。用户编辑跨轮保留；两路径汇聚点统一生成）
    from .calibrate.codebook import build_codebook, summary as _cb_summary
    print("②d codebook（编码-地质语义映射表 JSON = codebook）")
    print(_cb_summary(build_codebook(sh.key)))
    return 0


def convert(sheet_key: str, *, accept_portrait=False) -> int:
    """接口二：按照 codebook 完成 GeoSciML 转换（stylegen → build → verify）。"""
    sh = get_sheet(sheet_key)
    print(f"=== g4c convert：{sh.title}（按 codebook 转换 GeoSciML）===")

    # ③ stylegen（lite 优先；缺 lite 走 WP 引导——新幅首接通道）
    from .render import stylegen as _sg
    lite_unit = sh.lite_out / "geologic_unit_view.geojson"
    print(f"③ 样式生成（{'lite 语义源' if lite_unit.exists() else 'WP 引导'}）")
    mapping, report, pending = _sg.generate(
        sheet_key, _sg.Lib(), _sg.load_overrides(sheet_key),
        source=("lite" if lite_unit.exists() else "wp"))
    _sg.write_outputs(sheet_key, mapping, report, pending)

    # ④ build
    from .convert import build as _build
    print("④ GeoSciML build")
    _saved = sys.argv
    sys.argv = ["g4c build", "--sheet", sheet_key]
    try:
        if _build.main() != 0:
            return 1
    finally:
        sys.argv = _saved

    # ④b 断层样式（语义源=lite SDS 视图，build 后必有）
    from .render import stylegen_fault as _sgf
    out_f = _sgf.generate(sheet_key, _sgf.load_overrides(sheet_key))
    Path(sh.fault_styles_generated).write_text(
        json.dumps(out_f, ensure_ascii=False, indent=2), encoding="utf-8")

    # ⑤ verify
    from .convert import verify as _verify
    print("⑤ verify")
    _saved = sys.argv
    sys.argv = ["g4c verify", "--sheet", sheet_key]
    if accept_portrait:
        sys.argv.append("--accept-portrait")
    try:
        return _verify.main()
    finally:
        sys.argv = _saved


def render_stage(sheet_key: str, *, dpi=200, no_pattern=False) -> int:
    """接口三：完成 GeoSciML 渲染（叠加层生产默认 + L1 镜像核验）。"""
    sh = get_sheet(sheet_key)
    print(f"=== g4c render：{sh.title}（GeoSciML 渲染）===")
    from .render import render as _render
    _saved = sys.argv
    sys.argv = ["g4c render", "--sheet", sheet_key, "--dpi", str(dpi)]
    if no_pattern:
        sys.argv.append("--no-pattern")
    try:
        return _render.main()
    finally:
        sys.argv = _saved


def run_pipeline(sheet_key: str, *, skip_convert=False, skip_calibrate_stages=False,
                 skip_render=False, check_only=False, dpi=200,
                 no_pattern=False, accept_portrait=False) -> int:
    """全链 = 三接口顺序编排（向后兼容原 g4c pipeline 参数面）。"""
    rc = prepare(sheet_key, skip_convert=skip_convert,
                 skip_calibrate_stages=skip_calibrate_stages)
    if rc != 0:
        return rc
    rc = convert(sheet_key, accept_portrait=accept_portrait)
    if rc != 0 or check_only:
        return rc
    if skip_render:
        print("⑥ 跳过（--skip-render）")
        return 0
    return render_stage(sheet_key, dpi=dpi, no_pattern=no_pattern)


def prepare_main() -> int:
    ap = argparse.ArgumentParser(prog="g4c prepare")
    ap.add_argument("--sheet", choices=[s.key for s in list_sheets()],
                    required=True)
    ap.add_argument("--skip-convert", action="store_true")
    ap.add_argument("--skip-calibrate-stages", action="store_true",
                    help="跳过标定阶段脚本（仅物化+codebook——基线/调试通道）")
    args = ap.parse_args()
    return prepare(args.sheet, skip_convert=args.skip_convert,
                   skip_calibrate_stages=args.skip_calibrate_stages)


def convert_main() -> int:
    ap = argparse.ArgumentParser(prog="g4c convert")
    ap.add_argument("--sheet", choices=[s.key for s in list_sheets()],
                    required=True)
    ap.add_argument("--accept-portrait", action="store_true",
                    help="首次画像接受：verify 落盘画像并 exit 0（消除 re-run）")
    args = ap.parse_args()
    return convert(args.sheet, accept_portrait=args.accept_portrait)


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c pipeline")
    ap.add_argument("--sheet", choices=[s.key for s in list_sheets()],
                    required=True)
    ap.add_argument("--skip-convert", action="store_true")
    ap.add_argument("--skip-calibrate-stages", action="store_true",
                    help="跳过标定阶段脚本（仅物化+核验——基线/调试通道）")
    ap.add_argument("--skip-render", action="store_true")
    ap.add_argument("--check-only", action="store_true", help="止于 verify")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--no-pattern", action="store_true",
                    help="渲染禁花纹填充（纯色平铺加速）")
    ap.add_argument("--accept-portrait", action="store_true",
                    help="首次画像接受：verify 落盘画像并 exit 0（消除 re-run）")
    args = ap.parse_args()
    return run_pipeline(args.sheet, skip_convert=args.skip_convert,
                        skip_calibrate_stages=args.skip_calibrate_stages,
                        skip_render=args.skip_render, check_only=args.check_only,
                        dpi=args.dpi, no_pattern=args.no_pattern,
                        accept_portrait=args.accept_portrait)


if __name__ == "__main__":
    sys.exit(main())
