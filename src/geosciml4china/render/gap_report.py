# -*- coding: utf-8 -*-
"""标定缺口报告生成器（2026-10-03 用户裁定：标定存在缺口时以兜底机制
处理保障管线运行，同时记录报告（文字 + 单要素渲染配图），方便后期专家
裁决）。

缺口集合（图幅标定产物）：
  1. GZBD 先验缺口候选（_gzbd_gap_candidates_<key>.csv）
  2. GZBD 分歧段（_gzbd_calibration_report.csv verdict=分歧）
  3. 断层冲突/待裁定（_gzeeb_conflicts_<key>.csv pending_review）
  4. 断层矛盾保留行（_gzeeb_calibration_<key>.csv verdict=标定（矛盾保留））
  5. 一般断层兜底行（_gzeeb_fallback_<key>.csv，继承后可能为空）
  6. 码义提案（_gzeeb_code_semantics_proposal_<key>.csv——文字节）

产出：<out>/geosciml/gap_report/ ——
  index.md（文字报告+索引）、cards/*.pdf（每类一份多页 PDF，单要素一页：
  要素线高亮 + 周边面元按 L1 配色填充 + 单元名/时代标注 + 缺口缘由标题）。
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import geopandas as gpd

from ..sheets import get_sheet
from ..convert import config, ids


def _polygon_patch(fc_rgb):
    try:
        r, g, b = (int(x) for x in fc_rgb.strip("[]()").split(","))
        return (r / 255.0, g / 255.0, b / 255.0, 0.55)
    except Exception:
        return (0.9, 0.9, 0.9, 0.55)


def _card(ax, elem_geom, context, title, elem_color=(0.85, 0.05, 0.05),
          lw=3.0):
    """单要素卡片：周边面元填充 + 单元标注 + 要素线高亮 + 标题。"""
    for _, p in context.iterrows():
        g = p.geometry
        if g is None or g.is_empty:
            continue
        fc = _polygon_patch(str(p.get("fill_color") or ""))
        if g.geom_type == "Polygon":
            xs, ys = g.exterior.xy
            ax.fill(xs, ys, facecolor=fc, edgecolor="none", zorder=1)
        elif g.geom_type == "MultiPolygon":
            for sub in g.geoms:
                xs, ys = sub.exterior.xy
                ax.fill(xs, ys, facecolor=fc, edgecolor="none", zorder=1)
        cen = g.representative_point()
        ax.text(cen.x, cen.y, f"{p.get('QDUECD','')}({p.get('unit_age_rank','')})",
                fontsize=4.5, ha="center", va="center", zorder=2,
                bbox=dict(boxstyle="round,pad=0.1", fc="white",
                          ec="gray", alpha=0.7))
    if elem_geom is not None and not elem_geom.is_empty:
        if elem_geom.geom_type == "LineString":
            xs, ys = elem_geom.xy
            ax.plot(list(xs), list(ys), color=elem_color, linewidth=lw,
                    zorder=3, solid_capstyle="round")
        else:
            xs, ys = elem_geom.exterior.xy
            ax.plot(list(xs), list(ys), color=elem_color, linewidth=lw,
                    zorder=3)
    ax.set_title(title, fontsize=7)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def _multi_page_pdf(cards, out_pdf, figsize=(6.4, 4.8), dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    plt.rcParams["font.sans-serif"] = [
        "SimSun", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    with PdfPages(str(out_pdf)) as pdf:
        for title, draw in cards:
            fig, ax = plt.subplots(1, 1, figsize=figsize)
            ax.set_aspect("equal")
            ax.set_facecolor("white")
            draw(ax)
            pdf.savefig(fig, dpi=dpi)
            plt.close(fig)
    return out_pdf


def build_gap_report(sheet_key: str, out_dir=None) -> dict:
    sh = get_sheet(sheet_key)
    config.init_sheet(sheet_key)
    # sh.out_dir 已是 output/geosciml——不再追加 geosciml 段
    out_dir = Path(out_dir or sh.out_dir)
    rpt_dir = out_dir / "gap_report"
    cards_dir = rpt_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    pol = gpd.read_file(str(sh.geojson_l1 / "polygons.geojson"))
    bnd = gpd.read_file(str(sh.geojson_l1 / "boundaries.geojson"))
    flt = gpd.read_file(str(sh.geojson_l1 / "faults.geojson"))
    seg_ord = ids.fault_seg_ordinals(flt)

    stats = {}
    sections = []

    def _ctx(geom, buf=0.02):
        if geom is None or geom.is_empty:
            return pol.iloc[0:0]
        return pol[pol.intersects(geom.buffer(buf))]

    # ---- 1. GZBD 先验缺口候选 ----
    gap_p = Path(sh.root) / f"_gzbd_gap_candidates_{sh.key}.csv"
    if gap_p.exists():
        with open(gap_p, encoding="utf-8-sig") as f:
            gaps = list(csv.DictReader(f))
        cards = []
        for g in gaps:
            try:
                i = int(g.get("idx") or g.get("段") or -1)
            except (TypeError, ValueError):
                continue
            row = bnd[bnd["_src_id"].astype(int) == i] if len(bnd) else bnd
            if len(row) == 0:
                continue
            geom = row.iloc[0].geometry
            reason = "；".join(str(v) for k, v in g.items()
                               if v and k not in ("idx", "段"))
            title = (f"GZBD 先验缺口候选 段{i}（{g.get('gzbd','')}）"
                     f"：{reason[:70]}")
            cards.append((title, lambda ax, gm=geom, g=g, t=title:
                          _card(ax, gm, _ctx(gm), t,
                                elem_color=(0.0, 0.0, 0.6))))
        if cards:
            p = _multi_page_pdf(cards, cards_dir / "gzbd_gap_candidates.pdf")
            stats["gzbd_gap_candidates"] = len(cards)
            sections.append(f"## GZBD 先验缺口候选（{len(cards)} 段）\n"
                            f"配图：`cards/gzbd_gap_candidates.pdf`")

    # ---- 2. GZBD 分歧段 ----
    cal_p = Path(sh.root) / f"_gzbd_calibration_report.csv"
    if cal_p.exists():
        with open(cal_p, encoding="utf-8-sig") as f:
            div = [r for r in csv.DictReader(f) if "分歧" in str(r.get("verdict"))]
        cards = []
        for g in div:
            try:
                i = int(g.get("idx") or -1)
            except (TypeError, ValueError):
                continue
            row = bnd[bnd["_src_id"].astype(int) == i]
            if len(row) == 0:
                continue
            geom = row.iloc[0].geometry
            title = (f"GZBD 分歧 段{i}（{g.get('gzbd','')}，"
                     f"{g.get('rule_conf','')}）")
            cards.append((title, lambda ax, gm=geom, g=g, t=title:
                          _card(ax, gm, _ctx(gm), t,
                                elem_color=(0.7, 0.4, 0.0))))
        if cards:
            p = _multi_page_pdf(cards, cards_dir / "gzbd_divergence.pdf")
            stats["gzbd_divergence"] = len(cards)
            sections.append(f"## GZBD 分歧段（{len(cards)} 段）\n"
                            f"配图：`cards/gzbd_divergence.pdf`")

    # ---- 3+4. 断层冲突册 + 矛盾保留行 ----
    gz_p = Path(sh.root) / f"_gzeeb_calibration_{sh.key}.csv"
    if gz_p.exists():
        with open(gz_p, encoding="utf-8-sig") as f:
            gz = list(csv.DictReader(f))
        conf = [r for r in gz if str(r.get("verdict")).startswith("标定（矛盾保留）")]
        cards = []
        for r in conf:
            i = int(r["idx"])
            row = flt[flt["_src_id"].astype(int) == i]
            if len(row) == 0:
                continue
            geom = row.iloc[0].geometry
            fid, o = seg_ord[i]
            title = (f"{fid}.{o} {r['structural_type']} 矛盾保留："
                     f"{str(r.get('checks'))[:70]}")
            cards.append((title, lambda ax, gm=geom, r=r, t=title:
                          _card(ax, gm, _ctx(gm), t,
                                elem_color=(0.8, 0.1, 0.1))))
        if cards:
            p = _multi_page_pdf(cards, cards_dir / "fault_conflicts.pdf")
            stats["fault_conflicts"] = len(cards)
            sections.append(f"## 断层矛盾保留（{len(cards)} 段）\n"
                            f"配图：`cards/fault_conflicts.pdf`")

    # ---- 5. 兜底（继承后可能为空）----
    fb_p = Path(sh.root) / f"_gzeeb_fallback_{sh.key}.csv"
    fb_n = 0
    if fb_p.exists():
        with open(fb_p, encoding="utf-8-sig") as f:
            fb = list(csv.DictReader(f))
        fb_n = len(fb)
        cards = []
        for r in fb:
            i = int(r["idx"])
            row = flt[flt["_src_id"].astype(int) == i]
            if len(row) == 0:
                continue
            geom = row.iloc[0].geometry
            fid, o = seg_ord[i]
            title = f"{fid}.{o} 一般断层兜底（{r.get('GZEEB','')}）"
            cards.append((title, lambda ax, gm=geom, r=r, t=title:
                          _card(ax, gm, _ctx(gm), t,
                                elem_color=(0.4, 0.4, 0.4))))
        if cards:
            _multi_page_pdf(cards, cards_dir / "fault_fallback.pdf")
    stats["fault_fallback"] = fb_n

    # ---- 6. 码义提案（文字节）----
    prop_p = Path(sh.root) / f"_gzeeb_code_semantics_proposal_{sh.key}.csv"
    prop_txt = ""
    if prop_p.exists():
        with open(prop_p, encoding="utf-8-sig") as f:
            prop = list(csv.DictReader(f))
        for r in prop:
            prop_txt += (f"- **GZEEB={r['GZEEB']}**（{r['segs']} 段）："
                         f"mle_semantic={r.get('mle_semantic','')}；"
                         f"final={r.get('final_distribution','')[:80]}\n")
        sections.append("## GZEEB 码义提案（逻辑判断已继承，注册表待裁定）\n"
                        + prop_txt)

    # ---- 索引报告 ----
    lines = [f"# {sh.title} 标定缺口报告（{sh.key}）", "",
             "> 生成：2026-10-03 · 原则：缺口以兜底机制处理保障管线运行，"
             "本报告（文字 + 单要素渲染配图）供后期专家裁决。", ""]
    for s in sections:
        lines.append(s)
        lines.append("")
    lines.append(f"## 统计\n```json\n{json.dumps(stats, ensure_ascii=False, indent=1)}\n```")
    (rpt_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"缺口报告: {rpt_dir / 'index.md'}（{stats}）")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(prog="gap_report")
    ap.add_argument("--sheet", required=True)
    args = ap.parse_args()
    build_gap_report(args.sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
