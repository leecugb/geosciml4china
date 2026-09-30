"""GeoJSON FeatureCollection writers for the four Lite views.

Axis order: lon,lat is passed through unchanged (RFC7946); the GML flip
lives in emit/xmlcore.py and is NOT shared here by design.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import config
from . import views


def _feature(fid: str, properties: Dict[str, Any]) -> Dict[str, Any]:
    geometry = properties.pop("shape")
    return {"type": "Feature", "id": fid, "geometry": geometry, "properties": properties}


def _write_collection(name: str, features: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"type": "FeatureCollection", "name": name, "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print(f"  {path.name}: {len(features)} features")


def build_all(sample: Optional[int] = None) -> None:
    from ..build import (
        assemble_attitudes,
        assemble_contacts,
        assemble_faults,
        assemble_folds,
        assemble_polygon_mfs,
        assemble_specimens,
        assemble_units,
    )

    units = assemble_units()

    unit_features: List[Dict[str, Any]] = []
    from urllib.parse import unquote

    for mf in assemble_polygon_mfs(units, sample):
        norm = unquote(mf.specification_uri.rsplit("/", 1)[-1])
        unit = units[norm]
        unit_features.append(_feature(mf.uri, views.geologic_unit_view(mf, unit)))
    _write_collection("GeologicUnitView", unit_features, config.LITE_OUT / "geologic_unit_view.geojson")  # noqa: E501

    contact_features = [
        _feature(c.uri, views.contact_view(c)) for c in assemble_contacts(sample)
    ]
    _write_collection("ContactView", contact_features, config.LITE_OUT / "contact_view.geojson")

    sds_features = [_feature(f.uri, views.sds_view(f)) for f in assemble_faults(sample)]
    _write_collection(
        "ShearDisplacementStructureView",
        sds_features,
        config.LITE_OUT / "shear_displacement_structure_view.geojson",
    )

    # 断层产状测量点（09-27 用户裁定：点位=b 到所属段的垂足）
    fmp_features = []
    for f in assemble_faults(sample):
        for plane in f.planes:
            if plane.foot is None:
                continue
            fmp_features.append(
                _feature(
                    f"{config.BASE_URI}mappedfeature/fp.{plane.aux_idx}",
                    views.fault_measure_point_view(plane, f.uri,
                                                   f.fault_name or f.fault_id),
                )
            )
    _write_collection(
        "FaultAttitudePointView",
        fmp_features,
        config.LITE_OUT / "fault_attitude_point_view.geojson",
    )

    so_features = []
    for a in assemble_attitudes(units, sample):
        host_name = units[a.host_norm].name if a.host_norm in units else None
        host_uri = units[a.host_norm].uri if a.host_norm in units else None
        so_features.append(
            _feature(
                a.uri, views.site_observation_view(a, host_name, host_uri)
            )
        )
    _write_collection(
        "SiteObservationView",
        so_features,
        config.LITE_OUT / "site_observation_view.geojson",
    )

    # 化石/泥火山标本（2026-09-28 转入，lite 第六视图 GeologicSpecimenView）
    sp_features = [
        _feature(s.uri, views.fossil_specimen_view(s))
        for s in assemble_specimens(units, sample)
    ]
    _write_collection(
        "GeologicSpecimenView",
        sp_features,
        config.LITE_OUT / "fossil_specimen_view.geojson",
    )

    # 褶皱轴线（2026-09-28 接入，lite 第七视图 FoldView——
    # 参照 pymapgis render_fold_layer：GZCE 分型 + 纺锤透镜）
    fold_features = [
        _feature(f.uri, views.fold_view(f)) for f in assemble_folds(sample)
    ]
    _write_collection(
        "FoldView",
        fold_features,
        config.LITE_OUT / "fold_view.geojson",
    )

    # 水系双视图（2026-09-29 十一文件契约补全：水系属图面组成层，
    # 非 GeoSciML 地质要素——渲染支撑视图，L1 直通不改几何/轴序；
    # 本幅无对应主题→空集合照常写出，渲染侧零要素跳过）
    from .. import sources as _src
    for theme, vname, fname in (
            ("waterline", "WaterlineView", "waterline_view.geojson"),
            ("waterpoly", "WaterpolyView", "waterpoly_view.geojson")):
        feats = []
        try:
            g = _src.read_theme(theme)
        except FileNotFoundError:
            g = None
        if g is not None:
            for _, r in g.iterrows():
                fid = f"{config.BASE_URI}{theme}/{r['_src_file']}.{int(r['_src_id'])}"
                feats.append(_feature(fid, {
                    "@featureType": vname,
                    "identifier": {"value": fid, "@codeSpace": config.CODE_SPACE},
                    "GB": str(r.get("GB") or ""),
                    "name": str(r.get("NAME") or ""),
                    "HYDC": str(r.get("HYDC") or ""),
                    "shape": r.geometry.__geo_interface__,
                }))
        _write_collection(vname, feats, config.LITE_OUT / fname)
