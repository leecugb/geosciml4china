"""CLI 入口：g4c render --sheet kurgan（或 python -m geosciml4china.render.render）

渲染纪律（方案 R 系）：
- 强制 set_svg_pattern_registry_path（R11，花纹单元）；
- 渲染前断言 pdf_writer._fault_type_overrides == {}（R2 全局态污染）；
- --check-only 先于渲染通过（R6 静默跳过防线）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pymapgis.rendering import render_map_to_pdf
from pymapgis.rendering.pattern_engine import set_svg_pattern_registry_path

from ..sheets import get_sheet, list_sheets
from ..convert import config
from .codemap import DEFAULT_SVG_REGISTRY
from .map_builder import build_geosciml_map
from .mirror import check_consistency


def _render_profile(key: str) -> dict:
    """注册表图幅 → 渲染参数集（配色=stylegen 语义生成件，单源）。"""
    sh = get_sheet(key)
    return dict(lite_dir=str(sh.lite_out),
                l1_dir=str(sh.geojson_l1),
                gml=str(sh.gml_out),
                color_mapping=str(sh.style_generated),
                fault_styles=str(sh.fault_styles_generated),
                out=str(sh.render_out),
                expect_counts=sh.lite_expect_counts)

_ATTITUDE_COLORS = {
    "202001": (40, 40, 40), "202005": (40, 40, 40), "202004": (0, 150, 0),
    "202011": (220, 0, 0), "202007": (220, 0, 0),
    "面理产状": (220, 0, 0), "片麻理产状": (150, 20, 160),
    "地层产状": (40, 40, 40), "片理产状": (40, 40, 40),
    "倒转层理": (0, 150, 0),
}


def render_map_with_overlays(m, out, color_mapping_path, fault_styles_path,
                             overlay_fns=(), bare=True):
    """保留 ax 的薄装配（2026-09-28 起派发循环单源化：pdf_writer.draw_map_layers；
    叠加层绘制原语 100% 复用；字体/aspect/context/bare 逐位对齐）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from pymapgis.rendering.pdf_writer import (
        draw_map_layers, load_color_mapping, load_fault_styles)

    plt.rcParams["font.sans-serif"] = [
        "SimSun", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "custom"
    plt.rcParams["mathtext.rm"] = "SimSun"
    plt.rcParams["mathtext.it"] = "SimSun:italic"
    plt.rcParams["mathtext.bf"] = "SimSun:bold"
    plt.rcParams["mathtext.default"] = "regular"

    mapping = load_color_mapping(color_mapping_path)
    fault_styles = load_fault_styles(fault_styles_path)
    fig, ax = plt.subplots(1, 1, figsize=m.figsize)
    ax.set_aspect("equal")
    ax.set_facecolor("white")

    draw_map_layers(ax, m, mapping, fault_styles, bare=bare)  # 唯一派发循环
    for fn in overlay_fns:
        fn(ax)
    if m.bbox:
        ax.set_xlim(m.bbox[0], m.bbox[2])
        ax.set_ylim(m.bbox[1], m.bbox[3])
    if bare:
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(str(out)) as pdf:
        pdf.savefig(fig, dpi=m.dpi)
    fig.savefig(out.with_suffix(".png"), dpi=m.dpi)
    plt.close(fig)
    return out


def _regen_styles(sheet: str) -> None:
    """F3 样式动态重生（2026-09-28）：stylegen（面元）与 stylegen_fault（断层）
    的生成件缺失或陈旧于输入（lite 视图/DZ-T 色库/overrides/词表映射）时
    自动再生成——「GeoSciML 语义 + dzt0179_color_library → style → 渲染」
    原则工程化。--skip-stylegen 可跳过。"""
    import os
    from . import stylegen as _sg
    from . import stylegen_fault as _sgf

    inputs_poly = [_sg.LIB_PATH, Path(_sg.__file__)]
    inputs_fault = [Path(_sgf.__file__)]
    cfgp, cfgf = _sg.SHEETS[sheet], _sgf.SHEETS[sheet]
    lite_dir = Path(cfgp["lite_dir"])
    inputs_poly += [lite_dir / "geologic_unit_view.geojson", cfgp["overrides"]]
    inputs_fault += [lite_dir / "shear_displacement_structure_view.geojson",
                     cfgf["overrides"]]

    def _stale(out: Path, ins: list[Path]) -> bool:
        if not out.exists():
            return True
        om = out.stat().st_mtime
        return any(p.exists() and p.stat().st_mtime > om for p in ins)

    if _stale(Path(cfgp["out"]), inputs_poly):
        ov = _sg.load_overrides(sheet)
        mapping, report, pending = _sg.generate(sheet, overrides=ov)
        _sg.write_outputs(sheet, mapping, report, pending)
        print(f"F3 样式重生（面元）: {cfgp['out'].name}（单元 {len(report)}，"
              f"pending {len(pending)}）")
    if _stale(Path(cfgf["out"]), inputs_fault):
        out = _sgf.generate(sheet, _sgf.load_overrides(sheet))
        Path(cfgf["out"]).write_text(json.dumps(out, ensure_ascii=False,
                                                indent=2), encoding="utf-8")
        print(f"F3 样式重生（断层）: {cfgf['out'].name}"
              f"（码 {len(out['fault_types'])}）")


def main() -> int:
    ap = argparse.ArgumentParser(prog="geosciml_render.render")
    ap.add_argument("lite_dir", nargs="?", default=None)
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--sheet", choices=[s.key for s in list_sheets()],
                    default="kurgan")
    ap.add_argument("--bare", action="store_true", default=True)
    ap.add_argument("--no-bare", dest="bare", action="store_false")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--no-l1-check", action="store_true",
                    help="跳过 L1 一致性断言（GeoSciML 自足模式）")
    ap.add_argument("--l1-dir", default=None)
    ap.add_argument("--color-mapping", default=None)
    ap.add_argument("--fault-styles", default=None)
    ap.add_argument("--svg-registry", default=DEFAULT_SVG_REGISTRY)
    ap.add_argument("--gml", default=None,
                    help="叠加 GML 语义叠加层（走滑钩线/断层产状测量点/编图矛盾）")
    ap.add_argument("--no-overlay", dest="no_overlay", action="store_true",
                    help="关闭叠加层（纯 lite 底图）")
    ap.add_argument("--no-pattern", action="store_true",
                    help="禁花纹填充（纯色平铺——200dpi 全幅提速约 6×，"
                         "2026-10-03 业务流优化；pattern_engine 单源开关）")
    args = ap.parse_args()

    # 叠加层生产默认（2026-09-29 教训：褶皱修复轮重渲染漏带 --gml 致新幅
    # 测量点层丢失被用户发现）：未显式给 --gml 且该幅 GML 存在→自动叠加；
    # --no-overlay 显式关闭。历史生产调用均显式带 --gml→行为不变。
    # 词表消费（褶皱 fold_class 等）须按幅——入口确定性 init_sheet
    from ..convert import config as _cfg
    _cfg.init_sheet(args.sheet)
    prof = _render_profile(args.sheet)
    if args.no_overlay:
        args.gml = None
    elif not args.gml and Path(prof["gml"]).exists():
        args.gml = prof["gml"]
    lite_dir = args.lite_dir or prof["lite_dir"]
    l1_dir = args.l1_dir or prof["l1_dir"]
    color_mapping = args.color_mapping or prof["color_mapping"]
    fault_styles = args.fault_styles or prof["fault_styles"]

    set_svg_pattern_registry_path(args.svg_registry)
    if args.no_pattern:
        from pymapgis.rendering.pattern_engine import set_pattern_enabled
        set_pattern_enabled(False)
        print("花纹填充: 禁用（纯色平铺加速通道）")

    # L1 一致性断言：L1 目录存在且未显式跳过时执行（镜像核验通道）；
    # 无 L1 时引擎以 GeoSciML 工件自足运行（2026-09-28 全面解耦：
    # 生产渲染不依赖 MapGIS 语义解析产物）
    from pathlib import Path as _P
    _l1_present = (not args.no_l1_check) and l1_dir and _P(l1_dir).exists()
    if _l1_present:
        ok, lines = check_consistency(lite_dir, l1_dir, color_mapping,
                                      expect_counts=prof["expect_counts"])
        for ln in lines:
            print(ln)
        if not ok:
            print("!! 前置一致性断言失败，中止（R6）")
            return 1
    else:
        print("L1 一致性断言跳过（GeoSciML 自足模式 / --no-l1-check）")
    if args.check_only:
        print("check-only 通过")
        return 0

    from pymapgis.rendering import pdf_writer as _pw
    assert getattr(_pw, "_fault_type_overrides", {}) in ({}, None), (
        "全局态污染：_fault_type_overrides 非空（R2）")

    # F3（2026-09-28）：样式动态重生——style 文件缺失或陈旧于输入
    # （lite 视图/色库/overrides 裁定层/词表映射）时自动再生成
    _regen_styles(args.sheet)

    m, report = build_geosciml_map(
        lite_dir, dpi=args.dpi, color_mapping_path=color_mapping,
        title=config.SHEET_TITLE)
    for view, rep in report["layers"].items():
        print(f"  适配 {view}: loaded={rep['loaded']} adapted={rep['count']}"
              + (f" unmapped={rep['unmapped']}" if rep.get("unmapped") else "")
              + (f" bad_geom={rep['bad_geom']}" if rep.get("bad_geom") else ""))
    out = args.output or prof["out"]

    if args.gml:
        # 叠加路径：薄装配 + movementSense/编图矛盾叠加
        from . import adapters, gml_overlay, sources as _src
        import math
        entries = gml_overlay.read_gml_overlays(args.gml)
        feats_s = _src.load_lite_features(
            lite_dir, "shear_displacement_structure_view")
        gdf_s, _ = adapters.adapt_shear_structures(feats_s)
        lat0 = (m.bbox[1] + m.bbox[3]) / 2.0
        lon_m = 111320.0 * math.cos(math.radians(lat0))
        lat_m = 111320.0

        def _ov(ax):
            mpp = ((m.bbox[2] - m.bbox[0]) * lon_m / (m.figsize[0] * m.dpi)
                   if m.bbox else None)
            # 2026-09-28 用户裁定：正/逆运动语义标注停用（断层产状测量点
            # 体系已承担标注职能）；走滑旋向钩线保留（六类测量模式不含
            # 旋向指示）——draw_marks=False 仅画走滑端钩。
            b = gml_overlay.render_movement_sense_overlay(
                ax, entries, gdf_s, lon_m=lon_m, lat_m=lat_m,
                meters_per_px=mpp, draw_marks=False)
            print("走滑钩线叠加:", {k: (len(v) if isinstance(v, list) else v)
                                    for k, v in b.items()})
            c = gml_overlay.render_contradiction_overlay(ax, entries, gdf_s)
            print("编图矛盾叠加:", {k: (len(v) if isinstance(v, list) else v)
                                    for k, v in c.items()})
            # 断层产状测量点符号层（2026-09-27 用户方案，第五视图垂足点位；
            # 样式参照 pymapgis render_fault_aux_layer，尺寸按像素经 mpp 换算）
            from . import fault_measure
            mpts = fault_measure.load_measure_points(lite_dir)
            st = fault_measure.draw_fault_measure_points(
                ax, mpts, gdf_s, lon_m=lon_m, lat_m=lat_m, meters_per_px=mpp)
            print("测量点符号:", st)

        print(f"=== GeoSciML 渲染+GML 叠加（{len(m.layers)} 图层，dpi={args.dpi}）→ {out}")
        render_map_with_overlays(m, out, color_mapping,
                                 fault_styles, overlay_fns=[_ov],
                                 bare=args.bare)
        print("done:", out)
        return 0

    print(f"=== GeoSciML 渲染（{len(m.layers)} 图层，dpi={args.dpi}）→ {out}")
    render_map_to_pdf(m, out, color_mapping_path=color_mapping,
                      fault_styles_path=fault_styles, bare=args.bare)
    print("done:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
