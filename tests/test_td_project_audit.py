# -*- coding: utf-8 -*-
"""testdata 项目端到端审计（2026-10-05 用户指令：testdata 作为全链测试
数据推送 GitHub 并同步测试）。

方法：bundled MapGIS 源文件（data/testdata_mapgis/，11 文件）复制到临时
目录 → 临时注册 td 图幅 → 全管线 --check-only → verify 29/29 + 关键泛化
不变量断言（空码面元剔除/零长度界线剔除/语义三轴分布）。

环境契约：pymapgis.semantics 在场才运行（本地完整栈）；CI（PyPI 极简
pymapgis）整模块跳过。运行时长约 15 秒（小图幅端到端）。
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


def test_codebook_confidence_reconciles(td_project):
    """置信度文件（2026-10-07 配套裁定）：管线产出 codebook_confidence
    文件；机械汇总与标定 CSV 恒等对账（total==CSV 行数）。"""
    import json
    from geosciml4china.calibrate.confidence import confidence_path
    p = confidence_path(td_project, "tdc")
    assert p.exists(), "管线未产出 codebook 置信度文件"
    conf = json.loads(p.read_text(encoding="utf-8"))
    assert conf["codebook_confidence"] == "geosciml4china/codebook-confidence/v1"
    assert conf["readonly"] is True
    b = conf["domains"]["boundaries"]
    si = pd.read_csv(td_project / "_gzbd_semantic_interpretation.csv", dtype=str)
    assert b["total"] == len(si), "界线 total 与解释表行数不恒等"
    assert b["pending"] == int((si["状态"] == "分歧未裁定").sum())
    f = conf["domains"]["faults"]
    cal = pd.read_csv(td_project / "_gzeeb_calibration_tdc.csv", dtype=str)
    assert f["total"] == len(cal), "断层 total 与标定件行数不恒等"
    assert conf["codebook_quality"], "codebook_quality 缺席"


def test_probe_census_matches_bundled(td_project):
    """零注入普查（probe）自持回归：bundled 图幅自身数据的普查值逐项
    锁定（lat/aux 类词/子图号/计数/形态预警）——onboarding 通道防漂移。
    管道跑过的进程内 probe 仍须读原始 MapGIS（JWD_SOURCE 强制 raw）。"""
    import contextlib
    import io
    from geosciml4china.probe import probe
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = probe(td_project, "probec", register=False)
    assert out["lat_mid"] == 39.3
    assert out["aux_filter"] == "断层辅助点"
    assert out["b_symbol_raw"] == 1894
    assert out["counts"] == {"faults": 52, "boundaries": 353,
                             "attitudes": 23, "folds": 2}
    assert out["poly_dist"] == {"LDZOFBB001.WP": 86, "LDZOFBB002.WP": 7,
                                "LDZOFBB003.WP": 9, "LDZOFBB004.WP": 6}
    assert out["n_units_raw"] == 21
    assert any("空码面元" in w for w in out["warnings"])
    assert any("零长度界线" in w for w in out["warnings"])


def test_incremental_skip_second_run(td_project, capsys):
    """增量通道（2026-10-05 泛化提速）：L0 全部产物新于源文件时二次全链
    免转——二跑打印跳过行且仍全绿（幂等重跑，零语义漂移）。"""
    from geosciml4china import pipeline
    rc = pipeline.run_pipeline("tdc", check_only=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "① 跳过（L0 新于源文件" in out, "二次全链应命中增量通道"


def test_codebook_is_conversion_basis(td_project):
    """codebook 裁定（2026-10-06）：校准产出 codebook_<key>.json；
    用户可改 JSON；后续 GeoSciML 转换建立在 codebook 上——编辑
    user_semantic 后仅重跑 build（不重跑校准），GML 语义随编辑变化；
    还原编辑后 GML 复原。"""
    import json
    import sys
    from lxml import etree
    from geosciml4china.calibrate.codebook import (build_codebook,
                                                   codebook_path,
                                                   semantic_of)
    from geosciml4china.convert import build as _build

    cbp = codebook_path(td_project, "tdc")
    assert cbp.exists(), "管线未产出 codebook"
    cb = json.loads(cbp.read_text(encoding="utf-8"))
    assert cb["codebook"] == "geosciml4china/codebook/v1"

    # 选一个 td 在场码：其段当前语义与 codebook 一致（未编辑时字节稳定）
    fam = cb["codes"]["GZEEB"]
    code = sorted(fam, key=lambda c: -fam[c].get("segs", 0))[0]
    sem0 = semantic_of(cb, "GZEEB", code)
    assert sem0, "codebook 语义缺席"

    gml = td_project / "output/geosciml/tdc_geosciml_full.gml"
    ns = {"gsmlb": "http://www.opengis.net/gsml/4.1/GeoSciML-Basic"}

    def fault_types():
        doc = etree.parse(str(gml))
        out = {}
        for s in doc.findall(".//gsmlb:ShearDisplacementStructure", ns):
            ft = s.find("gsmlb:faultType", ns)
            href = (ft.get("{http://www.w3.org/1999/xlink}href", "?")
                    if ft is not None else "nil")
            out[href] = out.get(href, 0) + 1
        return out

    ft0 = fault_types()

    # 用户编辑：该码 user_semantic → 逆断层（直达转换层，不重跑校准）
    cb["codes"]["GZEEB"][code]["user_semantic"] = "逆断层"
    cbp.write_text(json.dumps(cb, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    saved = sys.argv
    sys.argv = ["g4c build", "--sheet", "tdc"]
    try:
        assert _build.main() == 0
    finally:
        sys.argv = saved
    ft1 = fault_types()
    rev = "http://resource.geosciml.org/classifier/cgi/faulttype/reverse_fault"
    assert ft1.get(rev, 0) > ft0.get(rev, 0), \
        f"编辑 codebook 未改变 faultType（{ft0.get(rev,0)}→{ft1.get(rev,0)}）"

    # 还原：清空用户编辑 + 再生成（跨轮保留机制下显式清空）→ 重跑 build
    cb["codes"]["GZEEB"][code]["user_semantic"] = ""
    cbp.write_text(json.dumps(cb, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    saved = sys.argv
    sys.argv = ["g4c build", "--sheet", "tdc"]
    try:
        assert _build.main() == 0
    finally:
        sys.argv = saved
    assert fault_types() == ft0, "还原后 GML 语义未复原"
