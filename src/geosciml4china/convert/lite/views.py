"""GeoSciML Lite view builders (flat properties per view type)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import config, model, vocab

NIL = config.NIL_URI


def _rgb_hex(rgb: Optional[List[int]]) -> Optional[str]:
    if not rgb:
        return None
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def geologic_unit_view(mf: model.MappedFeatureRec, unit: model.UnitRec) -> Dict[str, Any]:
    """GeologicUnitView properties (713 polygon MappedFeatures)."""
    props: Dict[str, Any] = {
        "@featureType": "GeologicUnitView",
        "identifier": {"value": mf.uri, "@codeSpace": config.CODE_SPACE},
        "name": unit.name,
        "description": f"{unit.norm} · {unit.layer_role}",
        "geologicUnitType": unit.unittype_term.replace("_", " "),
        "geologicUnitType_uri": vocab.cgi_term("geologicunittype", unit.unittype_term)[0],
        "rank": unit.rank_term,
        # 2026-09-28（F1 解耦）：stylegen 语义源字段——GeoSciML 侧自足携带
        # norm/角色/原码/源图层，样式生成不再回读 MapGIS（原则：与转换解耦）
        "unit_norm": unit.norm,
        "layer_role": unit.layer_role,
        "map_code": mf.map_code,
        "src_file": mf.src_file,
    }
    if unit.compositions:
        comp = unit.compositions[0]
        props["lithology"] = comp.lithology_label
        props["representativeLithology_uri"] = comp.lithology_uri
    else:
        props["representativeLithology_uri"] = NIL
    ev = unit.event
    if ev and ev.older_era:
        era_o = vocab.era(ev.older_era) or {}
        era_y = vocab.era(ev.younger_era) or {}
        zh_o, zh_y = era_o.get("label_zh", ev.older_era), era_y.get("label_zh", ev.younger_era)
        props["geologicHistory"] = zh_o if zh_o == zh_y else f"{zh_o}–{zh_y}"
        props["representativeAge_uri"] = vocab.era_uri(ev.older_era)
        props["representativeOlderAge_uri"] = vocab.era_uri(ev.older_era)
        props["representativeYoungerAge_uri"] = vocab.era_uri(ev.younger_era)
        props["numericOlderAge"] = era_o.get("older_Ma")
        props["numericYoungerAge"] = era_y.get("younger_Ma")
    else:
        props["representativeAge_uri"] = NIL
        props["representativeOlderAge_uri"] = NIL
        props["representativeYoungerAge_uri"] = NIL
    props["source"] = f"1:250000 {config.SHEET_TITLE}"
    props["specification_uri"] = unit.uri
    props["genericSymbolizer"] = _rgb_hex(unit.rgb)
    props["shape"] = mf.geometry
    return props


def contact_view(c: model.ContactRec) -> Dict[str, Any]:
    """ContactView properties (1317 contacts)."""
    if c.decided and c.contacttype_term:
        ct_uri, ct_label = vocab.cgi_term("contacttype", c.contacttype_term)
    else:
        ct_uri, ct_label = NIL, "unknown"
    desc = (c.verdict or "") + (f"；年轻侧 {c.younger_side}" if c.younger_side else "")
    props = {
        "@featureType": "ContactView",
        "identifier": {"value": c.uri, "@codeSpace": config.CODE_SPACE},
        "name": c.sem_label or c.code,
        "description": desc or "地质界线",
        "contactType": ct_label,
        "contactType_uri": ct_uri,
        "observationMethod": (c.observation_term or "outcrop_observation").replace("_", " "),
        "specification_uri": c.uri,
        "genericSymbolizer": c.code,
        "shape": c.geometry,
    }
    # 结构化年轻侧（2026-10-02 渲染优化）：04/24 不整合双线须用标定侧
    # （渲染层不再现场探针）；仅 truthy 发射——null 行属性缺席→探针回落
    if c.younger_side:
        props["younger_side"] = c.younger_side
    return props


def sds_view(f: model.FaultRec) -> Dict[str, Any]:
    """ShearDisplacementStructureView properties (310 faults)."""
    if f.faulttype_term:
        ft_uri, ft_label = vocab.cgi_term("faulttype", f.faulttype_term)
    else:
        ft_uri, ft_label = NIL, "unknown"
    desc = f.gzehg or ""
    if f.description_append:
        desc = (desc + "；" if desc else "") + f.description_append
    if f.attitude_note:
        desc = (desc + "；" if desc else "") + f.attitude_note
    if f.slip_sense:
        desc = (desc + "；" if desc else "") +             f"走滑旋向 {f.slip_sense}{f.slip_span}"
    return {
        "@featureType": "ShearDisplacementStructureView",
        "identifier": {"value": f.uri, "@codeSpace": config.CODE_SPACE},
        # B2 联动（2026-09-28）：name 只载真名——无名断层保持空串（渲染注记
        # 与 L1 侧同口径只标真名；fault_id 回退仅用于 GML 名称槽，不渲染）
        "name": f.fault_name or "",
        "description": desc or "断层",
        "faultType": ft_label,
        "faultType_uri": ft_uri,
        "observationMethod": (f.observation_term or "").replace("_", " "),
        "specification_uri": f.uri,
        "genericSymbolizer": f.gzeeb_eff,
        "shape": f.geometry,
    }


def site_observation_view(
    a: model.AttitudeRec, host_name: Optional[str], host_uri: Optional[str]
) -> Dict[str, Any]:
    """SiteObservationView properties (305 attitudes)."""
    if a.foliation_term:
        f_uri, f_label = vocab.foliation_uri(a.foliation_term)
    else:
        f_uri, f_label = NIL, "unknown"
    props: Dict[str, Any] = {
        "@featureType": "SiteObservationView",
        "identifier": {"value": a.uri, "@codeSpace": config.CODE_SPACE},
        "observationName": f_label,
        "label": (f"{a.azimuth:g}°∠{a.dip:g}°" if a.dip is not None
                  else f"{a.azimuth:g}°"),  # 空倾角缺省（如实）
        "observedProperty": "planar orientation",
        "observedValue": (f"{a.dip:g}" if a.dip is not None else ""),
        "observedValueUom": "deg",
        "propertyType_uri": f_uri,
        "symbolRotation": int(round((a.azimuth - 90.0) % 360.0)),
        "genericSymbolizer": a.gzbbga,
        # 2026-09-28：sem_type 有效类型下送（Pt1→片麻理产状等宿主裁定规则
        # 在渲染层生效；原码 GZBBGA 不改写，仅作 genericSymbolizer 键）
        "sem_type": a.sem_type,
        "shape": a.geometry,
    }
    if host_name:
        props["featureOfInterest"] = host_name
        props["featureOfInterest_uri"] = host_uri or NIL
    return props


def fault_measure_point_view(
    plane: model.FaultAuxPlane, sds_uri: str, sds_name: str
) -> Dict[str, Any]:
    """FaultAttitudePointView properties（断层产状测量点，09-27 用户裁定：
    点位=b 到所属段的垂足；b 原始点位不入产品）。

    symbolRotation=dip_az（b 的倾向方位，倾向箭头符号语义）。"""
    az = plane.azimuth
    dip_txt = f"{plane.dip:g}" if plane.dip is not None else ""
    props: Dict[str, Any] = {
        "@featureType": "FaultAttitudePointView",
        "identifier": {"value": f"{config.BASE_URI}mappedfeature/fp.{plane.aux_idx}",
                       "@codeSpace": config.CODE_SPACE},
        "observationName": "fault attitude measurement point",
        "label": f"{az:g}°" + (f"∠{plane.dip:g}°" if plane.dip is not None else "（仅倾向）"),
        "description": plane.mode,
        "observedProperty": "planar orientation",
        "observedValue": dip_txt if dip_txt else "unknown",
        "observedValueUom": "deg",
        "propertyType_uri": "http://resource.geosciml.org/classifier/cgi/planarorientationtype/planar_orientation",
        "symbolRotation": int(round(az)) % 360,
        "genericSymbolizer": "fault_attitude_point",
        "featureOfInterest": sds_name,
        "featureOfInterest_uri": sds_uri,
        "shape": plane.foot,
    }
    return props


def fossil_specimen_view(s) -> Dict[str, Any]:
    """GeologicSpecimenView properties（化石/泥火山产地，2026-09-28 转入）。

    槽位与 geosciml-lite.xsd GeologicSpecimenViewType 对齐：
    identifier/label/description/specimenType/materialClass/source/
    specimenType_uri/materialClass_uri/genericSymbolizer/shape。"""
    host_txt = s.host_name or s.host_norm or "未查明宿主"
    desc = f"{s.sem_type}（{s.kind}产地；宿主 {host_txt}；标定 verdict={s.verdict or '未评'}）"
    if s.note:
        desc += f"；{s.note}"
    return {
        "@featureType": "GeologicSpecimenView",
        "identifier": {"value": s.uri, "@codeSpace": config.CODE_SPACE},
        "label": s.sem_type,
        "description": desc,
        "specimenType": (f"{model.SPECIMEN_KINDS['fossil']}产地"
                         if s.kind == model.SPECIMEN_KINDS["fossil"]
                         else model.SPECIMEN_KINDS["mudvolcano"]),
        "source": "LDZOFBB099.WT（1:25万建造构造图）",
        "specimenType_uri": NIL,
        "materialClass_uri": NIL,
        "genericSymbolizer": str(s.sub_no),
        "symbol_no": int(s.sub_no or 0),   # render_fossil_layer 契约
        "height": float(s.height or 2.0),
        "angle": float(s.angle or 0.0),
        "shape": s.geometry,
    }


def fold_view(f: "model.FoldRec") -> Dict[str, Any]:
    """FoldView properties（褶皱轴线，2026-09-28 接入——参照 pymapgis
    render_fold_layer 契约：GZCE 分型 02/04 背斜实线透镜、03 复向斜断线）。"""
    return {
        "@featureType": "FoldView",
        "identifier": {"value": f.uri, "@codeSpace": config.CODE_SPACE},
        "label": f.name or f.feature_id,
        "observationName": "fold axis",
        "genericSymbolizer": f.gzce,
        "GZCE": f.gzce,
        "shape": f.geometry,
    }
