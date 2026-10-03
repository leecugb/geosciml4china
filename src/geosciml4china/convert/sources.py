"""Read L1 geojson themes and CSV side tables with a central dtype-coercion layer."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional

import geopandas as gpd
import pandas as pd

from . import config


def _float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    f = _float(value)
    return int(f) if f is not None else None


def _bool_str(value: Any) -> Optional[bool]:
    if value in ("True", "true", True, 1):
        return True
    if value in ("False", "false", False, 0):
        return False
    return None


def _strip_tilde(value: Any) -> Optional[float]:
    """'~2200' -> 2200.0"""
    if value is None:
        return None
    text = str(value).strip().lstrip("~").strip()
    return _float(text)


def read_theme(name: str) -> gpd.GeoDataFrame:
    path = config.GEOJSON_L1 / f"{name}.geojson"
    if not path.exists():
        raise FileNotFoundError(path)
    return gpd.read_file(path)


def read_age_table() -> Dict[str, dict]:
    """stratigraphic_geologic_age_table.csv -> {unit: {older_Ma, younger_Ma}}"""
    out: Dict[str, dict] = {}
    if config.AGE_TABLE_CSV is None or not config.AGE_TABLE_CSV.exists():
        return out
    with open(config.AGE_TABLE_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            unit = (row.get("代号") or "").strip()
            if not unit:
                continue
            out[unit] = {
                "older_Ma": _strip_tilde(row.get("Ma下限(老)")),
                "younger_Ma": _strip_tilde(row.get("Ma上限(新)")),
            }
    return out


def read_aux_pairs() -> tuple[Dict[int, dict], Dict[int, list]]:
    """fault_aux_number_1894_pairs.csv -> (pairs, conflicts)

    pairs:     {idx1894: {dip, num_idx}} —— 唯一配对的 b（1:1 合规）。
    conflicts: {idx1894: [(num_idx, dip), ...]} —— 共享 b（1:1 冲突），
               **隔离待裁定**：不入 pairs，倾角通道回落 GZECE（独立于注释
               争议的段编码字段），provenance 标注"配对待裁定"。
               对应 pending_review P-PAIR-* 与 semantics JSON『共享b待裁定』。

    Keys are the 1894-arrow's aux index (matches L1 fault_aux._src_id).
    Load-time guard: a present-but-empty table is a wiring error, not
    "no pairs" — die loudly (same lesson as the priors load-time check).
    """
    out: Dict[int, dict] = {}
    raw: Dict[int, list] = {}
    if not config.AUX_PAIRS_CSV.exists():
        return out, {}
    with open(config.AUX_PAIRS_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            b_idx = _int(row.get("idx1894"))
            if b_idx is None:
                continue
            raw.setdefault(b_idx, []).append(
                {"dip": _float(row.get("dip")), "note_idx": _int(row.get("num_idx"))})
    assert raw, f"pairs table loaded empty from {config.AUX_PAIRS_CSV} (key wiring drift?)"
    conflicts: Dict[int, list] = {}
    for b_idx, rows in raw.items():
        if len(rows) > 1:
            conflicts[b_idx] = [(r["note_idx"], r["dip"]) for r in rows]
        else:
            out[b_idx] = rows[0]
    return out, conflicts


def read_aux_triplets() -> Dict[int, dict]:
    """三联体表 -> {b_idx: {form, verdict, fault_id}}

    六类模式标签数据源（2026-09-26 用户定版）。库尔干表无 form 列、b 键
    a1894；英吉沙表带 form/aux_conf 列、b 键 b1851——列名自动探测。
    装载期断言：表在而空=接线漂移立即炸（同 pairs 教训）。
    """
    out: Dict[int, dict] = {}
    if not config.AUX_TRIPLETS_CSV.exists():
        return out
    with open(config.AUX_TRIPLETS_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        bcol = "a1894" if "a1894" in (reader.fieldnames or []) else "b1851"
        for row in reader:
            b_idx = _int(row.get(bcol))
            if b_idx is None:
                continue
            form = row.get("form") or (
                "a-b-a" if "/" in str(row.get("a1281", "")) else "a-b")
            # 归并规则（2026-09-26 用户定）：同 b 多组取最强形式 a-b-a>a-b
            # （唯一实例英吉沙 b211/F014）——行序后写不得降级既有 a-b-a
            if b_idx in out and out[b_idx]["form"] == "a-b-a" and form == "a-b":
                continue
            out[b_idx] = {"form": form, "verdict": (row.get("verdict") or "").strip(),
                          "fault_id": (row.get("fault_id") or "").strip(),
                          "a1281": (row.get("a1281") or "").strip()}
    assert out, f"triplets table loaded empty from {config.AUX_TRIPLETS_CSV}"
    return out


def read_fault_conflict_entities() -> set:
    """编图矛盾登记（段级，2026-10-02 泛化修复——jws 全管线测试暴露）：
    冲突册 _gzeeb_conflicts_<key>.csv pending 行 -> {(fault_id, seg_idx)}。
    横幅按冲突段精确挂载（原实体级广播在 F001 型大实体上过度横幅——
    24 vs 7 实证）；fault_aux_code_semantics.json 作裁定文档层。
    2026-10-02 活动断层审计 A7 双册消费已撤销（同日全管线测试裁定）：
    线层通道候选（_fault_contact_activity_conflicts_）系被面元拓扑通道
    取代的旧判据诊断件——只保留为审查档案，不再横幅产品。
    """
    out = set()
    for cand in (getattr(config, "CONFLICTS_CSV", None),):
        if cand is None or not cand.exists():
            continue
        try:
            df = pd.read_csv(cand, dtype=str)
        except Exception:
            continue
        for _, r in df.iterrows():
            if str(r.get("status") or "") != "pending_review":
                continue
            fid = str(r.get("fault_id") or "").strip()
            # 2026-10-02 活动断层审计：空 fault_id 经 pandas 读回 NaN →
            # str() 成 "nan"（真值非空）会以 ("nan", seg) 入横幅集合——
            # 显式过滤
            if fid in ("", "nan", "None"):
                continue
            import re as _re
            _segs_raw = str(r.get("segs") or "")
            _segs_raw = _re.sub(r"[\[\]]", "", _segs_raw)
            for sg in _segs_raw.split(","):
                sg = sg.strip()
                if sg and fid:
                    try:
                        out.add((fid, int(float(sg))))
                    except ValueError:
                        continue
    return out


def read_calibration_report() -> list:
    """config.CALIBRATION_CSV -> [{idx, gzbd, left, right, young_side,
    verdict, rule_conf}]（单元对接地关系 v2.1 数据源；原始名列交由
    build 侧经 units.raw_to_norm_map 归一）。图幅参数化于 config.init_sheet。"""
    out = []
    path = config.CALIBRATION_CSV
    if path is None or not Path(path).exists():
        return out
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out.append({
                "idx": _int(row.get("idx")),
                "gzbd": (row.get("gzbd") or "").strip(),
                "left": (row.get("left") or "").strip(),
                "right": (row.get("right") or "").strip(),
                "young_side": (row.get("young_side") or "").strip().lower(),
                "verdict": (row.get("verdict") or "").strip(),
                "rule_conf": (row.get("rule_conf") or "").strip(),
            })
    assert out, f"calibration report loaded empty from {config.CALIBRATION_CSV}"
    return out


def read_aux_assoc() -> Dict[int, dict]:
    """fault_aux_point_association.csv -> {aux_idx: row dict (typed)}"""
    out: Dict[int, dict] = {}
    if not config.AUX_ASSOC_CSV.exists():
        return out
    with open(config.AUX_ASSOC_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            idx = _int(row.get("aux_idx"))
            if idx is None:
                continue
            out[idx] = {
                "kind": row.get("kind"),
                "sub_no": _int(row.get("sub_no")),
                "dip": _float(row.get("dip")),
                "seg_idx": _int(row.get("seg_idx")),
                "dip_az": _float(row.get("dip_az")),
                "confidence": row.get("confidence"),
            }
    return out


def read_color_units() -> Dict[str, dict]:
    """Color mapping units keyed by raw mathtext code:
    {raw_code: {norm, name, rgb, layer_role, layer_file}}"""
    with open(config.UNIT_COLOR_MAPPING, encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[str, dict] = {}
    for layer_file, info in data["polygon_layers"].items():
        role = info.get("role", "")
        for raw, unit in info.get("units", {}).items():
            out[raw] = {
                "norm": unit.get("norm"),
                "name": unit.get("name"),
                "rgb": unit.get("rgb"),
                "layer_role": role,
                "layer_file": layer_file,
            }
    return out


def read_unit_to_ics() -> Dict[str, dict]:
    if config.UNIT_TO_ICS is None or not Path(config.UNIT_TO_ICS).exists():
        return {}
    with open(config.UNIT_TO_ICS, encoding="utf-8") as f:
        rows = json.load(f)
    return {r["unit"]: r for r in rows}
