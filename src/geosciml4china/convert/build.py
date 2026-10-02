"""Build one sheet's GeoSciML outputs (GML + Lite views + pending list).

CLI: g4c build --sheet kurgan [--only gml|lite|pending] [--sample N]
（驱动移植自 build_geosciml.py，2026-09-28 入包）
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List, Optional

import pandas as pd

from ..sheets import list_sheets
from . import config, ids, mapping, model, sources
from . import units as unit_mod
from .emit import document, features
from .model import (
    AttitudeRec,
    ContactRec,
    FaultAuxPlane,
    FaultRec,
    MappedFeatureRec,
)


def assemble_units() -> Dict[str, model.UnitRec]:
    return unit_mod.build_units()


_CONF_RANK = {"adjudicated": 6, "verified": 5, "memoir": 4, "memoir_multi": 4,
              "inferred": 3, "generic": 2, "generic_rules": 2}


def assemble_unit_relations(units: Dict[str, model.UnitRec]) -> int:
    """单元对接地关系（v2.1，GeologicFeatureRelation inline 于年轻单元）。

    数据源：_gzbd_calibration_report.csv 可定向行（young_side 图面证据
    left/right + 左右单元经 units.raw_to_norm_map 归一）。同对多段去重：
    verdict=标定通过优先、rule_conf 高者优先；relationship 取该段的
    GZBD_eff 已定 contacttype 词（与段级 Contact 一致）。仅 分歧 行覆盖的
    对仍发射（方向有图面证据），描述注明交检核。
    """
    import re

    r2n = unit_mod.raw_to_norm_map()

    def norm_of(v: str) -> Optional[str]:
        code = re.sub(r"（.*?）|\(.*?\)", "", v or "").strip()
        return r2n.get(code)

    best: Dict[tuple, dict] = {}
    for row in sources.read_calibration_report():
        ln, rn = norm_of(row["left"]), norm_of(row["right"])
        if not ln or not rn or ln == rn:
            continue
        if row["young_side"] == "left":
            yn, on = ln, rn
        elif row["young_side"] == "right":
            yn, on = rn, ln
        else:
            continue
        if yn not in units or on not in units:
            continue
        key = (yn, on)
        code = row["gzbd"].strip()
        code = code[:-2] if code.endswith(".0") else code
        term = mapping.gzbd_row(code.zfill(2)).get("term")
        if not term:
            continue
        rank = (1 if row["verdict"] == "标定通过" else 0,
                _CONF_RANK.get(row["rule_conf"], 0))
        if key not in best:
            best[key] = {"term": term, "rank": rank, "n": 1,
                         "verdict": row["verdict"], "conf": row["rule_conf"],
                         "codes": {code.zfill(2)}}
        else:
            b = best[key]
            b["n"] += 1
            b["codes"].add(code.zfill(2))
            if rank > b["rank"]:
                b.update(term=term, rank=rank, verdict=row["verdict"],
                         conf=row["rule_conf"])
    n_rel = 0
    for (yn, on), b in sorted(best.items()):
        note = (f"{b['n']} 段佐证（GZBD={','.join(sorted(b['codes']))}），"
                f"verdict={b['verdict']}（conf={b['conf'] or '码面'}）；"
                f"source=年轻单元、target=较老单元（young_side 图面证据）")
        units[yn].relations.append({"target_norm": on, "term": b["term"],
                                    "note": note})
        n_rel += 1
    return n_rel


def assemble_polygon_mfs(
    units: Dict[str, model.UnitRec], sample: Optional[int] = None
) -> List[MappedFeatureRec]:
    gdf = sources.read_theme("polygons")
    raw2norm = unit_mod.raw_to_norm_map()
    dist = gdf["_src_file"].value_counts().to_dict()
    if config.EXPECTED_POLYGON_DIST is not None:  # None=首接基线免闸（实测后回填注册）
        assert dist == config.EXPECTED_POLYGON_DIST, f"polygons composition drift: {dist}"
    else:
        print(f"  面分布首接实测（未注册闸）: {dist}")
    out: List[MappedFeatureRec] = []
    # 语义 id（2026-10-02 裁定）：mf.{norm}.{ord}——图元 FEATUREID 不入产品
    poly_ids = ids.polygon_mf_ids(gdf, raw2norm)
    ids.assert_no_norm_collisions(raw2norm.values())
    for i, (_, row) in enumerate(gdf.iterrows()):
        if sample is not None and i >= sample:
            break
        raw = row["QDUECC_eff"]
        norm = raw2norm.get(raw)
        if norm is None:
            raise KeyError(f"QDUECC_eff {raw!r} not in color units (row {row['_src_id']})")
        unit = units[norm]
        out.append(
            MappedFeatureRec(
                feature_id=poly_ids[i],
                specification_uri=unit.uri,
                specification_title=unit.name,
                geometry=row.geometry.__geo_interface__,
                map_code=str(raw),
                src_file=str(row["_src_file"]),
            )
        )
    return out


def _clean_optional_str(v):
    """NaN/空串 → None（B2 修复 2026-09-28：NaN 真值曾使回退链失效）。"""
    if v is None:
        return None
    try:
        if v != v:  # NaN
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return s or None


# B1 修复登记（2026-09-28 用户裁定）：制图误差（剔除）行不发射
_EXCLUDED_CONTACTS: List[int] = []


def assemble_contacts(sample: Optional[int] = None) -> List[ContactRec]:
    gdf = sources.read_theme("boundaries")
    # 语义 id（2026-10-02 裁定）：c.{GZBD_eff}.{类内序}——图元 _src_id 不入产品
    c_ids = ids.contact_ids(gdf)
    out: List[ContactRec] = []
    for _, row in gdf.iterrows():
        code = row["GZBD_eff"]
        row_map = mapping.gzbd_row(code)
        status = row_map.get("status")
        if status in ("skip_fault", "skip_nongeologic"):
            continue
        # B1：判别系统剔除裁决必须被执行——剔除=非地质接触，不发射
        if str(row.get("status") or "normal") == "excluded":
            _EXCLUDED_CONTACTS.append(int(row["_src_id"]))
            continue
        if sample is not None and len(out) >= sample:
            break
        decided = status == "decided" and row_map.get("term")
        _cid = c_ids[int(row["_src_id"])]
        out.append(
            ContactRec(
                src_id=int(row["_src_id"]),
                code=code,
                ord=int(_cid.split(".")[1]),
                sem_label=row["sem_label"],
                verdict=row["verdict"],
                        younger_side=(
                    row.get("younger_side")
                    if isinstance(row.get("younger_side"), str)
                    else None
                ),
                geometry=row.geometry.__geo_interface__,
                decided=bool(decided),
                contacttype_term=row_map.get("term") if decided else None,
                contacttype_label=row_map.get("term", "") if decided else "",
                observation_term=row_map.get("obs") if decided else None,
                pending_ref=row_map.get("ref"),
            )
        )
    return out


def assemble_faults(sample: Optional[int] = None) -> List[FaultRec]:
    gdf = sources.read_theme("faults")
    aux_gdf = sources.read_theme("fault_aux")
    assoc = sources.read_aux_assoc()
    pairs, pair_conflicts = sources.read_aux_pairs()   # 共享 b 隔离待裁定（09-26）
    triplets = sources.read_aux_triplets()             # 六类模式标签（09-26 定版）
    conflict_entities = sources.read_fault_conflict_entities()  # 编图矛盾登记册
    # 语义 id（2026-10-02 裁定）：sds.{fault_id}.{段序} / fp.{fault_id}.{沿弧序}
    seg_ord_of = ids.fault_seg_ordinals(gdf)
    _auxchain_csv = config.SHEET_ROOT / f"fault_aux_{config.SHEET_KEY}.csv"
    _auxchain_df = pd.read_csv(_auxchain_csv, dtype=str) \
        if _auxchain_csv.exists() else None
    mp_of = ids.measure_point_ids(aux_gdf, _auxchain_df, gdf)

    # 1894 arrows grouped by seg_idx: azimuth=dip_az;
    # dip=配对注释(1:1 合规) -> GZECE>0（含配对待裁定隔离回落） -> None
    planes_by_seg: Dict[int, List[FaultAuxPlane]] = {}
    aux_geom: Dict[int, Any] = {}  # aux_idx → b 点几何（垂足计算源，原始点位不入产品）
    for _, row in aux_gdf.iterrows():
        if row.get("kind") != "symbol" or int(row.get("sub_no") or 0) != 1894:
            continue
        # 异常册/剔除点不成平面（英吉沙 status=anomaly；库尔干 confirmed_error 已无 sub_no）
        if str(row.get("status") or "normal") not in ("normal", ""):
            continue
        seg = row.get("seg_idx")
        if seg is None:
            continue
        seg = int(seg)
        az = row.get("dip_az")
        if az is None:
            continue
        aux_idx = int(row["_src_id"])
        aux_geom[aux_idx] = row.geometry
        dip, dip_src = None, ""
        _nid = None
        if aux_idx in pair_conflicts:
            pass  # 注释配对争议隔离：回落段 GZECE（在下方实体循环内回填）
        elif aux_idx in pairs and pairs[aux_idx]["dip"] is not None:
            _nid = pairs[aux_idx].get("note_idx")
            # 语义化来源（2026-10-02 裁定）：注释① 而非 MapGIS 注释号
            dip, dip_src = pairs[aux_idx]["dip"], (
                "注释①" if _nid is not None else "配对注释")
        elif aux_idx in assoc and assoc[aux_idx]["dip"] is not None:
            dip, dip_src = assoc[aux_idx]["dip"], "配对注释"
        # 六类模式标签+movement_sense（2026-10-02 用户裁定：a 依附于 b，
        # 与注释共同构成 b 的断层产状测量地质语义——a 不构成实体，
        # 其语义经三联体 verdict 折叠入 b 的 mode，成员号随注记出站）
        tri = triplets.get(aux_idx)
        a_ids = ""
        if tri:
            mode = f"{tri['form']}·{tri['verdict']}"
            a_ids = tri.get("a1281", "")
            # 三态显式判别（2026-09-29 修）：存疑（点近线侧别不可判等）
            # 不得落入 reverse——原 `"正" in verdict else reverse` 缺陷
            if "正断层" in tri["verdict"]:
                msense = "normal"
            elif "逆断层" in tri["verdict"]:
                msense = "reverse"
            else:
                msense = "no_movement_sense"
        elif aux_idx in pair_conflicts:
            mode = "倾向-倾角产状点（无运动指示）"
            msense = "no_movement_sense"
        elif aux_idx in pairs or (aux_idx in assoc and assoc[aux_idx]["dip"] is not None):
            mode = "倾向-倾角产状点（无运动指示）"
            msense = "no_movement_sense"
        else:
            mode = "倾向产状点（仅倾向，无倾角无运动指示）"
            msense = "no_movement_sense"
        _mp = mp_of.get(aux_idx, {})
        planes_by_seg.setdefault(seg, []).append(
            FaultAuxPlane(azimuth=float(az), dip=dip, aux_idx=aux_idx,
                          mode=mode, dip_source=dip_src, movement_sense=msense,
                          a_ids=a_ids,
                          mp_id=_mp.get("mp_id", f"fp.{aux_idx}"),
                          mp_label=_mp.get("label", f"b{aux_idx}"),
                          a_label=ids.a_designation(a_ids),
                          note_label=("注释①" if _nid is not None else "")))

    # 走滑钩旋向 → slip_sense（2026-10-02 接线：空间识别 CSV 消费——auxchain
    # 产出 _fault_hooks_<key>.csv，按区间段号展开；旋向=垂足区间内区段的
    # 运动学性质（钩对表征所属断层的某段，用户想法 2026-10-01）；
    # 左行→sinistral / 右行→dextral，区间跨度随注记出站）
    slip_by_seg: Dict[int, str] = {}
    slip_span_by_seg: Dict[int, str] = {}
    _hpath = config.SHEET_ROOT / f"_fault_hooks_{config.SHEET_KEY}.csv"
    if _hpath.exists():
        _hdf = pd.read_csv(_hpath, dtype=str)
        for _, _hr in _hdf.iterrows():
            _segs = [int(x) for x in str(_hr.get("segs") or "").split(",")
                     if x.strip()]
            _sense = ("sinistral" if str(_hr["sense"]) == "左行" else "dextral")
            _span = (f"（滑移区段 {float(_hr['foot_arc1_m'])/1000:.1f}–"
                     f"{float(_hr['foot_arc2_m'])/1000:.1f}km）")
            for _sg in _segs:
                slip_by_seg[_sg] = _sense
                slip_span_by_seg[_sg] = _span

    out: List[FaultRec] = []
    for i, (_, row) in enumerate(gdf.iterrows()):
        if sample is not None and i >= sample:
            break
        seg_idx = int(row["_src_id"])
        code = row["gzeeb_eff"]
        row_map = mapping.gzeeb_row(code)
        obs = row_map.get("obs") or mapping.evidence_observation(row["evidence_class"])
        planes = planes_by_seg.get(seg_idx, [])
        # 2026-09-29 用户对齐裁定：断层产状测量点=实测产状——缺失倾角注释点
        # 时倾角留空，不从所属断层继承（GZECE 回落废止）。GZECE 仅存于段级
        # 属性（FaultRec.gzece 记录值）供核验参考，不再注入测量点倾角。
        gzece = float(row["GZECE"]) if row.get("GZECE") not in (None, "") else 0.0
        filled: List[FaultAuxPlane] = []
        notes: List[str] = []
        seg_geom = row.geometry  # 段线几何（垂足锚定源）
        for plane in planes:
            dip, src = plane.dip, plane.dip_source
            if plane.aux_idx in pair_conflicts:
                src = "配对待裁定"  # 注释争议隔离：倾角留空（候选入 note）
            # 测量点位=b 到所属段的垂足（09-27 用户裁定保留；b 原始点位不入产品）
            foot = None
            bg = aux_geom.get(plane.aux_idx)
            if bg is not None and seg_geom is not None and not seg_geom.is_empty:
                foot_pt = seg_geom.interpolate(seg_geom.project(bg))
                foot = foot_pt.__geo_interface__
            note = f"产状点 {plane.mp_label}：{plane.mode}"
            if plane.a_label:
                note += f"（{plane.a_label}）"
            note += f"；倾向 {plane.azimuth:g}°"
            if dip is not None:
                note += f"∠{dip:g}°（{plane.note_label or src}）"
            else:
                note += "（仅倾向）"
            if plane.aux_idx in pair_conflicts:
                cands = "、".join(f"{n}={d:g}°" for n, d in pair_conflicts[plane.aux_idx])
                _fid = mp_of.get(plane.aux_idx, {}).get("fault_id",
                                                        str(row["fault_id"]))
                _ord = mp_of.get(plane.aux_idx, {}).get("ord", 0)
                note += (f"；注释配对二义（候选 {cands}）交人工裁定"
                         f"（P-PAIR-{_fid}-{_ord}）")
            notes.append(note)
            filled.append(FaultAuxPlane(azimuth=plane.azimuth, dip=dip,
                                        aux_idx=plane.aux_idx, mode=plane.mode,
                                        dip_source=src,
                                        movement_sense=plane.movement_sense,
                                        a_ids=plane.a_ids,
                                        mp_id=plane.mp_id,
                                        mp_label=plane.mp_label,
                                        a_label=plane.a_label,
                                        note_label=plane.note_label,
                                        foot=foot))
        # 编图矛盾横幅（登记册驱动，不改码）
        if (str(row["fault_id"]), int(row["_src_id"])) in conflict_entities:
            notes.append("【编图矛盾登记】本实体辅助点产状判别与 GZEEB 编码矛盾，"
                         "已登记交人工裁定、不改码（fault_aux_code_semantics.json）")
        # B3（2026-09-28 用户裁定）：违反（待裁定）行如实标记——与矛盾横幅
        # 同构的 verdict 声明（登记不改码）
        _fv = _clean_optional_str(row.get("verdict"))
        if _fv and ("违反" in _fv or "待裁定" in _fv):
            notes.append(f"标定 verdict：{_fv}（已登记交人工裁定、不改码）")
        # 活动性层描述出站（2026-09-28 处置 A）：37 码经词表 description_append
        # 承载（与 31 同构）；非 37 的活动/活动候选行在此追加（登记不改码）；
        # 第四系界线重合证据注记（活动性强先验）随 checks 出站
        _act = _clean_optional_str(row.get("activity"))
        if _act and "候选" in _act:
            notes.append(f"活动性：{_act}（登记不改码）")
        elif _act and _act != "未评" and code != "37":
            notes.append("活动性：活动断层")
        _ch = _clean_optional_str(row.get("checks"))
        if _ch:
            for _tok in _ch.split("；"):
                if ("第四系界线重合" in _tok or "活动性佐证" in _tok
                        or "Q-地层边界重合" in _tok):
                    # 2026-10-02 活动断层审计：补面元拓扑通道证据串出站
                    notes.append(_tok)
        out.append(
            FaultRec(
                feature_id=(f"{row['fault_id']}.{seg_ord_of[int(row['_src_id'])][1]}"
                            if int(row["_src_id"]) in seg_ord_of
                            else row["FEATUREID"]),
                fault_id=row["fault_id"],
                fault_name=_clean_optional_str(row.get("fault_name")),
                gzeeb_eff=code,
                structural_type=row["structural_type"],
                evidence_class=row["evidence_class"],
                faulttype_term=row_map.get("term"),
                faulttype_label=row_map.get("term", ""),
                observation_term=obs,
                observation_label=(obs or "").replace("_", " "),
                description_append=row_map.get("description_append", ""),
                gzehg=row.get("GZEHG") or "",
                gzece=gzece,
                attitude_note="；".join(notes),
                slip_sense=slip_by_seg.get(seg_idx, ""),
                slip_span=slip_span_by_seg.get(seg_idx, ""),
                planes=filled,
                geometry=row.geometry.__geo_interface__,
            )
        )
    return out


def assemble_attitudes(
    units: Dict[str, model.UnitRec], sample: Optional[int] = None
) -> List[AttitudeRec]:
    gdf = sources.read_theme("attitude")
    raw2norm = unit_mod.raw_to_norm_map()
    # 语义 id（2026-10-02 裁定）：fol.{host}.{宿主内序}
    fol_ids = ids.foliation_ids(gdf, raw2norm)
    out: List[AttitudeRec] = []
    for i, (_, row) in enumerate(gdf.iterrows()):
        if sample is not None and i >= sample:
            break
        sem = row["sem_type"]
        row_map = mapping.foliation_row(sem)
        if not row_map.get("term"):
            row_map = mapping.foliation_row(row["GZBBGA"])
        host_norm = raw2norm.get(row["host_code"]) if isinstance(row.get("host_code"), str) else None  # noqa: E501
        # B3（2026-09-28 用户裁定）：违反（待裁定）行如实标记
        _av = _clean_optional_str(row.get("verdict"))
        note = (f"标定 verdict：{_av}（已登记交人工裁定、不改码）"
                if _av and ("违反" in _av or "待裁定" in _av) else "")
        out.append(
            AttitudeRec(
                src_id=int(row["_src_id"]),
                gzbbga=row["GZBBGA"],
                sem_type=sem,
                azimuth=float(row["GZBBAC"]) % 360.0,  # 单位圆规范化
                # （360≡0；奥依亚依拉克 1 点 GZBBAC=360 首遇，A09 约定 [0,360)；
                # 库尔干/英吉沙无 360 值→恒等，逐字节一致保持）
                dip=(float(row["GZBBAD"]) if str(row["GZBBAD"]).strip() != ""
                     else None),  # 空倾角（巴什库尔干 17 点）→None 如实缺省
                foliation_term=row_map.get("term"),
                foliation_label=row_map.get("term", ""),
                overturned=(row_map.get("polarity") == "overturned"),
                host_norm=host_norm,
                host_name=units[host_norm].name if host_norm in units else None,
                note=note,
                ord=fol_ids[int(row["_src_id"])]["ord"],
                geometry=row.geometry.__geo_interface__,
            )
        )
    return out


def assemble_specimens(units: Dict[str, model.UnitRec],
                       sample: Optional[int] = None) -> List[model.SpecimenRec]:
    """化石/泥火山产地标本（2026-09-28 转入，lite 第六视图 GeologicSpecimenView）。"""
    raw2norm = unit_mod.raw_to_norm_map()
    out: List[model.SpecimenRec] = []
    _frames = []
    for theme in ("fossil", "mudvolcano"):
        if (config.GEOJSON_L1 / f"{theme}.geojson").exists():
            _frames.append((theme, sources.read_theme(theme)))
    sp_ids = ids.specimen_ids(_frames, raw2norm)
    for theme, gdf in _frames:
        for i, (_, row) in enumerate(gdf.iterrows()):
            if sample is not None and i >= sample:
                break
            host_norm = raw2norm.get(row["host_code"]) \
                if isinstance(row.get("host_code"), str) else None
            v = _clean_optional_str(row.get("verdict"))
            note = (f"标定 verdict：{v}（已登记交人工裁定、不改码）"
                    if v and ("违反" in v or "待裁定" in v) else "")
            out.append(
                model.SpecimenRec(
                    src_id=int(row["_src_id"]),
                    kind=model.SPECIMEN_KINDS[theme],
                    sem_type=_clean_optional_str(row.get("sem_type")) or "未知",
                    sub_no=str(row.get("symbol_no") or ""),
                    height=str(row.get("height") or "2.0"),
                    angle=str(row.get("angle") or "0.0"),
                    verdict=v or "",
                    host_norm=host_norm,
                    host_name=(units[host_norm].name
                               if host_norm in units else None),
                    note=note,
                    ord=sp_ids[(theme, i)]["ord"],
                    geometry=row.geometry.__geo_interface__,
                )
            )
    return out


def assemble_folds(sample: Optional[int] = None) -> List[model.FoldRec]:
    gdf = sources.read_theme("fold")
    out: List[model.FoldRec] = []
    for i, (_, row) in enumerate(gdf.iterrows()):
        if sample is not None and i >= sample:
            break
        out.append(
            model.FoldRec(
                feature_id=str(i + 1),  # 语义 id（fold.N，2026-10-02 裁定）
                name=row["GZCAB"],
                gzce=row["GZCE"],
                profile_term=mapping.load()["gzce_foldprofile"][row["GZCE"]]["term"],
                geometry=row.geometry.__geo_interface__,
            )
        )
    return out


def _stale_inputs() -> list[str]:
    """时效守卫（2026-10-02 b1950 案）：装配输入（L1 主题件）不得旧于其
    标定源。违例=某标定域在 L1 物化后被单域重跑而 materialize 未跟进——
    GML 将与最新判别不一致（b1950：assoc=fault_aux 表 F061，GML 却发 F065）。
    09-28 正典件装配链教训的硬闸：build 入口拒绝陈旧 L1，点名缺失阶段，
    不再静默装配。"""
    from pymapgis.semantics.profile import get_profile as _prof

    root, l1 = config.SHEET_ROOT, config.GEOJSON_L1
    pairs = [
        (root / f"fault_aux_{config.SHEET_KEY}.csv", l1 / "fault_aux.geojson", "auxchain"),
        (root / f"_fault_triplets_{config.SHEET_KEY}.csv", l1 / "fault_aux.geojson",
         "auxchain 三联体"),
        (root / f"_gzeeb_calibration_{config.SHEET_KEY}.csv", l1 / "faults.geojson",
         "gzeeb"),
        (root / "_attitude_calibration.csv", l1 / "attitude.geojson", "attitudes"),
        (root / f"_fossil_calibration_{config.SHEET_KEY}.csv", l1 / "fossil.geojson",
         "fossils"),
        (root / "_inferred_fault_calibration.csv", l1 / "faults.geojson",
         "inferred_faults"),
        # 泛化（2026-10-02 审计）：实体表名经剖面通道——原硬编码
        # 库尔干名致英吉沙/奥依亚依拉克/巴什库尔干 entities 时效闸被绕过
        (root / (_prof().entities_csv or "fault_entities.csv"),
         l1 / "faults.geojson", "entities"),
    ]
    if config.CALIBRATION_CSV is not None:
        pairs.append((config.CALIBRATION_CSV, l1 / "boundaries.geojson", "gzbd"))
    stale = []
    for src, tgt, stage in pairs:
        if not src.exists() or not tgt.exists():
            continue
        if src.stat().st_mtime > tgt.stat().st_mtime + 2.0:
            stale.append(f"{stage}（{src.name} 新于 {tgt.name}）")
    return stale


def build_gml(sample: Optional[int] = None) -> None:
    _EXCLUDED_CONTACTS.clear()
    units = assemble_units()
    n_rel = assemble_unit_relations(units)
    print(f"unit relations assembled: {n_rel}")
    features_out = []

    # 57 unit concept objects
    for norm in sorted(units):
        features_out.append(features.emit_geologic_unit(units[norm]))

    # 713 polygon MappedFeatures
    for mf in assemble_polygon_mfs(units, sample):
        features_out.append(features.emit_mapped_feature(mf))

    # 1317 contacts + their mapped features
    for c in assemble_contacts(sample):
        features_out.append(features.emit_contact(c))
        mf = MappedFeatureRec(
            feature_id=c.gml_id,
            specification_uri=c.uri,
            specification_title=c.sem_label,
            geometry=c.geometry,
            observation_term=c.observation_term,
        )
        features_out.append(features.emit_mapped_feature(mf))

    # 310 faults + mapped features（线 MF=迹线 + 点 MF=产状测量位置垂足，09-27 裁定）
    for f in assemble_faults(sample):
        features_out.append(features.emit_sds(f))
        mf = MappedFeatureRec(
            feature_id=f.feature_id,  # 语义 id（mf.F085.1，2026-10-02 裁定）
            specification_uri=f.uri,
            specification_title=f.fault_name or f.fault_id,
            geometry=f.geometry,
            observation_term=f.observation_term,
        )
        features_out.append(features.emit_mapped_feature(mf))
        for plane in f.planes:
            if plane.foot is None:
                continue
            pmf = MappedFeatureRec(
                feature_id=plane.mp_id,
                specification_uri=f.uri,
                specification_title=f.fault_name or f.fault_id,
                geometry=plane.foot,
                observation_term=f.observation_term,
                description=(
                    f"断层产状测量点 {plane.mp_label} 位置（{plane.mode}"
                    + (f"，{plane.a_label}" if plane.a_label else "")
                    + (f"，∠{plane.dip:g}°（{plane.note_label or plane.dip_source}）"
                       if plane.dip is not None and (plane.note_label or plane.dip_source) else "")
                    + "；到所属断层段垂足）"),
            )
            features_out.append(features.emit_mapped_feature(pmf))

    # 305 foliations + mapped features
    for a in assemble_attitudes(units, sample):
        features_out.append(features.emit_foliation(a))
        mf = MappedFeatureRec(
            feature_id=a.gml_id,
            specification_uri=a.uri,
            specification_title=f"{a.sem_type}",
            geometry=a.geometry,
        )
        features_out.append(features.emit_mapped_feature(mf))

    # 4 folds + mapped features
    for f in assemble_folds(sample):
        profile_uri = mapping.fold_profile(f.gzce)
        features_out.append(features.emit_fold(f, profile_uri))
        mf = MappedFeatureRec(
            feature_id=f.gml_id,
            specification_uri=f.uri,
            specification_title=f.name,
            geometry=f.geometry,
        )
        features_out.append(features.emit_mapped_feature(mf))

    root = document.assemble(features_out)
    document.write(root, config.GML_OUT)
    print(f"GML written: {config.GML_OUT} ({len(features_out)} members)")
    if _EXCLUDED_CONTACTS:
        print(f"B1 剔除执行: 制图误差（剔除）界线未发射 {len(_EXCLUDED_CONTACTS)} 条 "
              f"（idx={sorted(_EXCLUDED_CONTACTS)}；仍登记于 gzbd_overrides）")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["gml", "lite", "pending"], default=None)
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--sheet", choices=[s.key for s in list_sheets()],
                        default="kurgan")
    args = parser.parse_args()

    config.init_sheet(args.sheet)  # 图幅参数集切换（一切装载之前）

    _stale = _stale_inputs()
    if _stale:
        print("!! 时效守卫中止：标定件新于 L1，装配将产出与最新判别不一致的 GML。")
        for _s in _stale:
            print("   -", _s)
        print("   请先按管线序重跑 materialize（必要时连同上游标定域）再 build。")
        return 2

    if args.only in (None, "gml"):
        build_gml(args.sample)
    if args.only in (None, "lite"):
        from .lite import geojson as lite_geojson

        lite_geojson.build_all(args.sample)
    if args.only in (None, "pending"):
        from . import pending as pending_mod

        pending_mod.write(config.PENDING_OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
