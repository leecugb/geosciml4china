"""镜像验证（geosciml_render）。

--check-only 前置一致性断言（渲染前必过）：Lite 视图 vs L1 语义层。
像素级镜像对账在 P2（render_map_to_pdf 双数据源同路径+掩膜归类差分）。
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import geopandas as gpd

from . import adapters, sources
from ..convert.ids import CONTACT_CODES
from .codemap import build_reverse_unit_map, feature_id, hex_to_rgb

ND = 12  # 几何比对舍入（1e-12°，repr 14 位精度内，F2 实测零误差）


def _geom_key(g) -> tuple:
    """几何→可哈希坐标多重集键（多边形含孔）。"""
    def ring(cs):
        return tuple((round(x, ND), round(y, ND)) for x, y in cs)
    if g.geom_type == "Point":
        return ("P", round(g.x, ND), round(g.y, ND))
    if g.geom_type == "LineString":
        return ("L", ring(g.coords))
    if g.geom_type == "Polygon":
        return ("PG", ring(g.exterior.coords),
                tuple(sorted(ring(r.coords) for r in g.interiors)))
    if g.geom_type == "MultiPolygon":
        return ("MP", tuple(sorted(
            (ring(p.exterior.coords),
             tuple(sorted(ring(r.coords) for r in p.interiors)))
            for p in g.geoms)))
    raise ValueError(f"unsupported geom {g.geom_type}")


def _multiset(gdf) -> Counter:
    return Counter(_geom_key(g) for g in gdf.geometry)


def check_consistency(lite_dir: str | Path,
                      l1_dir: str | Path,
                      color_mapping_path: str | Path,
                      expect_counts: tuple = (713, 1316, 310, 305),
                      ) -> tuple[bool, list[str]]:
    """6 项前置一致性断言。返回 (ok, 行报告)。

    expect_counts: (面, 界线, 断层, 产状)——库尔干 (713,1317,310,305)；
    英吉沙 (808,1199,289,165)。其余断言全数据驱动。
    """
    lines: list[str] = []
    ok_all = True

    def rep(tag: str, ok: bool, detail: str):
        nonlocal ok_all
        ok_all = ok_all and ok
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {tag} — {detail}")

    l1_dir = Path(l1_dir)
    l1_poly = gpd.read_file(l1_dir / "polygons.geojson")
    l1_bnd = gpd.read_file(l1_dir / "boundaries.geojson")
    l1_flt = gpd.read_file(l1_dir / "faults.geojson")
    l1_att = gpd.read_file(l1_dir / "attitude.geojson")

    gzbd_eff = l1_bnd["GZBD_eff"].astype(str).str.replace(".0", "", regex=False).str.zfill(2)
    # B1 对齐（2026-09-28）：Lite 侧剔除制图误差行后，L1 侧同口径过滤
    # status=excluded（此前 M2 掩膜承载的差异现为双侧一致排除）
    is_excl = l1_bnd["status"].astype(str) == "excluded"
    conv8 = l1_bnd[gzbd_eff.isin(list(CONTACT_CODES))
                   & ~is_excl]

    feats_u = sources.load_lite_features(lite_dir, "geologic_unit_view")
    feats_c = sources.load_lite_features(lite_dir, "contact_view")
    feats_s = sources.load_lite_features(lite_dir, "shear_displacement_structure_view")
    feats_a = sources.load_lite_features(lite_dir, "site_observation_view")

    # ① 计数
    counts = (len(feats_u), len(feats_c), len(feats_s), len(feats_a))
    rep("C1 要素计数", counts == expect_counts,
        f"面/界线/断层/产状 = {counts}（L1 侧 {len(l1_poly)}/{len(conv8)}/{len(l1_flt)}/{len(l1_att)}，"
        f"期望 {expect_counts}）")

    # 适配（供后续断言复用）
    rmap = build_reverse_unit_map(color_mapping_path)
    from .codemap import zorder_table
    gdf_u, rep_u = adapters.adapt_geologic_units(feats_u, rmap, zorder_table())
    gdf_c, _ = adapters.adapt_contacts(feats_c)
    gdf_s, _ = adapters.adapt_shear_structures(feats_s)
    gdf_a, _ = adapters.adapt_site_observations(feats_a)

    # ② 几何多重集相等
    geo_ok = True
    details = []
    for name, a_gdf, b_gdf in (("面", gdf_u, l1_poly), ("界线", gdf_c, conv8),
                               ("断层", gdf_s, l1_flt), ("产状", gdf_a, l1_att)):
        ka, kb = _multiset(a_gdf), _multiset(b_gdf)
        same = ka == kb
        geo_ok = geo_ok and same
        details.append(f"{name}{'=' if same else '≠'}({sum(ka.values())}/{sum(kb.values())})")
    rep("C2 几何多重集相等@1e-12", geo_ok, " ".join(details))

    # ③ 面色逐要素 == 反查 rgb（适配器报告）
    bad = rep_u.get("symbolizer_mismatch") or []
    unm = rep_u.get("unmapped") or []
    rep("C3 面色 genericSymbolizer==反查 rgb", not bad and not unm,
        f"mismatch={len(bad)} unmapped={unm[:5]}（{len(gdf_u)}/{expect_counts[0]}）")

    # ④ SDS.name == L1.GZEAB（语义 sds id join，2026-10-02 裁定）
    from ..convert import ids as _ids
    _seg_ord = _ids.fault_seg_ordinals(l1_flt)
    l1_name = {}
    for _, r in l1_flt.iterrows():
        v = r.get("GZEAB")
        v = "" if v is None or str(v).strip().lower() in ("nan", "none") else str(v).strip()
        l1_name[f"{r['fault_id']}.{_seg_ord[int(r['_src_id'])][1]}"] = v
    n_hit = n_tot = 0
    for _, r in gdf_s.iterrows():
        fid = str(r["FEATUREID"])
        if l1_name.get(fid):
            n_tot += 1
            n_hit += int(str(r["GZEAB"]) == l1_name[fid])
    rep("C4 SDS.name==L1.GZEAB", n_hit == n_tot,
        f"{n_hit}/{n_tot} 非空名一致（Lite 空名 {int((gdf_s['GZEAB']=='').sum())}）")

    # ⑤ 产状角度（点位键 join：GZBBAC/GZBBAD == L1）
    l1_att_map = {}
    for _, r in l1_att.iterrows():
        g = r.geometry
        try:
            _dip = float(r["GZBBAD"])
        except (TypeError, ValueError):
            _dip = None  # 空倾角行保留位置键（dip 比对跳过）——
            # 2026-09-29 修正：初版 continue 致 lite 侧判 missing（9 点误报）
        l1_att_map[(round(g.x, 9), round(g.y, 9))] = (
            float(r["GZBBAC"]) % 360.0, _dip)  # 双侧同口径 %360
    n_bad = n_miss = 0
    for _, r in gdf_a.iterrows():
        k = (round(r.geometry.x, 9), round(r.geometry.y, 9))
        if k not in l1_att_map:
            n_miss += 1
            continue
        az, dip = l1_att_map[k]
        # 单位圆规范化同口径（build 侧 GZBBAC%360；360≡0，奥依亚依拉克 1 点首遇）
        if abs((r["dip_az"] % 360.0) - az) > 1e-6:
            n_bad += 1
            continue
        # dip 双侧任一缺省（空倾角行）→ 跳过 dip 比对（缺省如实登记非失配）
        try:
            _rdip = None if r["dip"] is None else float(r["dip"])
        except (TypeError, ValueError):
            _rdip = None
        if dip is not None and _rdip is not None and abs(_rdip - dip) > 1e-6:
            n_bad += 1
    rep("C5 产状角度一致", n_bad == 0 and n_miss == 0,
        f"mismatch={n_bad} missing={n_miss}（{len(gdf_a)}/{expect_counts[3]}）")

    # ⑥ 语义分布一致（2026-10-03 渲染完全基于 geosciml：断层侧改按标定
    # 结构语义对账，脱离码系统；接触侧仍码口径待界线域解耦切换）
    dist_s = Counter(gdf_s["structural_type"])
    dist_s_l1 = Counter(l1_flt["structural_type"].astype(str))
    dist_c = Counter(gdf_c["sem_label"])
    dist_c_l1 = Counter(conv8["sem_label"].astype(str))
    rep("C6 语义分布一致",
        dist_s == dist_s_l1 and dist_c == dist_c_l1,
        f"SDS {'=' if dist_s == dist_s_l1 else dict(dist_s_l1)} / Contact {'=' if dist_c == dist_c_l1 else '≠'}")

    # C7 断层产状测量点视图（09-27 裁定新增）：计数=b 数；点位==L1 独立重算垂足
    import json as _json
    from shapely.geometry import Point as _Pt
    fp_path = Path(lite_dir) / "fault_attitude_point_view.geojson"
    if fp_path.exists():
        fp = _json.loads(fp_path.read_text(encoding="utf-8"))
        feats = fp.get("features", [])
        l1_fl = gpd.read_file(l1_dir / "faults.geojson")
        l1_fa_x = gpd.read_file(l1_dir / "fault_aux.geojson")
        l1_fa_x["_src_id"] = l1_fa_x["_src_id"].astype(int)
        b_sub = l1_fa_x[(l1_fa_x["kind"] == "symbol")
                        & (l1_fa_x["sub_no"].astype(str).str.replace(".0", "", regex=False) == "1894")
                        & (l1_fa_x["status"].astype(str) == "normal")]
        n_view = len(feats)
        pos_bad = 0
        # 垂足坐标多重集比对（语义 id 下不复用 URI 解析，2026-10-02 裁定）
        from collections import Counter as _Counter
        expect_feet = _Counter()
        for _, r in b_sub.iterrows():
            seg_geom = l1_fl.geometry.iloc[int(r["seg_idx"])]
            expect = seg_geom.interpolate(seg_geom.project(r.geometry))
            expect_feet[(round(expect.x, 9), round(expect.y, 9))] += 1
        for ft in feats:
            gx, gy = ft["geometry"]["coordinates"][:2]
            key = (round(gx, 9), round(gy, 9))
            if expect_feet[key] <= 0:
                pos_bad += 1
            else:
                expect_feet[key] -= 1
        rep("C7 测量点视图一致（计数/垂足）",
            n_view == len(b_sub) and pos_bad == 0,
            f"view={n_view}/{len(b_sub)} 错位={pos_bad}")
    else:
        rep("C7 测量点视图一致（计数/垂足）", False, "fault_attitude_point_view.geojson 缺失")

    return ok_all, lines


# ================= 镜像渲染对账（P2） =================

LAYER_TABLE_L1 = [
    ("polygons", "polygon|merged", "polygon", 2),
    ("boundaries", "boundary|LDZOFBA002.WL", "boundary", 10),
    ("fold", "fold|LDZOFBA005.WL", "fold", 14),
    ("faults", "fault|LDZOFBA003.WL", "fault", 15),
    ("fossil", "fossil|LDZOFBB099.WT", "fossil", 17),
    ("mudvolcano", "mudvolcano|LDZOFBB099.WT", "mudvolcano", 17),
    ("attitude", "attitude|LDZOFBA016.WT", "attitude", 18),
]


def assemble_l1_map(l1_dir: str | Path, bbox, *, dpi: int = 200):
    """L1 侧镜像装配 + 中性化（仅改数据列，绘制路径不动）。

    中性化：faults GZEEB:=gzeeb_eff、删 GZEEE 列；boundaries 保 younger_side
    （双侧同用标定列，null → 双侧同探针）
    列（两侧均现场计算）；保留 10/81 码行（10 静默跳过、81 归 M1）；
    attitude 保留 sem_type（差异归 M3）；polygons 不动（zorder 稳定排序）。
    """
    import geopandas as gpd
    import numpy as np
    from pymapgis.rendering import Layer, Map

    l1_dir = Path(l1_dir)
    m = Map(title="L1 镜像", figsize=(24.0, 16.0), dpi=dpi)
    for theme, lname, role, z in LAYER_TABLE_L1:
        fp = l1_dir / f"{theme}.geojson"
        if not fp.exists():
            continue  # 可选主题（mudvolcano 仅库尔干；缺主题不破坏对账）
        g = gpd.read_file(fp)
        if theme == "polygons":
            g = g.sort_values("zorder", kind="stable")
        elif theme == "faults":
            g = g.copy()
            g["GZEEB"] = (g["gzeeb_eff"].astype(str)
                          .str.replace(".0", "", regex=False).str.zfill(2))
            g = g.drop(columns=[c for c in ("GZEEE",) if c in g.columns])
        elif theme == "boundaries":
            # B1 对齐（2026-09-28）：双侧同口径剔除制图误差行；
            # 2026-10-02 渲染优化：保 younger_side（双侧同用标定列，
            # null → 双侧同探针）——GZEEE 仍删（faults 分支，line_cfg 宽对齐）
            g = g[g["status"].astype(str) != "excluded"]
        m.add_layer(Layer(name=lname, geodataframe=g, zorder=z, role=role))
    m.bbox = bbox
    return m


def shared_bbox(l1_dir: str | Path, margin: float = 0.05):
    """bbox 单源计算（L1 四层并集+margin）——同一个 tuple 塞两侧（R12）。"""
    import geopandas as gpd
    import numpy as np
    l1_dir = Path(l1_dir)
    bs = []
    for theme, *_ in LAYER_TABLE_L1:
        fp = l1_dir / f"{theme}.geojson"
        if fp.exists():
            bs.append(gpd.read_file(fp).total_bounds)
    B = np.array(bs)
    minx, miny = B[:, 0].min(), B[:, 1].min()
    maxx, maxy = B[:, 2].max(), B[:, 3].max()
    dx, dy = (maxx - minx) * margin, (maxy - miny) * margin
    return (minx - dx, miny - dy, maxx + dx, maxy + dy)


def run_mirror(lite_dir: str | Path, l1_dir: str | Path, out_dir: str | Path,
               *, dpi: int = 200, color_mapping_path: str | Path,
               fault_styles_path: str | Path, svg_registry: str | Path,
               channel_tol: int = 8) -> tuple[bool, dict]:
    """双数据源同路径渲染 + 像素差分 + 掩膜归类。硬门 unclassified==0。

    掩膜仿射从实际渲染的 ax.transData 捕获（savefig 探针）——
    各向异性布局教训：不得手算等比满幅仿射（2026-09-27）。
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages

    from pymapgis.rendering import render_map_to_pdf
    from pymapgis.rendering import pdf_writer as _pw
    from pymapgis.rendering.pattern_engine import set_svg_pattern_registry_path

    from . import diff as _diff
    from . import masks as _masks
    from .map_builder import build_geosciml_map

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    set_svg_pattern_registry_path(svg_registry)
    bbox = shared_bbox(l1_dir)

    # savefig 探针：捕获每次 render_map_to_pdf 的真实 transData
    captured: list[dict] = []
    _orig_sf = PdfPages.savefig

    def _spy(self, figure=None, **kwargs):
        import matplotlib.pyplot as plt
        fig = figure or plt.gcf()
        ax = fig.axes[0]
        captured.append({"trans": ax.transData, "fig_dpi": float(fig.dpi)})
        return _orig_sf(self, figure, **kwargs)

    PdfPages.savefig = _spy
    try:
        assert getattr(_pw, "_fault_type_overrides", {}) in ({}, None), "R2 全局态污染"
        m1 = assemble_l1_map(l1_dir, bbox, dpi=dpi)
        png1 = out_dir / "_mirror_l1.png"
        render_map_to_pdf(m1, out_dir / "_mirror_l1.pdf",
                          color_mapping_path=color_mapping_path,
                          fault_styles_path=fault_styles_path, bare=True)
        print("L1 侧渲染完成")

        assert getattr(_pw, "_fault_type_overrides", {}) in ({}, None), "R2 全局态污染"
        m2, _ = build_geosciml_map(lite_dir, bbox=bbox, dpi=dpi,
                                   color_mapping_path=color_mapping_path)
        png2 = out_dir / "_mirror_geosciml.png"
        render_map_to_pdf(m2, out_dir / "_mirror_geosciml.pdf",
                          color_mapping_path=color_mapping_path,
                          fault_styles_path=fault_styles_path, bare=True)
        print("GeoSciML 侧渲染完成")
    finally:
        PdfPages.savefig = _orig_sf

    mism, shape = _diff.pixel_diff(png1, png2, channel_tol=channel_tol)
    assert captured, "transData 捕获失败（savefig 探针未触发）"
    cap = captured[0]
    to_px = _masks.RenderTransform(cap["trans"], cap["fig_dpi"], float(dpi), shape)
    import geopandas as gpd
    l1_bnd = gpd.read_file(Path(l1_dir) / "boundaries.geojson")
    l1_att = gpd.read_file(Path(l1_dir) / "attitude.geojson")
    masks = _masks.build_masks(l1_bnd, l1_att, to_px, shape)
    res = _diff.classify(mism, masks)
    rest = res.pop("_rest_mask")
    meta = {"shape": shape, "dpi": dpi, "channel_tol": channel_tol,
            "bbox": bbox, "lite_dir": str(lite_dir), "l1_dir": str(l1_dir)}
    _diff.write_diff_heat(png1, mism, rest, out_dir / "_geosciml_render_diff.png")
    _diff.write_report(res, out_dir / "_geosciml_render_reconcile.json",
                       out_dir / "_geosciml_render_reconcile.md", meta)
    ok = res["unclassified"] == 0
    print(f"镜像差分: mismatch={res['total_mismatch']} "
          f"classes={res['classes']} unclassified={res['unclassified']}"
          f" → {'PASS' if ok else 'FAIL'}")
    res["meta"] = meta
    return ok, res
