# -*- coding: utf-8 -*-
"""GZBD 界线标定规则动态审计（2026-09-29 用户指令：审计标定程序严格落实裁定逻辑）。

合成图幅（L0 GeoJSON）驱动 calibrate_boundaries 全流程，逐条验证：
  T1a/T1b 段间通则相邻段（01 通过 / 02 分歧）
  T2      段间通则跨段仅断层（10）
  T3      名称段式跨段（代码无段号→名称回退：虚构群二段|四段 → 10）
  T4      相对段相邻（下岩段|上岩段 → 01）
  T5      兜底拦截（域外码 99 → 一般地质界线，不被第四系通则误标）+ 审计存档
  T6      第四系通用规则（02 通过）
  T7/T7b  侵入时代二分（覆盖→04 / 非覆盖→11）
  T8      间断通则（gap≥200 → 04）
  T9      43 约束违反（非岩浆岩侧 → 分歧未裁定，不改码）
  T10     60 约束通过（同代岩浆岩 → 特殊码独立标定）

裁定基准（用户 2026-09-29）：五通道+兜底+段间通则（上段新下段老/一段老二段新/
相邻段整合接触）。
"""
import json
import os

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

os.environ.setdefault("JWD_SOURCE", "geojson")

# ---- 合成图幅（模块级 fixture） ------------------------------------------------
CASES = []


def _strip(y0, left_code, left_name, right_code, right_name, gzbd,
           left_intr=False, right_intr=False):
    """水平界线 y=y0，上方（探针左）=left 单元、下方=right 单元。"""
    CASES.append(dict(y0=y0, lc=left_code, ln=left_name, rc=right_code,
                      rn=right_name, gzbd=gzbd, li=left_intr, ri=right_intr))


_strips = [
    # (y, 左码, 左名, 右码, 右名, gzbd, 左侵入, 右侵入)
    (1.0, "K2x1", "虚构组一段", "K2x2", "虚构组二段", 1, False, False),    # T1a
    (1.2, "K2x1", "虚构组一段", "K2x2", "虚构组二段", 2, False, False),    # T1b
    (1.4, "K2x1", "虚构组一段", "K2x3", "虚构组三段", 1, False, False),    # T2 跨段（期望10 vs 实际01→分歧）
    (1.6, "Pt1qa", "虚构群二段", "Pt1qb", "虚构群四段", 1, False, False),   # T3 名称回退跨段（同）
    (1.8, "Ar3a", "虚构群下岩段", "Ar3b", "虚构群上岩段", 1, False, False), # T4 相对相邻
    (2.0, "Qp3", "冲积物", "C2", "虚构组", 99, False, False),              # T5 兜底拦截
    (2.2, "Qp3", "冲积物", "C2", "虚构组", 2, False, False),               # T6 第四系
    (2.4, "C2", "虚构组", "γC", "石炭纪花岗岩", 4, False, True),           # T7 覆盖
    (2.6, "γC", "石炭纪花岗岩", "S", "志留系地层", 11, True, False),       # T7b 非覆盖
    (2.8, "C1", "虚构组A", "S", "志留系地层", 4, False, False),            # T8 间断
    (3.0, "γC", "石炭纪花岗岩", "C2", "虚构组", 43, True, False),          # T9 43违反
    (3.2, "γC", "花岗岩A", "γC", "花岗岩B", 60, True, True),               # T10 60通过
    (3.4, "Ar3c", "三段群下岩段", "Ar3d", "三段群上岩段", 1, False, False),  # T4b 三段式（远处有中岩段）
    (5.0, "Ar3m", "三段群中岩段", "Ar3m2", "三段群中岩段", 1, False, False), # 普查用中段（远离界线不干扰探针）
]
for args in _strips:
    _strip(*args)


@pytest.fixture(scope="module")
def audit_sheet(tmp_path_factory):
    from geosciml4china.sheets import Sheet, register_sheet
    from pymapgis.semantics.profile import PROFILES, SheetProfile

    root = tmp_path_factory.mktemp("audit_sheet")
    l0 = root / "geojson" / "L0"
    l0.mkdir(parents=True)

    def _poly(y_lo, y_hi):
        return Polygon([(0, y_lo), (1, y_lo), (1, y_hi), (0, y_hi)])

    sed_rows, intr_rows, bnd_rows = [], [], []
    for i, c in enumerate(CASES):
        y = c["y0"]
        # 上方（探针左）单元
        rec = dict(QDUECC=c["lc"], QDUECD=c["ln"],
                   geometry=_poly(y + 0.001, y + 0.05))
        (intr_rows if c["li"] else sed_rows).append(rec)
        # 下方（探针右）单元
        rec = dict(QDUECC=c["rc"], QDUECD=c["rn"],
                   geometry=_poly(y - 0.05, y - 0.001))
        (intr_rows if c["ri"] else sed_rows).append(rec)
        bnd_rows.append(dict(_src_id=i, GZBD=c["gzbd"],
                             geometry=LineString([(0, y), (1, y)])))

    gpd.GeoDataFrame(sed_rows, geometry="geometry", crs="EPSG:4326").to_file(
        l0 / "LDZOFBB001.WP.geojson", driver="GeoJSON")
    if intr_rows:
        gpd.GeoDataFrame(intr_rows, geometry="geometry", crs="EPSG:4326").to_file(
            l0 / "LDZOFBB003.WP.geojson", driver="GeoJSON")
    gpd.GeoDataFrame(bnd_rows, geometry="geometry", crs="EPSG:4326").to_file(
        l0 / "LDZOFBA002.WL.geojson", driver="GeoJSON")

    register_sheet(Sheet(key="_audit", code="AUDIT", title="审计合成幅", root=root))
    PROFILES["_audit"] = SheetProfile(
        sheet="_audit", sheet_title="审计合成幅", center_lat_hint=39.5,
        bbox_margin_frac=0.05, aux_filter="", b_symbol_raw=1894,
        b_dip_offset_deg=0.0, char_dists={"b": 277.0, "a": 115.0},
        b_angle_remap_deg=0.0, color_mapping="", fault_styles="",
        svg_pattern_registry="", assoc_csv="", entities_csv="")
    return root


