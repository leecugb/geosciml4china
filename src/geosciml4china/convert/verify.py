# ruff: noqa: E501
"""Verify GeoSciML outputs: XSD validation + business assertions + reconciliation.

CLI: g4c verify --sheet kurgan [--gml path] [--lite-dir path] [--report path]
Exit code 1 on any FAIL assertion.（驱动移植自 verify_geosciml_output.py，2026-09-28 入包）
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

from lxml import etree

from ..sheets import list_sheets
from pymapgis.semantics.profile import get_profile
from . import config, mapping, model, sources, validate
from . import ids as semantic_ids
from . import units as unit_mod

GSMLB = "{http://www.opengis.net/gsml/4.1/GeoSciML-Basic}"
GSMLE = "{http://www.opengis.net/gsml/4.1/GeoSciML-Extension}"
GML = "{http://www.opengis.net/gml/3.2}"
XLINK = "{http://www.w3.org/1999/xlink}"

# 双幅期望画像（2026-09-27 英吉沙接入实测核定）
EXPECT = {
    # 库尔干幅副本（全管线测试幅，2026-10-02）——画像=库尔干镜像
    "jws": dict(
        units=57, poly_mfs=713, contacts=1316, contact_nil=0, sds=310,
        sds_nil_faulttype=0, planes=93, polarity=2, folds=4, fold_nil=0,
        members=4733, compositions=12, six_mode=(51, 5, 3, 0, 29, 5),
        regional_norms=("ChA", "ChSt", "Pt1K"),
        banners=7, dv_blocks=97,  # 2026-10-02 实测：Qp1X 箭头归一修复后
        # 活动候选队列 8→1（F038/F070/F093/F032/F004/F001/F067 消解）
        ms_dist={"reverse": 54, "normal": 5, "no_movement_sense": 34,
                 "dextral": 1, "sinistral": 3},
        hwd=93, relations=153, measure_points=93, char_dist_b=277.0,  # 全链基线 160→153（区域单元年代不可判 7 对，2026-10-02 裁定）
        lite_counts={"geologic_unit_view": 713, "contact_view": 1316,
                     "shear_displacement_structure_view": 310,
                     "site_observation_view": 305,
                     "fault_attitude_point_view": 93,
                     "fossil_specimen_view": 48},
        fossil_violations=1,
    ),
    "kurgan": dict(
        units=57, poly_mfs=713, contacts=1316, contact_nil=0, sds=310,
        sds_nil_faulttype=0, planes=93, polarity=2, folds=4, fold_nil=0,
        members=4733, compositions=12, six_mode=(51, 5, 3, 0, 29, 5),
        regional_norms=("ChA", "ChSt", "Pt1K"),
        banners=7, dv_blocks=97,
        ms_dist={"reverse": 54, "normal": 5, "no_movement_sense": 34,
                 "dextral": 1, "sinistral": 3},
        hwd=93, relations=160, measure_points=93, char_dist_b=277.0,
        lite_counts={"geologic_unit_view": 713, "contact_view": 1316,
                     "shear_displacement_structure_view": 310,
                     "site_observation_view": 305,
                     "fault_attitude_point_view": 93,
                     "fossil_specimen_view": 48},
        fossil_violations=1,
    ),
    # jwss（英吉沙幅副本独立项目，2026-10-02 泛化测试）：画像=英吉沙镜像
    # 初始猜测——独立跑测后按实测回填
    # jwss（英吉沙幅副本独立项目，2026-10-02 泛化测试）：零数据件复制的
    # 裸接入基线——派生映射 pending 接触 405、gzeeb 兜底决定（nil 6）、
    # 自身登记册 27 对、关系 163（均实测）
    # jwss（英吉沙幅副本独立项目，2026-10-02 泛化测试）：码义对齐裁定后
    # 基线——全新裸项目（2026-10-03 首跑实测画像；库尔干幅副本 J43C001002，
    # 无注册表无裁定——未注册码 MLE 提案 pending 通道验证）
    "jwsss": dict(
        units=57, poly_mfs=713, contacts=1318, contact_nil=80, sds=310,
        # 2026-10-04 实测：contactType 语义驱动后 nil 278→80
        # （整合接触→conformable 等段级终态语义→CGI 词；余侵入接触
        # 78+推测界线 1+复合标签 1 待词表裁定）
        sds_nil_faulttype=0, planes=94, polarity=2, folds=4, fold_nil=0,
        members=4738, compositions=12, six_mode=(51, 5, 3, 0, 30, 5),
        orphan_tolerance=True, fossil_violations=1,
        banners=22,  # 2026-10-04 实测：无族义即无冲突后（全继承 18+
                      # 真实 3+码义未注册 5 基线——归一通道撤销）
        dv_blocks=98,
        ms_dist={"no_movement_sense": 35, "reverse": 54, "normal": 5,
                 "sinistral": 3, "dextral": 1},
        hwd=94, relations=113, measure_points=94, char_dist_b=277.7,
        lite_counts={"geologic_unit_view": 713, "contact_view": 1318,
                     "shear_displacement_structure_view": 310,
                     "site_observation_view": 305,
                     "fault_attitude_point_view": 94,
                     "fossil_specimen_view": 48},
    ),
    # 基线——图幅注册表仅 {02: 推测断层}，未注册码 MLE 提案待裁定
    "jwss": dict(
        units=95, poly_mfs=808, contacts=1199, contact_nil=192, sds=289,
        # 2026-10-04 实测：contactType 语义驱动后 nil 405→192
        # （jwss 24 案对齐——段级整合接触⇄CGI conformable；余侵入
        # 接触 186 等未覆盖标签待词表裁定）
        sds_nil_faulttype=0, planes=134, polarity=0, folds=7, fold_nil=0,
        members=4357, compositions=0, six_mode=(46, 22, 11, 7, 47, 1),
        orphan_tolerance=True,
        banners=7,  # 2026-10-04 实测：类别编码值最高优先级裁定（全继承
                    # 含泛称，一般断层兼容一切）——8 条 01 码 dip-gate 被
                    # 兼容吸收，余 4 真实张力+3 全继承登记（F026 单条去重）
        dv_blocks=137,
        ms_dist={"reverse": 57, "normal": 29, "no_movement_sense": 48,
                 "sinistral": 3},
        hwd=134, relations=163, measure_points=134, char_dist_b=297.0,
        lite_counts={"geologic_unit_view": 808, "contact_view": 1199,
                     "shear_displacement_structure_view": 289,
                     "site_observation_view": 165,
                     "fault_attitude_point_view": 134,
                     "fossil_specimen_view": 40},
    ),
    "yingjisha": dict(
        units=95, poly_mfs=808, contacts=1199, contact_nil=0, sds=289,
        sds_nil_faulttype=51, planes=134, polarity=0, folds=7, fold_nil=0,
        members=4357, compositions=0, six_mode=(46, 22, 11, 7, 47, 1),
        orphan_tolerance=True,  # 色库 95 > 图面引用（泛化审计 2026-10-02 画像化）
        banners=7, dv_blocks=137,  # 2026-10-02 语义 id 迁移实测
        # auxchain 版画像（2026-09-29 重测）；238/239 钩旋向未提取
        # （sinistral 3 丢失——登记缺口）
        # 2026-09-30 距离带四案+主路降级终版后画像
        # 2026-10-02 slip_sense 接线后画像（+sinistral 3 走滑旋向块）；
        # 语义 id 迁移实测更新
        ms_dist={"reverse": 57, "normal": 29, "no_movement_sense": 48,
                 "sinistral": 3},
        hwd=134, relations=23, measure_points=134, char_dist_b=297.0,
        lite_counts={"geologic_unit_view": 808, "contact_view": 1199,
                     "shear_displacement_structure_view": 289,
                     "site_observation_view": 165,
                     "fault_attitude_point_view": 134,
                     "fossil_specimen_view": 40},
    ),
    # 巴什库尔干（2026-09-29 首接+aux 基线）：无倾角注释类别→倾角留空
    # （仅倾向 12）；三联体 8 组（距离带约束后：逆 3/存疑 5，互证 3）；
    # GZEEB 02/23/39 pending（20 段）；水系面/化石本幅无。
    "bashkurgan": dict(
        units=40, poly_mfs=403, contacts=546, contact_nil=0, sds=213,
        sds_nil_faulttype=20, planes=20, polarity=0, folds=10, fold_nil=0,
        members=2525, compositions=0, six_mode=(8, 0, 1, 0, 0, 11),
        orphan_tolerance=True,
        banners=3, dv_blocks=20,  # 2026-10-02 gzeeb 现版重跑实测
        # 2026-09-30 距离带四案+主路降级终版后画像：逆 6→7
        ms_dist={"reverse": 9, "no_movement_sense": 11},
        hwd=20, relations=78, measure_points=20, char_dist_b=190.4,
        lite_counts={"geologic_unit_view": 403, "contact_view": 546,
                     "shear_displacement_structure_view": 213,
                     "site_observation_view": 262,
                     "fault_attitude_point_view": 20,
                     "fossil_specimen_view": 0},
    ),
    # 奥依亚依拉克首接基线（2026-09-29 实测核定）：aux 标定链未接入
    # （pairs/triplets/entities 缺省→planes/dv/hwd/measure_points/relations=0）；
    # GZEEB 02/03/35/40（73 段）与 GZCE 01（44 段）pending 中——
    # 画像随 pending_review.md 裁定逐轮收紧。
    # 2026-09-29 二轮：aux 基线关联（箭头×61 归属+配对×27）；
    # 三轮：三联体基线（35 组；距离带约束 2026-09-29 用户裁定）。四轮：
    # 实体链判别（auxchain，2026-09-29 泛化优化）——36 组（跨段恢复 1 组）：
    # 逆 22/正 5（带外组禁止成组严格化后，2026-09-29）；配对 21；
    # 六类画像随实体链版更新。
    "aoyiyayilake": dict(
        units=58, poly_mfs=543, contacts=734, contact_nil=0, sds=341,
        sds_nil_faulttype=73, planes=61, polarity=13, folds=60, fold_nil=0,
        members=3744, compositions=0, six_mode=(27, 6, 2, 0, 9, 17),
        orphan_tolerance=True,
        banners=36, dv_blocks=65,  # 2026-10-02 gzeeb 现版重跑实测（Qp1X/注释通道裁定后）
        # 2026-10-02 slip_sense 接线后画像：a-b→a-b-a 升级（臂隙兜底）+
        # 走滑旋向块 sinistral 3/dextral 1（空间识别钩对出站）
        ms_dist={"reverse": 29, "normal": 6, "no_movement_sense": 26,
                 "sinistral": 3, "dextral": 1},
        hwd=61, relations=0, measure_points=61, char_dist_b=209.6,
        lite_counts={"geologic_unit_view": 543, "contact_view": 734,
                     "shear_displacement_structure_view": 341,
                     "site_observation_view": 406,
                     "fault_attitude_point_view": 61,
                     "fossil_specimen_view": 20},
    ),
}

results: List[Tuple[str, str, str]] = []  # (id, level, message)


def check(cid: str, ok: bool, message: str, level: str = "FAIL") -> bool:
    results.append((cid, "PASS" if ok else level, message))
    return ok


def _text(el, path: str) -> Optional[str]:
    found = el.find(path)
    return found.text if found is not None else None


def main() -> int:
    # GBK 控制台容忍（2026-10-02 重渲崩溃案）：✓/⚠ 标记在 cp936 stdout
    # 下 UnicodeEncodeError 中止 verify——统一降级 replace，报告文件不受影响
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--gml", default=None)
    ap.add_argument("--lite-dir", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--sheet", choices=[s.key for s in list_sheets()],
                    default="kurgan")
    args = ap.parse_args()

    config.init_sheet(args.sheet)
    EXP = EXPECT[args.sheet]
    gml_path = Path(args.gml or str(config.GML_OUT))
    lite_dir = Path(args.lite_dir or str(config.LITE_OUT))
    args.report = args.report or str(config.REPORT_OUT)

    # --- XSD validation -------------------------------------------------------
    ok, err_log = validate.validate(gml_path)
    check("XSD", ok, f"full document validates against geoSciMLExtension.xsd ({len(err_log)} errors)")  # noqa: E501
    if not ok:
        for e in list(err_log)[:10]:
            print("  XSD-ERR:", str(e)[:200])

    doc = etree.parse(str(gml_path))
    root = doc.getroot()
    members = root.findall(f"{GSMLB}member")
    units_el = doc.findall(f".//{GSMLB}GeologicUnit")
    mf_el = doc.findall(f".//{GSMLB}MappedFeature")
    contacts_el = doc.findall(f".//{GSMLB}Contact")
    sds_el = doc.findall(f".//{GSMLB}ShearDisplacementStructure")
    fol_el = doc.findall(f".//{GSMLB}Foliation")
    fold_el = doc.findall(f".//{GSMLB}Fold")

    unit_records = unit_mod.build_units()

    # --- A01: units + global unique ids --------------------------------------
    ids = [el.get(f"{GML}id") for el in members[0].iter() if el.get(f"{GML}id")]
    dup = [i for i, n in Counter(ids).items() if n > 1 and i]
    check("A01", len(units_el) == EXP["units"] and not dup,
          f"{EXP['units']} GeologicUnit (got {len(units_el)}); duplicate gml:id: {dup[:5]}")

    # --- A02: events have an age representation (5 dykes exempt) -------------
    from urllib.parse import unquote

    def _unit_norm(u) -> str:
        """单元 norm 真值：从 gml:identifier URI 反编码（gml:id 已 NCName 化，
        不能直接切——英吉沙 ∈/+ 码教训）。"""
        ident = u.find(f"{GML}identifier")
        if ident is not None and ident.text:
            return unquote(ident.text.rstrip("/").rsplit("/", 1)[-1])
        return u.get(f"{GML}id", "")[3:]

    dyke_pending = {"δ", "υ", "τα", "βμ", "γρ"}
    bad_events = []
    for u in units_el:
        norm = _unit_norm(u)
        for ev in u.findall(f"{GSMLB}geologicHistory/{GSMLB}GeologicEvent"):
            named = ev.findall(f"{GSMLB}olderNamedAge") or ev.findall(f"{GSMLB}youngerNamedAge")
            numeric = ev.findall(f"{GSMLB}numericAge")
            if not named and not numeric and norm not in dyke_pending:
                bad_events.append(norm)
    check("A02", not bad_events, f"events lacking any age (non-exempt): {sorted(set(bad_events))}")

    # --- A03: regional dual-track（库尔干 3 单元；英吉沙无此约定） -------------
    regional_bad = []
    regional_norms = tuple(EXP.get("regional_norms", ()))
    for norm in regional_norms:
        u = next((x for x in units_el if _unit_norm(x) == norm), None)
        if u is None:
            regional_bad.append(f"{norm} missing")
            continue
        named = u.findall(f".//{GSMLB}olderNamedAge")
        numeric = u.findall(f".//{GSMLB}numericAge")
        rec = unit_records.get(norm)
        if not named or not numeric:
            regional_bad.append(f"{norm} dual-track incomplete")
        elif rec and rec.event.numeric_pair and rec.event.numeric_pair[0] <= rec.event.numeric_pair[1]:
            regional_bad.append(f"{norm} numeric order wrong")
    check("A03", not regional_bad, f"regional dual-track issues: {regional_bad}")

    # --- A04: eventProcess matches layer class -------------------------------
    ep_bad = []
    # 官方图层名对齐（2026-09-29）：新名生效，旧名兼容期保留
    expect = {"沉积岩建造": "deposition", "火山岩性岩相": "deposition",
              "侵入岩": "intrusion", "变质岩建造": "metamorphic_process",
              # 火山岩性岩相→deposition：用户词表定值（火山层按沉积建造处理）
              "正式沉积地层": "deposition", "补充沉积地层": "deposition",
              "变质岩": "metamorphic_process"}
    for u in units_el:
        norm = _unit_norm(u)
        want = expect.get(unit_records.get(norm).layer_role if unit_records.get(norm) else None)
        got = u.find(f".//{GSMLB}eventProcess")
        if got is None or not str(got.get(f"{XLINK}href", "")).endswith(f"/{want}"):
            ep_bad.append(f"{norm}: want {want}, got {got.get(f'{XLINK}href') if got is not None else None}")  # noqa: E501
    check("A04", not ep_bad, f"eventProcess mismatches: {ep_bad[:5]}")

    # --- A05: composition count and lithology URIs valid ---------------------
    with open(config.SIMPLE_LITHOLOGY, encoding="utf-8") as f:
        lith_uris = {e["uri"] for e in json.load(f).values()}
    comp_units = [u for u in units_el if u.findall(f"{GSMLB}composition")]
    lith_hrefs = [h for u in units_el for h in
                  (x.get(f"{XLINK}href") for x in u.findall(f".//{GSMLB}lithology"))]
    bad_lith = [h for h in lith_hrefs if h not in lith_uris]
    decided_n = sum(1 for u in unit_records.values() if u.compositions)
    check("A05", len(comp_units) == decided_n and not bad_lith,
          f"composition units: {len(comp_units)} (mapping expects {decided_n}); bad lithology URIs: {bad_lith[:3]}")  # noqa: E501

    # --- A06: 713 MFs resolve; no orphan units/features ----------------------
    unit_uris = {rec.uri for rec in unit_records.values()}
    spec_hrefs = [el.get(f"{XLINK}href") for el in doc.findall(f".//{GSMLB}MappedFeature/{GSMLB}specification")]  # noqa: E501
    unresolved = [h for h in spec_hrefs if h and h not in unit_uris and not h.startswith(config.BASE_URI + "contact/")
                  and not h.startswith(config.BASE_URI + "fault/") and not h.startswith(config.BASE_URI + "foliation/")
                  and not h.startswith(config.BASE_URI + "fold/")]
    poly_mfs = [h for h in spec_hrefs if h in unit_uris]
    used_units = {h for h in poly_mfs}
    orphans = unit_uris - used_units
    orphan_fail = bool(orphans) and EXP.get("orphan_tolerance", False) is False
    check("A06", len(poly_mfs) == EXP["poly_mfs"] and not unresolved and not orphan_fail,
          f"polygon MFs: {len(poly_mfs)}/{EXP['poly_mfs']}; unresolved: {len(unresolved)}; orphan units: {len(orphans)} {sorted(orphans)[:5]}")

    # --- A07: contacts count and pending nils --------------------------------
    nil_contacts = [c for c in contacts_el
                    if (c.find(f"{GSMLB}contactType") is not None
                        and c.find(f"{GSMLB}contactType").get(f"{XLINK}href") == config.NIL_URI)]
    check("A07", len(contacts_el) == EXP["contacts"] and len(nil_contacts) == EXP["contact_nil"],
          f"contacts: {len(contacts_el)}/{EXP['contacts']}; nil contactType: {len(nil_contacts)}/{EXP['contact_nil']}")

    # --- A08: SDS count, faulttype terms（pending 码 nil 容忍按幅核定） --------
    sds_bad = []
    n_nil_ft = 0
    for s in sds_el:
        ft = s.find(f"{GSMLB}faultType")
        href = ft.get(f"{XLINK}href", "") if ft is not None else ""
        if href == config.NIL_URI:
            n_nil_ft += 1
        elif ft is None or not href.startswith(config.CGI_CLASSIFIER + "/faulttype/"):
            sds_bad.append("faultType not CGI/nil")
    check("A08", len(sds_el) == EXP["sds"] and not sds_bad
          and n_nil_ft == EXP["sds_nil_faulttype"],
          f"SDS: {len(sds_el)}/{EXP['sds']}; nil faultType: {n_nil_ft}/{EXP['sds_nil_faulttype']}"
          f"（pending 码）; issues: {sds_bad[:3]}")

    # --- A09: plane-bearing stStructureDescription count and ranges ------------
    # 2026-09-26 v2：该槽 0..* 混装 ShearDisplacementStructureDescription（93 产状块）
    # 与 DisplacementValue（93 b 块+4 走滑钩块）——计数按 planeOrientation 载体过滤
    stsd = doc.findall(f".//{GSMLB}stStructureDescription")
    plane_blocks = [b for b in stsd if b.find(f".//{GSMLE}planeOrientation") is not None]
    azimuths = [float(x.text) for x in doc.findall(f".//{GSMLB}GSML_PlanarOrientation/{GSMLB}azimuth//{GSMLB}lowerValue")
                if x.text]
    dips = [float(x.text) for x in doc.findall(f".//{GSMLB}GSML_PlanarOrientation/{GSMLB}dip//{GSMLB}lowerValue")
            if x.text]
    az_bad = [a for a in azimuths if not (0 <= a < 360)]
    dip_bad = [d for d in dips if not (0 <= d <= 90)]
    check("A09", len(plane_blocks) == EXP["planes"] and not az_bad and not dip_bad,
          f"产状块: {len(plane_blocks)}/{EXP['planes']}（stSD 总 {len(stsd)}）; azimuth out of range: {az_bad[:3]}; dip: {dip_bad[:3]}")

    # --- A10: polarity only on 202004 ----------------------------------------
    pol = doc.findall(f".//{GSMLB}polarity")
    fol_bad = len(pol) != EXP["polarity"]
    check("A10", not fol_bad, f"polarity occurrences: {len(pol)} (expect {EXP['polarity']}, 202004 only)")

    # --- A11: fold profile URIs（pending 码 nil 容忍按幅核定） ------------------
    prof_hrefs = [x.get(f"{XLINK}href") for x in doc.findall(f".//{GSMLB}profileType")]
    n_nil_prof = sum(1 for h in prof_hrefs if h == config.NIL_URI)
    prof_bad = [h for h in prof_hrefs
                if h != config.NIL_URI
                and not (h or "").startswith("http://inspire.ec.europa.eu/codelist/FoldProfileTypeValue/")]
    check("A11", len(fold_el) == EXP["folds"] and not prof_bad
          and n_nil_prof == EXP["fold_nil"],
          f"folds: {len(fold_el)}/{EXP['folds']}; nil profileType: {n_nil_prof}/{EXP['fold_nil']}; bad URIs: {prof_bad}")

    # --- A12: axis order round-trip -------------------------------------------
    # Read one polygon MF posList and compare flipped coords against L1 source
    def _sample_axis_check() -> Tuple[bool, str]:
        polys = sources.read_theme("polygons")
        first = polys.iloc[0]
        src = first.geometry.__geo_interface__
        # 语义 id 重算（2026-10-02 裁定）：mf.{safe_norm}.{ord}——与 build 同源
        poly_ids = semantic_ids.polygon_mf_ids(polys, unit_mod.raw_to_norm_map())
        _safe = model._safe_ncname(poly_ids[0].split(".")[0])
        _ord = poly_ids[0].split(".")[1]
        target_id = f"{_safe}.{_ord}"
        mf = next((el for el in mf_el if el.get(f"{GML}id") == f"mf.{target_id}"), None)
        if mf is None:
            return False, f"MF {target_id} not found"
        pos = mf.find(f".//{GML}posList")
        if pos is None or not pos.text:
            return False, "no posList in first MF"
        nums = [float(v) for v in pos.text.split()]
        pairs = list(zip(nums[0::2], nums[1::2]))  # (lat, lon)
        coords = src["coordinates"]
        src_ring = coords[0] if src["type"] == "Polygon" else coords[0][0]
        src_ring = src_ring[: len(pairs)]
        mism = sum(1 for (la, lo), (x, y) in zip(pairs, src_ring) if abs(la - y) > 0 or abs(lo - x) > 0)
        return mism == 0, f"axis flip mismatches: {mism}"

    ok12, msg12 = _sample_axis_check()
    check("A12", ok12, f"axis round-trip (GML flipped == L1 source): {msg12}")

    lite_axis_ok = True
    lite_msg = ""
    try:
        with open(lite_dir / "geologic_unit_view.geojson", encoding="utf-8") as f:
            lite = json.load(f)
        f0 = lite["features"][0]
        polys = sources.read_theme("polygons")
        src = polys.iloc[0].geometry.__geo_interface__
        src_ring = [list(pt) for pt in (src["coordinates"][0] if src["type"] == "Polygon" else src["coordinates"][0][0])]
        lite_ring = [list(pt) for pt in (f0["geometry"]["coordinates"][0] if f0["geometry"]["type"] == "Polygon" else f0["geometry"]["coordinates"][0][0])]
        lite_axis_ok = src_ring == lite_ring
        lite_msg = f"lite first ring == source: {lite_axis_ok}"
    except Exception as exc:
        lite_axis_ok, lite_msg = False, f"lite axis check failed: {exc}"
    check("A12b", lite_axis_ok, f"Lite axis passthrough (unflipped): {lite_msg}")

    # --- A13: URI legality + internal byRef resolvable ------------------------
    hrefs = [el.get(f"{XLINK}href") for el in root.iter() if el.get(f"{XLINK}href")]
    illegal = [h for h in hrefs if h and not h.startswith("http")]
    internal = [h for h in hrefs if h and h.startswith(config.BASE_URI)]
    unresolved_internal = [
        h for h in internal
        if not (h in unit_uris or h.startswith(config.BASE_URI + "contact/")
                or h.startswith(config.BASE_URI + "fault/")
                or h.startswith(config.BASE_URI + "foliation/")
                or h.startswith(config.BASE_URI + "fold/")
                or h.startswith(config.BASE_URI + "mappedfeature/"))
    ]
    check("A13", not illegal and not unresolved_internal,
          f"illegal URIs: {illegal[:3]}; unresolved internal: {unresolved_internal[:3]}")

    # --- A14: quantity ranges -------------------------------------------------
    qr_bad = []
    for qr in doc.findall(f".//{GSMLB}GSML_QuantityRange"):
        lo = qr.find(f"{GSMLB}lowerValue")
        hi = qr.find(f"{GSMLB}upperValue")
        val = qr.find("{http://www.opengis.net/swe/2.0}value")
        uom = qr.find("{http://www.opengis.net/swe/2.0}uom")
        if lo is None or hi is None or uom is None:
            qr_bad.append("missing lo/hi/uom")
            continue
        if float(lo.text) > float(hi.text):
            qr_bad.append(f"lower>upper: {lo.text}>{hi.text}")
        if lo.text == hi.text and val is not None and val.text != f"{lo.text} {lo.text}":
            qr_bad.append(f"single value not doubled: {val.text}")
    check("A14", not qr_bad, f"QuantityRange issues: {qr_bad[:4]}")

    # --- A15: no empty elements ----------------------------------------------
    empties = []
    for tag in ("occurrence", "relatedFeature", "classifier"):
        for el in doc.findall(f".//{GSMLB}{tag}"):
            if len(el) == 0 and not el.get(f"{XLINK}href") and not (el.text or "").strip():
                empties.append(tag)
    check("A15", not empties, f"empty elements found: {empties[:4]}")

    # --- A16: member count -----------------------------------------------------
    check("A16", len(members) == EXP["members"], f"members: {len(members)}/{EXP['members']}")

    # --- A17: Lite views --------------------------------------------------------
    lite_bad = []
    expected_views = {
        "geologic_unit_view.geojson": ("Polygon", EXP["lite_counts"]["geologic_unit_view"]),
        "contact_view.geojson": ("LineString", EXP["lite_counts"]["contact_view"]),
        "shear_displacement_structure_view.geojson": ("LineString", EXP["lite_counts"]["shear_displacement_structure_view"]),
        "site_observation_view.geojson": ("Point", EXP["lite_counts"]["site_observation_view"]),
    }
    lite_ids: List[str] = []
    for fname, (gtype, count) in expected_views.items():
        path = lite_dir / fname
        if not path.exists():
            lite_bad.append(f"{fname} missing")
            continue
        with open(path, encoding="utf-8") as f:
            coll = json.load(f)
        feats = coll.get("features", [])
        if len(feats) != count:
            lite_bad.append(f"{fname}: {len(feats)}/{count}")
        gtypes = {ft["geometry"]["type"] for ft in feats}
        expected_g = {gtype} if gtype != "Polygon" else {"Polygon", "MultiPolygon"}
        if not gtypes <= expected_g:
            lite_bad.append(f"{fname}: geometry types {gtypes}")
        if fname == "contact_view.geojson":
            missing_ct = sum(1 for ft in feats if not ft["properties"].get("contactType_uri"))
            if missing_ct:
                lite_bad.append(f"contact_view: {missing_ct} missing contactType_uri")
        if fname == "site_observation_view.geojson":
            bad_rot = [ft["properties"].get("symbolRotation") for ft in feats
                       if not isinstance(ft["properties"].get("symbolRotation"), int)
                       or not (0 <= ft["properties"]["symbolRotation"] <= 359)]
            if bad_rot:
                lite_bad.append(f"site_observation: bad symbolRotation {bad_rot[:3]}")
        lite_ids.extend(str(ft.get("id") or ft["properties"].get("identifier", {}).get("value")) for ft in feats)
    dup_lite = [i for i, n in Counter(lite_ids).items() if n > 1]
    if dup_lite:
        lite_bad.append(f"duplicate lite identifiers: {dup_lite[:3]}")
    check("A17", not lite_bad, f"Lite issues: {lite_bad[:5]}")

    # --- A18: load-time composition + key alignment ----------------------------
    a18_msg = []
    polys = sources.read_theme("polygons")
    dist = polys["_src_file"].value_counts().to_dict()
    if (config.EXPECTED_POLYGON_DIST is not None
            and dist != config.EXPECTED_POLYGON_DIST):
        a18_msg.append(f"polygon composition {dist} != {config.EXPECTED_POLYGON_DIST}")
    check("A18", not a18_msg, f"load-time drift: {a18_msg}")

    # --- A19: namespace placeholder gate --------------------------------------
    text = gml_path.read_text(encoding="utf-8")
    has_placeholder = config.NAMESPACE_PLACEHOLDER in text
    gate_ok = has_placeholder if not config.NAMESPACE_FINAL else not has_placeholder
    check("A19", gate_ok,
          f"placeholder present={has_placeholder}, NAMESPACE_FINAL={config.NAMESPACE_FINAL}",
          level="WARN" if config.NAMESPACE_FINAL else "PASS")

    # --- A20: semantic spot checks（库尔干专属样例；英吉沙走 pending 检查） ------
    warn = []
    if args.sheet == "kurgan":
        f48 = [s for s in sds_el if "F48" in (s.find(f"{GML}name").text if s.find(f"{GML}name") is not None else "")]
        if not f48:
            warn.append("no SDS named F48 found")
        c43 = [c for c in contacts_el
               if c.find(f"{GSMLB}contactType") is not None
               and (c.find(f"{GSMLB}contactType").get(f"{XLINK}href") or "").endswith(
                   "/igneous_phase_contact")]
        if len(c43) != 4:  # 43×2 + 60×2（2026-09-26 裁定后）
            warn.append(f"igneous_phase_contact contacts: {len(c43)} (expect 4)")
    elif args.sheet == "yingjisha":
        pend_text = config.PENDING_OUT.read_text(encoding="utf-8") if config.PENDING_OUT.exists() else ""
        if "P-YJS-GZEEB-03" not in pend_text:
            warn.append("P-YJS-GZEEB-03 pending 未在册")
        n_nil_ft = sum(1 for s in sds_el
                       if (s.find(f"{GSMLB}faultType") is not None
                           and s.find(f"{GSMLB}faultType").get(f"{XLINK}href") == config.NIL_URI))
        if n_nil_ft == 0:
            warn.append("英吉沙应有 pending 码 nil faultType（03/37/35）但未发现")
    else:
        # 新幅通用抽查：pending 裁定单存在且非空（登记制在册）
        if not (config.PENDING_OUT.exists()
                and config.PENDING_OUT.stat().st_size > 0):
            warn.append("pending_review.md 缺失或为空")
    results.append(("A20", "WARN" if warn else "PASS", f"spot checks: {'; '.join(warn) if warn else 'ok'}"))

    # --- A21: 共享 b 配对（库尔干 3 例已消解；英吉沙 1:1 原生合规） -------------
    gml_text = etree.tostring(doc, encoding="unicode")
    n_contested = gml_text.count("注释配对二义")
    pend_text = config.PENDING_OUT.read_text(encoding="utf-8") if config.PENDING_OUT.exists() else ""
    check("A21", n_contested == 0 and "P-PAIR" not in pend_text,
          f"配对待裁定标记: {n_contested}/0; pending 无 P-PAIR 残留: {'P-PAIR' not in pend_text}")

    # --- A22: 六类模式标签分区 = 各幅普查定版 --------------------------------
    # 计数域限定 SDS gml:description（测量点 MF 描述也带模式标签，全文档计数会翻倍）
    sds_desc_text = "".join((s.find(f"{GML}description").text or "") for s in sds_el
                            if s.find(f"{GML}description") is not None)
    n_aba_ni = sds_desc_text.count("a-b-a·逆断层产状点")
    n_aba_zh = sds_desc_text.count("a-b-a·正断层产状点")
    n_ab_ni = sds_desc_text.count("a-b·逆断层产状点")
    n_ab_zh = sds_desc_text.count("a-b·正断层产状点")
    n_full = sds_desc_text.count("倾向-倾角产状点")
    n_only = sds_desc_text.count("倾向产状点（仅倾向")
    got6 = (n_aba_ni, n_aba_zh, n_ab_ni, n_ab_zh, n_full, n_only)
    check("A22", got6 == EXP["six_mode"],
          f"六类标签: {got6} vs 期望 {EXP['six_mode']}（合计 {sum(got6)}/{EXP['planes']}）")

    # --- A23: 编图矛盾横幅（库尔干 3 实体=7 段；英吉沙登记册暂不套用） ----------
    n_banner = gml_text.count("【编图矛盾登记】")
    check("A23", n_banner == EXP["banners"],
          f"矛盾横幅 SDS 数: {n_banner}/{EXP['banners']}")

    # --- A24: DisplacementValue 块（辅助点非实体原则 v2，2026-09-26） -----------
    dv_el = doc.findall(f".//{GSMLE}DisplacementValue")
    ms_hrefs = [e.get(f"{XLINK}href", "") for e in doc.findall(f".//{GSMLE}movementSense")]
    ms_dist = Counter(h.rsplit("/", 1)[-1] for h in ms_hrefs)
    hwd = doc.findall(f".//{GSMLE}hangingWallDirection//{GSMLB}trend//{GSMLB}lowerValue")
    hwd_vals = [float(x.text) for x in hwd if x.text]
    hwd_bad = [v for v in hwd_vals if not (0 <= v < 360)]
    check("A24", len(dv_el) == EXP["dv_blocks"] and ms_dist == EXP["ms_dist"]
          and len(hwd_vals) == EXP["hwd"] and not hwd_bad,
          f"DisplacementValue: {len(dv_el)}/{EXP['dv_blocks']}; "
          f"movementSense 分布 {dict(ms_dist)} vs {EXP['ms_dist']}; "
          f"hangingWallDirection trend: {len(hwd_vals)}/{EXP['hwd']} 越界 {hwd_bad[:3]}")

    # --- A25: 单元对接地关系 GeologicFeatureRelation（v2.1） --------------------
    rel_el = doc.findall(f".//{GSMLE}GeologicFeatureRelation")
    rel_targets = [r.find(f"{GSMLB}relatedFeature").get(f"{XLINK}href", "")
                   for r in rel_el if r.find(f"{GSMLB}relatedFeature") is not None]
    rel_terms = [r.find(f"{GSMLE}relationship").get(f"{XLINK}href", "")
                 for r in rel_el if r.find(f"{GSMLE}relationship") is not None]
    ct_prefix = config.CGI_CLASSIFIER + "/contacttype/"
    tgt_bad = [h for h in rel_targets if not h.startswith(config.BASE_URI + "geologicunit/")]
    term_bad = [h for h in rel_terms if not h.startswith(ct_prefix)]
    self_rel = [r.get(f"{GML}id") for r in rel_el
                if r.get(f"{GML}id", "").split(".")[-2] == r.get(f"{GML}id", "").split(".")[-1]]
    check("A25", len(rel_el) == EXP["relations"] and not tgt_bad and not term_bad and not self_rel,
          f"GeologicFeatureRelation: {len(rel_el)}/{EXP['relations']}; 非法 target: {len(tgt_bad)}; "
          f"非 contacttype relationship: {len(term_bad)}; 自指: {self_rel[:3]}")

    # --- A26: 断层产状测量点 MF（垂足锚定，09-27 用户裁定） ---------------------
    fp_mfs = [m for m in mf_el if (m.get(f"{GML}id") or "").startswith("mf.fp.")]
    sds_uris = {s.find(f"{GML}identifier").text for s in sds_el
                if s.find(f"{GML}identifier") is not None}
    fp_bad = []
    for m in fp_mfs:
        spec = m.find(f"{GSMLB}specification")
        href = spec.get(f"{XLINK}href", "") if spec is not None else ""
        if href not in sds_uris:
            fp_bad.append(f"specification 未解析: {href}")
    # 垂足硬校验：从源数据独立重算——b 点(L1 fault_aux)到归属段(L1 faults)的投影
    import geopandas as _gpd
    from shapely.geometry import Point as _Pt
    l1_fl = _gpd.read_file(config.GEOJSON_L1 / "faults.geojson")
    l1_fa = _gpd.read_file(config.GEOJSON_L1 / "fault_aux.geojson")
    l1_fa["_src_id"] = l1_fa["_src_id"].astype(int)
    b_sub = l1_fa[(l1_fa["kind"] == "symbol")
                  & (l1_fa["sub_no"].astype(str).str.replace(".0", "", regex=False) == "1894")
                  & (l1_fa["status"].astype(str) == "normal")]
    # 语义 id 集合比对（2026-10-02 裁定）：mf.fp.{fault_id}.{序}——与 build 同源
    _auxchain_csv = config.SHEET_ROOT / f"fault_aux_{config.SHEET_KEY}.csv"
    _auxchain_df = __import__("pandas").read_csv(_auxchain_csv, dtype=str)         if _auxchain_csv.exists() else None
    mp_of = semantic_ids.measure_point_ids(l1_fa, _auxchain_df, l1_fl)
    expect_mp_ids = {f"mf.{v['mp_id']}" for v in mp_of.values()}
    got_mp_ids = {m.get(f"{GML}id") for m in fp_mfs}
    mp_id_bad = sorted(got_mp_ids ^ expect_mp_ids)
    # 垂足硬校验（坐标多重集比对——语义 id 下不复用 aux_idx 解析）
    gml_fp_pos = Counter()
    for m in fp_mfs:
        pos = m.find(f".//{GML}pos")
        if pos is not None and pos.text:
            lat, lon = (float(v) for v in pos.text.split()[:2])
            gml_fp_pos[(round(lon, 9), round(lat, 9))] += 1  # GML 轴序 lat,lon → 还原 lon,lat
    offseg = offband = mismatch = clamps = 0
    char = float(get_profile(args.sheet).char_dists.get("b") or EXP["char_dist_b"])
    for _, r in b_sub.iterrows():
        aux_idx = int(r["_src_id"])
        seg = int(r["seg_idx"])
        seg_geom = l1_fl.geometry.iloc[seg]
        expect_pt = seg_geom.interpolate(seg_geom.project(r.geometry))
        got_key = (round(expect_pt.x, 9), round(expect_pt.y, 9))
        if gml_fp_pos[got_key] <= 0:
            mismatch += 1
            continue
        gml_fp_pos[got_key] -= 1
        got = got_key
        d_pt = ((got[0] - expect_pt.x) ** 2 + (got[1] - expect_pt.y) ** 2) ** 0.5
        if d_pt > 1e-9:
            mismatch += 1
            continue
        # on-seg：垂足到段距离应为 0；摆放距应在特征距离带 [0.5,3]×char
        if seg_geom.distance(_Pt(got)) > 1e-9:
            offseg += 1
        proj_m = seg_geom.project(r.geometry)
        if proj_m <= 1e-9 or proj_m >= seg_geom.length - 1e-9:
            clamps += 1
        # 摆放距（米制，度→米换算按纬度缩放经度）
        import math as _math
        lat0 = (expect_pt.y + r.geometry.y) / 2.0
        d_b_foot = _math.hypot((got[0] - r.geometry.x) * 111320.0 * _math.cos(_math.radians(lat0)),
                               (got[1] - r.geometry.y) * 111320.0)
        if not (0.5 * char <= d_b_foot <= 3.0 * char):
            offband += 1
    check("A26", len(fp_mfs) == EXP["measure_points"] and not fp_bad
          and not mp_id_bad
          and mismatch == 0 and offseg == 0,
          f"测量点 MF: {len(fp_mfs)}/{EXP['measure_points']}; specification 未解析: {len(fp_bad)}; "
          f"垂足错位/缺失: {mismatch}; 离线: {offseg}; 出特征带: {offband}; 端点钳制: {clamps}")

    # --- A27: 化石/泥火山标本视图（2026-09-28 转入，lite 第六视图） -------------
    import json as _json27
    sp_path = config.LITE_OUT / "fossil_specimen_view.geojson"
    sp_bad = []
    sp_n = sp_viol = 0
    if not sp_path.exists():
        sp_bad.append("fossil_specimen_view.geojson 缺失")
    else:
        sp_doc = _json27.loads(sp_path.read_text(encoding="utf-8"))
        sp_feats = sp_doc.get("features", [])
        sp_n = len(sp_feats)
        for ft in sp_feats:
            pr = ft.get("properties", {})
            ident = str((pr.get("identifier") or {}).get("value", ""))
            if "/specimen/" not in ident:
                sp_bad.append(f"identifier 形态: {ident[:60]}")
            if not pr.get("specimenType"):
                sp_bad.append(f"specimenType 空: {ident[-30:]}")
            if not str(pr.get("genericSymbolizer", "")).isdigit():
                sp_bad.append(f"genericSymbolizer 非码: {pr.get('genericSymbolizer')}")
            if (ft.get("geometry") or {}).get("type") != "Point":
                sp_bad.append(f"geometry 非点: {ident[-30:]}")
            if "违反（待裁定）" in str(pr.get("description", "")):
                sp_viol += 1
    exp_viol = int(EXP.get("fossil_violations", 0))  # 画像驱动（库尔干
    # idx2009 违反化石 1 处；2026-10-02 泛化：jws 副本同 1）
    check("A27", sp_n == EXP["lite_counts"]["fossil_specimen_view"]
          and not sp_bad and sp_viol == exp_viol,
          f"标本视图: {sp_n}/{EXP['lite_counts']['fossil_specimen_view']}; "
          f"结构违规: {len(sp_bad)}{sp_bad[:3]}; 违反标记: {sp_viol}/{exp_viol}")

    # --- Report ----------------------------------------------------------------
    fails = [r for r in results if r[1] == "FAIL"]
    warns = [r for r in results if r[1] == "WARN"]
    lines = [
        f"# GeoSciML 转换对账报告（{config.SHEET_TITLE}）",
        "",
        f"生成: {__import__('datetime').date.today().isoformat()} · GML: `{gml_path.name}` · Lite: `{lite_dir}`",
        "",
        "## 断言汇总",
        "",
        f"PASS {sum(1 for r in results if r[1]=='PASS')} / WARN {len(warns)} / FAIL {len(fails)}",
        "",
        "| ID | 级别 | 内容 |",
        "|---|---|---|",
    ]
    for cid, level, msg in results:
        lines.append(f"| {cid} | {level} | {msg} |")
    lines += [
        "",
        "## 源-目标计数",
        "",
        "| 主题 | 源(L1) | 目标 | 说明 |",
        "|---|---|---|---|",
        f"| 单元 GeologicUnit | {EXP['units']} | {len(units_el)} | 概念对象 |",
        f"| 图斑 MappedFeature | {EXP['poly_mfs']} | {len(poly_mfs)} | {config.EXPECTED_POLYGON_DIST} |",
        f"| 界线 Contact | — | {len(contacts_el)} | 剔 GZBD=10/81 后为 {EXP['contacts']} |",
        f"| 断层 SDS | {EXP['sds']} | {len(sds_el)} | |",
        f"| 断层产状描述 stStructureDescription | {EXP['planes']} 箭头 | {len(stsd)} | 含 DisplacementValue 块 |",
        f"| 产状 Foliation | {EXP['lite_counts']['site_observation_view']} | {len(fol_el)} | |",
        f"| 褶皱 Fold | {EXP['folds']} | {len(fold_el)} | Lite 不出 |",
        f"| member 总数 | — | {len(members)} | 期望 {EXP['members']} |",
        "",
        "## pending 状态",
        "",
        f"映射文件 pending 节: {len(mapping.pending())} 项 → `{config.PENDING_OUT}`",
        f"nil contactType: {len(nil_contacts)}（期望 {EXP['contact_nil']}）",
    ]
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")

    for cid, level, msg in results:
        mark = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[level]
        print(f"  {mark} {cid}: {msg}")
    print(f"\nreport: {args.report}")
    print(f"PASS {sum(1 for r in results if r[1]=='PASS')} / WARN {len(warns)} / FAIL {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
