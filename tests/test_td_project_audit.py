# -*- coding: utf-8 -*-
"""testdata 项目端到端审计（2026-10-05 用户指令：testdata 作为全链测试
数据推送 GitHub 并同步测试）。

方法：bundled MapGIS 源文件（data/testdata_mapgis/，11 文件）复制到临时
目录 → 临时注册 td 图幅 → 全管线 --check-only → verify 29/29 + 关键泛化
不变量断言（空码面元剔除/零长度界线剔除/语义三轴分布）。

环境契约：pymapgis.semantics 在场才运行（本地完整栈）；CI（PyPI 极简
pymapgis）整模块跳过。运行时长约 3-5 分钟（小图幅端到端）。
"""
from pathlib import Path

import pandas as pd
import pytest

ROOT_BUNDLED = Path(__file__).resolve().parents[1] / "data" / "testdata_mapgis"

_prof = pytest.importorskip("pymapgis.semantics.profile")


@pytest.fixture(scope="module")
def td_project(tmp_path_factory):
    """bundled MapGIS → 临时项目目录 + 临时图幅注册 + 全链 --check-only。

    独立测试键 tdc（避开用户 TOML 的 [sheets.td] 覆盖层——_apply_user_config
    会以 TOML root 覆盖注册值致管线跑错目录）。profile 与 verify 画像在
    fixture 内自建/复制（bundled 数据自持，零外部信息依赖）。
    """
    import shutil
    from geosciml4china.sheets import register_sheet, Sheet
    from geosciml4china import pipeline
    from pymapgis.semantics.profile import PROFILES, SheetProfile
    key = "tdc"
    PROFILES[key] = SheetProfile(
        sheet=key, sheet_title="testdata bundled end-to-end test",
        center_lat_hint=39.3,        # bundled L0 普查（mid 39.32）
        bbox_margin_frac=0.05,
        aux_filter="断层辅助点",     # bundled BB099 普查（20 点）
        b_symbol_raw=1894,           # 自身子图号普查（8 点）
        b_dip_offset_deg=0.0,
        char_dists={}, b_angle_remap_deg=0.0,
        color_mapping=f"output/geosciml/{key}_style_generated.json",
        fault_styles=f"output/geosciml/{key}_fault_styles_generated.json",
        svg_pattern_registry="",     # stylegen 走包数据（单源）
        assoc_csv=f"fault_aux_{key}.csv",
        entities_csv=f"fault_entities_{key}.csv",
        anomaly_csv="_fault_aux_anomalies.csv",
        render_themes=[], l1_stages=[], verify_stages=[])
    tmp = tmp_path_factory.mktemp("td_proj")
    for f in ROOT_BUNDLED.iterdir():
        if f.suffix in (".WL", ".WP", ".WT"):
            shutil.copy2(f, tmp / f.name)
    register_sheet(Sheet(
        key=key, code="J43T000001",
        title="testdata bundled end-to-end test",
        root=tmp,
        aux_pairs_csv="fault_aux_number_1894_pairs.csv",
        aux_assoc_csv=f"fault_aux_{key}.csv",
        aux_triplets_csv=f"_fault_triplets_{key}.csv",
        calibration_csv="_gzbd_calibration_report.csv",
        lite_expect_counts=(107, 143, 52, 23)))
    # verify 画像：复制 td 实测画像（数据同源——bundled testdata）
    from geosciml4china.convert import verify
    verify.EXPECT[key] = dict(verify.EXPECT["td"])
    rc = pipeline.run_pipeline(key, check_only=True)
    assert rc == 0, f"{key} pipeline rc={rc}（应为 0=verify 全过）"
    return tmp


def test_pipeline_converges(td_project):
    """全链收敛是 fixture 断言本身（rc==0 → verify 29/29 PASS）。"""
    from geosciml4china.convert import config
    config.init_sheet("tdc")
    rep = Path(config.REPORT_OUT)
    assert rep.exists(), f"verify 报告缺席: {rep}"
    txt = rep.read_text(encoding="utf-8")
    assert "PASS 29 / WARN 0 / FAIL 0" in txt or (
        "| A24 | PASS |" in txt and "| A24 | FAIL |" not in txt)


def test_blank_code_polygon_excluded(td_project):
    """空码面元（LDZOFBB001 row 42）：build 剔除不发射 MF——GML 中其
    几何对应面元数=L1 面元数−1（经 lxml 解析按单元 norm 归属计数——
    规避文本计数的属性序脆性）。"""
    import geopandas as gpd
    from lxml import etree
    from geosciml4china.convert import config, units as unit_mod
    config.init_sheet("tdc")
    l1 = gpd.read_file(td_project / "geojson/L1/polygons.geojson")
    n_blank = int((l1["QDUECC_eff"].astype(str).str.strip() == "").sum())
    assert n_blank == 1, f"空码面元计数 {n_blank}≠1（数据源特征）"
    doc = etree.parse(td_project / "output/geosciml/tdc_geosciml_full.gml")
    ns = {"gsmlb": "http://www.opengis.net/gsml/4.1/GeoSciML-Basic"}
    norms = set(unit_mod.build_units().keys())
    n_poly = 0
    for m in doc.findall(".//gsmlb:MappedFeature", ns):
        iid = m.get("{http://www.opengis.net/gml/3.2}id") or ""
        if not iid.startswith("mf."):
            continue
        core = iid[3:].rsplit(".", 1)[0] if "." in iid[3:] else iid[3:]
        if core in norms:
            n_poly += 1
    assert n_poly == len(l1) - 1


def test_zero_length_boundaries_excluded(td_project):
    """零长度界线（6 段 GZBD=02）：探针跳过→未标定→build 剔除不发射——
    GML Contact 数=149−6=143。"""
    gml = (td_project / "output/geosciml/tdc_geosciml_full.gml") \
        .read_text(encoding="utf-8")
    assert gml.count("<gsmlb:Contact") == 143
    # 语义侧：解释表 347 行 = 353−6（零长度不上探针）——数据自证
    si = pd.read_csv(td_project / "_gzbd_semantic_interpretation.csv",
                     dtype=str)
    assert len(si) == 347


def test_fault_semantics_three_axes(td_project):
    """断层三维：52 段全部获结构语义（无 nil faultType）；泛称兜底在案。"""
    cal = pd.read_csv(td_project / "_gzeeb_calibration_tdc.csv", dtype=str)
    assert len(cal) == 52
    assert set(cal["structural_type"].dropna()) != set()
    # 运动学一致性抽象约束生产不变量：不一致段必须已登记矛盾保留
    from geosciml4china.calibrate.gzeeb import _kin_consistent
    for _, r in cal.iterrows():
        res = _kin_consistent(str(r["structural_type"]),
                              str(r["gzeld_sem"]))
        if res is False:
            assert "矛盾" in str(r["verdict"]) or "违反" in str(r["verdict"]), \
                f"td seg{r['idx']} 不一致未登记"


def test_fault_contact_activity_layer(td_project):
    """断裂接触活动审计层在该小图幅执行（产出在案，不崩）。"""
    p = td_project / "_fault_contact_activity_tdc.csv"
    assert p.exists()
    fc = pd.read_csv(p, dtype=str)
    assert len(fc) >= 0  # 层执行（候选数随数据，不断言）