@pytest.fixture(scope="module")
def audit_out(audit_sheet, tmp_path_factory):
    from geosciml4china.calibrate.gzbd import calibrate_boundaries
    out = tmp_path_factory.mktemp("audit_out")
    calibrate_boundaries("_audit", out_dir=str(out))
    return out


def _interp(audit_out):
    import pandas as pd
    df = pd.read_csv(audit_out / "_gzbd_semantic_interpretation.csv", dtype=str)
    return {int(r["idx"]): r for _, r in df.iterrows()}


def test_audit_rules(audit_out):
    m = _interp(audit_out)
    # T1a 相邻段 01 通过 + 段序新老（二段新→年轻侧=右）
    assert m[0]["状态"] == "标定通过" and "段间通则-相邻段" in m[0]["证据"]
    assert m[0]["先验年轻侧"] == "right"
    # T1b 相邻段 02 分歧（期望 01，不改码）
    assert m[1]["状态"] == "分歧未裁定" and m[1]["GZBD_eff"] == "02"
    # T2 跨段：通则期望 10、实际 01 → 分歧未裁定（矛盾交人工通道）+ 三段新→右
    assert m[2]["状态"] == "分歧未裁定" and "段间通则-跨段仅断层" in m[2]["证据"]         and m[2]["GZBD_eff"] == "01" and m[2]["先验年轻侧"] == "right"
    # T3 名称段式回退：虚构群二段|四段（代码无段号）同判跨段 → 分歧未裁定
    assert m[3]["状态"] == "分歧未裁定" and "段间通则-跨段仅断层" in m[3]["证据"]
    # T4 相对段：下岩段|上岩段 相邻 → 01 + 上新下老（上侧=右 年轻）
    assert m[4]["状态"] == "标定通过" and "段间通则-相邻段" in m[4]["证据"]
    assert m[4]["先验年轻侧"] == "right"
    # T4b 三段式组：下|上 隔中段 → 跨段（普查在册）+ 上新下老仍成立
    assert m[12]["状态"] == "分歧未裁定" and "段间通则-跨段仅断层" in m[12]["证据"]
    assert m[12]["先验年轻侧"] == "right"
    # T6 第四系通则
    assert m[6]["状态"] == "标定通过" and "第四系通用规则" in m[6]["证据"]
    # T7 侵入覆盖二分 → 04
    assert m[7]["状态"] == "标定通过" and "侵入通用规则-覆盖" in m[7]["证据"]
    # T7b 非覆盖 → 11
    assert m[8]["状态"] == "标定通过" and "侵入通用规则" in m[8]["证据"] \
        and "覆盖" not in m[8]["证据"]
    # T8 间断通则 gap≥200 → 04
    assert m[9]["状态"] == "标定通过" and "间断通则" in m[9]["证据"]
    # T9 43 约束违反 → 分歧未裁定、不改码
    assert m[10]["状态"] == "分歧未裁定" and "43约束" in m[10]["证据"] \
        and m[10]["GZBD_eff"] == "43"
    # T10 60 约束通过 → 特殊码独立标定
    assert m[11]["状态"] == "特殊码（独立标定）"


def test_audit_fallback_interception(audit_out):
    """T5 域外码 99：兜底拦截于先验/通则级联之前（第四系通则不得误标），
    语义=一般地质界线、GZBD_eff 不改码、审计档案在册。"""
    m = _interp(audit_out)
    r = m[5]
    assert r["状态"] == "特殊码兜底（一般地质界线）"
    assert r["标定语义"] == "一般地质界线"
    assert r["GZBD_eff"] == "99"
    assert "第四系" not in r["证据"] and "兜底" in r["证据"]
    fb = __import__("pandas").read_csv(
        audit_out / "_gzbd_special_fallback.csv", dtype=str)
    assert len(fb) == 1 and fb.iloc[0]["GZBD原码"] == "99"


def test_audit_confidence_columns(audit_out):
    """影子置信三列齐备（S×I×F 框架契约）。"""
    import pandas as pd
    df = pd.read_csv(audit_out / "_gzbd_semantic_interpretation.csv", dtype=str)
    for col in ("confidence_u", "conf_breakdown_u", "conf_band_u"):
        assert col in df.columns
    # 兜底行落 conflict 带（码义待裁定）
    fb = df[df["状态"] == "特殊码兜底（一般地质界线）"]
    assert (fb["conf_band_u"] == "conflict").all()
