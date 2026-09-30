"""Build one sheet's GeoSciML outputs (GML + Lite views + pending list).

CLI: g4c build --sheet kurgan [--only gml|lite|pending] [--sample N]
（驱动移植自 build_geosciml.py，2026-09-28 入包）
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List, Optional

from ..sheets import list_sheets
from . import config, mapping, model, sources
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
                feature_id=row["FEATUREID"],
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
        out.append(
            ContactRec(
                src_id=int(row["_src_id"]),
                code=code,
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
        if aux_idx in pair_conflicts:
            pass  # 注释配对争议隔离：回落段 GZECE（在下方实体循环内回填）
        elif aux_idx in pairs and pairs[aux_idx]["dip"] is not None:
            dip, dip_src = pairs[aux_idx]["dip"], "配对注释"
        elif aux_idx in assoc and assoc[aux_idx]["dip"] is not None:
            dip, dip_src = assoc[aux_idx]["dip"], "配对注释"
        # 六类模式标签+movement_sense（辅助点非实体原则：a 折叠为判定值）
        tri = triplets.get(aux_idx)
        if tri:
            mode = f"{tri['form']}·{tri['verdict']}"
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
        planes_by_seg.setdefault(seg, []).append(
            FaultAuxPlane(azimuth=float(az), dip=dip, aux_idx=aux_idx,
                          mode=mode, dip_source=dip_src, movement_sense=msense))

    # 238/239 走滑钩 → slip_sense（同原则：钩不存实体，旋向折叠为 movementSense）
    slip_by_seg: Dict[int, str] = {}
    for _, row in aux_gdf.iterrows():
        if row.get("kind") != "symbol" or row.get("seg_idx") is None:
            continue
        if str(row.get("status") or "normal") not in ("normal", ""):
            continue
        sn = int(row.get("sub_no") or 0)
        if sn == 238:
            slip_by_seg[int(row["seg_idx"])] = "dextral"
        elif sn == 239:
            slip_by_seg[int(row["seg_idx"])] = "sinistral"

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
            note = f"产状点 b{plane.aux_idx}：{plane.mode}；倾向 {plane.azimuth:g}°"
            if dip is not None:
                note += f"∠{dip:g}°（{src}）"
            else:
                note += "（仅倾向）"
            if plane.aux_idx in pair_conflicts:
                cands = "、".join(f"{n}={d:g}°" for n, d in pair_conflicts[plane.aux_idx])
                note += f"；注释配对二义（候选 {cands}）交人工裁定（P-PAIR-b{plane.aux_idx}）"
            notes.append(note)
            filled.append(FaultAuxPlane(azimuth=plane.azimuth, dip=dip,
                                        aux_idx=plane.aux_idx, mode=plane.mode,
                                        dip_source=src,
                                        movement_sense=plane.movement_sense,
                                        foot=foot))
        # 编图矛盾横幅（登记册驱动，不改码）
        if row["fault_id"] in conflict_entities:
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
                if "第四系界线重合" in _tok or "活动性佐证" in _tok:
                    notes.append(_tok)
        out.append(
            FaultRec(
                feature_id=row["FEATUREID"],
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
                geometry=row.geometry.__geo_interface__,
            )
        )
    return out


def assemble_specimens(units: Dict[str, model.UnitRec],
                       sample: Optional[int] = None) -> List[model.SpecimenRec]:
    """化石/泥火山产地标本（2026-09-28 转入，lite 第六视图 GeologicSpecimenView）。"""
    raw2norm = unit_mod.raw_to_norm_map()
    out: List[model.SpecimenRec] = []
    for theme in ("fossil", "mudvolcano"):
        if not (config.GEOJSON_L1 / f"{theme}.geojson").exists():
            continue
        gdf = sources.read_theme(theme)
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
                    kind={"fossil": "化石", "mudvolcano": "泥火山"}[theme],
                    sem_type=_clean_optional_str(row.get("sem_type")) or "未知",
                    sub_no=str(row.get("symbol_no") or ""),
                    height=str(row.get("height") or "2.0"),
                    angle=str(row.get("angle") or "0.0"),
                    verdict=v or "",
                    host_norm=host_norm,
                    host_name=(units[host_norm].name
                               if host_norm in units else None),
                    note=note,
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
                feature_id=row["FEATUREID"],
                name=row["GZCAB"],
                gzce=row["GZCE"],
                profile_term=mapping.load()["gzce_foldprofile"][row["GZCE"]]["term"],
                geometry=row.geometry.__geo_interface__,
            )
        )
    return out


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
            feature_id=f.gml_id,
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
                feature_id=f"fp.{plane.aux_idx}",
                specification_uri=f.uri,
                specification_title=f.fault_name or f.fault_id,
                geometry=plane.foot,
                observation_term=f.observation_term,
                description=(f"断层产状测量点 b{plane.aux_idx} 位置"
                             f"（{plane.mode}；到所属断层段垂足）"),
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
