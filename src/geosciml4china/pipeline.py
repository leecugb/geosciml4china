"""全链编排器（2026-09-29 全链范围裁定）：MapGIS 工程文件夹 → 标定 → 转换 → 渲染。

阶段序（管线纪律，逐段失败即中止）：
  ① convert       MapGIS 原生 → geojson/L0（pymapgis.semantics.convert_sheet + validate_l0）
  ② calibrate     L0 → 标定阶段链 → geojson/L1（pymapgis.semantics.calibrate_semantics；
                  图幅剖面 l1_stages 驱动；标定规则库 geosciml4china.calibrate 渐进迁入）
  ②a entities/auxchain 断层归组（登记册+G2）→ 辅助点实体链判别（全裁定）
        → 写回 → L1 重物化
  ③ stylegen      语义→样式（lite 优先；lite 缺失时 --from-wp 引导——新幅首接）
  ④ build         L1 → GML + Lite + pending（含断层样式生成：其语义源=lite SDS 视图）
  ⑤ verify        XSD + 业务断言
  ⑥ render        渲染 + L1 镜像核验（叠加层生产默认）

CLI: g4c pipeline --sheet <key> [--skip-convert] [--skip-calibrate-stages]
     [--skip-render] [--check-only（止于 verify）] [--dpi N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .sheets import get_sheet, list_sheets


def run_pipeline(sheet_key: str, *, skip_convert=False, skip_calibrate_stages=False,
                 skip_render=False, check_only=False, dpi=200) -> int:
    sh = get_sheet(sheet_key)
    print(f"=== g4c pipeline：{sh.title}（{sh.root}）===")

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
                  f"{sh.key!r}）——先注册剖面再跑 pipeline")
            return 2
        print("① MapGIS → L0 转换")
        convert_sheet(sh.root)
        write_profile(sh.key, sh.root)
        if not validate_l0(sh.root):
            print("!! L0 校验失败，中止")
            return 1
    else:
        print("① 跳过（--skip-convert）")

    # ② calibrate：标定阶段链 + 物化 L1 + 核验（pymapgis 编排器）
    from pymapgis.semantics.calibrate import calibrate_semantics
    print("② 标定阶段链 + L1 物化")
    if not calibrate_semantics(sh.root, skip_stages=skip_calibrate_stages):
        print("!! 标定/物化/核验失败，中止")
        return 1

    # ②a 断层实体归组（四步链第①步）+ 辅助点实体链判别（第②③④步）
    from .calibrate.entities import calibrate_entities
    from .calibrate.auxchain import calibrate_auxchain
    from pymapgis.semantics.materialize import materialize_sheet
    print("②a 断层归组 + 辅助点实体链判别")
    calibrate_entities(sh.key)
    calibrate_auxchain(sh.key)
    calibrate_entities(sh.key, triplets_csv=f"_fault_triplets_{sh.key}.csv",
                       triplet_attitude_csv=f"_fault_triplets_{sh.key}.csv")
    materialize_sheet(sh.root)  # 重物化（实体/aux 判别写回进 L1）

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
    import json as _json
    out_f = _sgf.generate(sheet_key, _sgf.load_overrides(sheet_key))
    Path(sh.fault_styles_generated).write_text(
        _json.dumps(out_f, ensure_ascii=False, indent=2), encoding="utf-8")

    # ⑤ verify
    from .convert import verify as _verify
    print("⑤ verify")
    _saved = sys.argv
    sys.argv = ["g4c verify", "--sheet", sheet_key]
    try:
        rc = _verify.main()
    finally:
        sys.argv = _saved
    if rc != 0 or check_only:
        return rc

    # ⑥ render（叠加层生产默认）
    if skip_render:
        print("⑥ 跳过（--skip-render）")
        return 0
    from .render import render as _render
    print("⑥ render（叠加层）")
    _saved = sys.argv
    sys.argv = ["g4c render", "--sheet", sheet_key, "--dpi", str(dpi)]
    try:
        return _render.main()
    finally:
        sys.argv = _saved


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
    args = ap.parse_args()
    return run_pipeline(args.sheet, skip_convert=args.skip_convert,
                        skip_calibrate_stages=args.skip_calibrate_stages,
                        skip_render=args.skip_render, check_only=args.check_only,
                        dpi=args.dpi)


if __name__ == "__main__":
    sys.exit(main())
