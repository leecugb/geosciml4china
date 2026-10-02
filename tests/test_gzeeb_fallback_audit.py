# -*- coding: utf-8 -*-
"""一般断层兜底执行审计（2026-10-02 用户指令「审计 geosciml4china 执行上述
逻辑」——兜底裁定：gzeeb 码无法标定（名不蕴含语义+无辅助点语义）→统一
一般断层，管线运转，详情档案）。

方法=独立重算：签名集（全段无倾角+真覆盖段≥2）/逐行投票模型（码先验/名/
签名/运动学/dip/aux/覆盖）/兜底判定自实现，与生产 verdict 与档案逐行对照。
"""
import math
import re

import geopandas as gpd
import pandas as pd
import pytest
from shapely.ops import unary_union

from pymapgis.rendering.pdf_writer import _unit_age_rank

SHEETS = [
    ("kurgan", r"D:\JWD", 39.5),
    ("yingjisha", r"D:\J43C002003新疆英吉沙县\J43C002003\MAPGIS\JWD", 38.5),
    ("aoyiyayilake", r"D:\J45C004001新疆奥依亚依拉克\J45C004001\MAPGIS\JWD", 36.5),
    ("bashkurgan", r"D:\ts\JWD", 39.5),
]

_NAME_KW = [("逆冲推覆", "推覆体边界"), ("逆冲", "逆断层"), ("逆掩", "逆断层"),
            ("逆断层", "逆断层"), ("正断层", "正断层"), ("左型走滑", "左型走滑断层"),
            ("右型走滑", "右型走滑断层"), ("左行", "左型走滑断层"),
            ("右行", "右型走滑断层"), ("走滑", "走滑断层"), ("平移", "走滑断层"),
            ("复活", "复活断层"), ("活动", "活动断层")]


def _nsem(x):
    return re.sub(r"[（(].*?[)）]", "", str(x)).strip()


def _name_sem(nm):
    for kw, sem in _NAME_KW:
        if kw in str(nm or ""):
            return sem
    return ""


def _load_reg(root, key):
    import json
    from pathlib import Path
    for cand in (Path(root) / f"fault_semantics_{key}.json",
                 Path(root) / "data" / "gzeeb_codes.json"):
        if cand.exists():
            j = json.load(open(cand, encoding="utf-8"))
            return (dict(j.get("gzeeb_semantics") or j.get("codes") or {}),
                    dict(j.get("gzeld_semantics", {})))
    j = json.load(open(r"D:\geosciml4china\src\geosciml4china\data"
                       r"\gzeeb_codes.json", encoding="utf-8"))
    return (dict(j.get("gzeeb_semantics") or j.get("codes") or {}),
            dict(j.get("gzeld_semantics", {})))


def _independent_fallback(key, root, lat):
    """独立重算：返回 {idx: True/False}（兜底判定）+ 签名集。"""
    from pymapgis.semantics.profile import get_profile
    from pathlib import Path
    prof = get_profile(key)
    lon_m = 111320.0 * math.cos(math.radians(lat))
    fl = gpd.read_file(root + r"\geojson\L1\faults.geojson") \
        .sort_values("_src_id").reset_index(drop=True)
    ent = pd.read_csv(root + (r"\fault_entities.csv" if key == "kurgan"
                              else rf"\fault_entities_{key}.csv"), dtype=str)
    ent_first = ent.groupby("fault_id").first()
    gsem, gzeld_sem = _load_reg(root, key)
    # 覆盖联合（priors 参数化）
    from geosciml4china.calibrate.priors import load_priors
    _pri = load_priors(key) or {}
    _q_excl = set(_pri.get("quaternary_exclude", ["Qp1X"]))
    _rank_min = float(_pri.get("quaternary_rank_min", 1300.0))
    ice = gpd.read_file(root + r"\geojson\L0\LDLYAAE002.WP.geojson") \
        if Path(root + r"\geojson\L0\LDLYAAE002.WP.geojson").exists() \
        else gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
    wl = gpd.read_file(root + r"\geojson\L0\LDLYAAE001.WL.geojson") \
        if Path(root + r"\geojson\L0\LDLYAAE001.WL.geojson").exists() \
        else gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
    poly = gpd.read_file(root + r"\geojson\L0\LDZOFBB001.WP.geojson") \
        if Path(root + r"\geojson\L0\LDZOFBB001.WP.geojson").exists() \
        else gpd.GeoDataFrame({"geometry": [], "QDUECC": []}, crs="EPSG:4326")
    ice_u = ice.geometry.union_all() if len(ice) else None
    wat_u = wl.geometry.union_all().buffer(100.0 / lon_m) if len(wl) else None
    qg = [g for g, c in zip(poly.geometry.values, poly["QDUECC"].astype(str).values)
          if g is not None and not g.is_empty
          and (_unit_age_rank(c) or 0) >= _rank_min
          and not any(x in c for x in _q_excl)]
    quat_u = unary_union(qg) if qg else None
    cover_u = unary_union([u for u in (ice_u, wat_u, quat_u) if u is not None]) \
        if any(u is not None for u in (ice_u, wat_u, quat_u)) else None
    # 签名集（码级：全段无倾角+真覆盖≥2；仅未注册码）
    code_dip, code_buried = set(), {}
    for _, row in fl.iterrows():
        gz = str(row.get("GZEEB") or "")
        if not gz or gz in gsem:
            continue
        code_buried.setdefault(gz, 0)
        try:
            d0 = float(row.get("GZECE") or 0)
        except (TypeError, ValueError):
            d0 = 0.0
        if d0 > 0:
            code_dip.add(gz)
        g0 = row.geometry
        if cover_u is not None and g0 is not None and not g0.is_empty:
            fc = g0.intersection(cover_u).length / g0.length if g0.length else 0.0
            if fc >= 0.5:
                code_buried[gz] += 1
    sig = {c for c, n in code_buried.items() if c not in code_dip and n >= 2}
    # 覆盖库裁定（adjudicated）
    import json
    ov = {}
    for cand in (Path(root) / f"fault_type_overrides_{key}.json",
                 Path(root) / "fault_type_overrides.json",
                 Path(root) / "data" / "fault_type_overrides.json"):
        if cand.exists():
            ov = json.load(open(cand, encoding="utf-8")).get("overrides", {})
            break
    out = {}
    for idx, row in fl.iterrows():
        g = row.geometry
        if g is None or g.is_empty:
            continue
        gz = str(row.get("GZEEB") or "")
        ov_e = ov.get(str(idx))
        eff = gz
        adjudicated = False
        if ov_e and ov_e.get("status") == "adjudicated" \
                and str(ov_e.get("original")) == gz:
            eff = str(ov_e.get("effective", gz))
            adjudicated = True
        sem_entry = gsem.get(eff, {})
        sem_name = _nsem(sem_entry.get("semantic", sem_entry.get("meaning", ""))
                         if isinstance(sem_entry, dict) else "")
        if not sem_name and adjudicated and ov_e.get("effective_semantic"):
            sem_name = _nsem(ov_e["effective_semantic"])
        ns_hit = False
        if not sem_name:
            ns = _name_sem(ent_first.get(f"fault_id") is None and "" or
                           ent_first.loc[row.get("fault_id"), "name"]
                           if row.get("fault_id") in ent_first.index else "")
            if ns:
                sem_name = ns
                ns_hit = True
        sig_hit = False
        if not sem_name and eff in sig:
            sem_name = "推测断层"
            sig_hit = True
        # 投票
        votes = {}
        if sem_name and (bool(sem_entry) or (adjudicated
                                             and ov_e.get("effective_semantic"))):
            votes[sem_name] = votes.get(sem_name, 0) + 3
        if ns_hit:
            votes[sem_name] = votes.get(sem_name, 0) + 2
        if sig_hit:
            votes["推测断层"] = votes.get("推测断层", 0) + 2
        gzeld_sem_now = gzeld_sem.get(str(row.get("GZELD") or ""),
                                      str(row.get("GZELD") or ""))
        if str(gzeld_sem_now).startswith("压性"):
            votes["逆断层"] = votes.get("逆断层", 0) + 2
            votes["推覆体边界"] = votes.get("推覆体边界", 0) + 2
        elif str(gzeld_sem_now).startswith("张性"):
            votes["正断层"] = votes.get("正断层", 0) + 2
        elif str(gzeld_sem_now).startswith("左行"):
            votes["左型走滑断层"] = votes.get("左型走滑断层", 0) + 2
        elif str(gzeld_sem_now).startswith("右行"):
            votes["右型走滑断层"] = votes.get("右型走滑断层", 0) + 2
        try:
            dip = float(row.get("GZECE") or 0)
        except (TypeError, ValueError):
            dip = 0.0
        if dip > 0:
            if 25 <= dip <= 85:
                votes["逆断层"] = votes.get("逆断层", 0) + 1
            if 50 <= dip <= 90:
                votes["正断层"] = votes.get("正断层", 0) + 1
            if 0 <= dip <= 35:
                votes["推覆体边界"] = votes.get("推覆体边界", 0) + 1
        fc = (g.intersection(cover_u).length / g.length
              if cover_u is not None and g.length else 0.0)
        if fc >= 0.5:
            votes["推测断层"] = votes.get("推测断层", 0) + 2
        elif cover_u is not None:
            try:
                de = g.distance(cover_u.boundary) * lon_m
            except Exception:
                de = None
            if de is not None and de <= 1000.0:
                votes["推测断层"] = votes.get("推测断层", 0) + 2
        mle = "断层泛称"
        if votes:
            mx = max(votes.values())
            if mx >= 2:
                win = [k for k, v in votes.items() if v == mx]
                if len(win) == 1:
                    mle = win[0]
                elif sem_name in win and (bool(sem_entry) or (adjudicated
                                                              and ov_e.get(
                            "effective_semantic"))):
                    mle = sem_name
                elif "推测断层" in win:
                    mle = [k for k in win if k != "推测断层"][0]
        if adjudicated and ov_e.get("structural_type"):
            mle = str(ov_e.get("structural_type"))
        fallback = (not sem_entry and not ns_hit and not sig_hit
                    and not adjudicated and mle == "断层泛称")
        out[int(idx)] = fallback
    return out, sig


@pytest.mark.parametrize("key,root,lat", SHEETS)
def test_fallback_execution(key, root, lat):
    gz = pd.read_csv(root + rf"\_gzeeb_calibration_{key}.csv", dtype=str)
    ind, sig = _independent_fallback(key, root, lat)
    prod = {int(r["idx"]): r for _, r in gz.iterrows()}
    prod_fb = {i for i, r in prod.items()
               if str(r["verdict"]) == "兜底（一般断层）"}
    ind_fb = {i for i, v in ind.items() if v}
    assert prod_fb == ind_fb, \
        f"兜底判定不符 {key}: 生产多 {sorted(prod_fb - ind_fb)} 独立多 {sorted(ind_fb - prod_fb)}"
    # 兜底行不变量
    for i in prod_fb:
        r = prod[i]
        assert r["structural_type"] == "断层泛称"
        assert "一般断层兜底" in str(r["checks"])
        assert "unassessed" in str(r.get("conf_band_u") or "") or \
            "unassessed" in str(r.get("conf_breakdown_u") or "")
    # 反向：非兜底行不得携带兜底注记
    for i, r in prod.items():
        if i not in prod_fb:
            assert "一般断层兜底" not in str(r["checks"]), \
                f"seg{i} 非兜底行携带兜底注记"
    # 档案：恰为兜底行且详情列齐全
    from pathlib import Path
    fp = Path(root) / f"_gzeeb_fallback_{key}.csv"
    if prod_fb:
        assert fp.exists(), f"{key} 兜底行无档案"
        fb = pd.read_csv(fp, dtype=str)
        assert {int(x) for x in fb["idx"]} == prod_fb
        for col in ("idx", "fault_id", "GZEEB", "fault_name", "gzeld",
                    "evidence_class", "structural_type", "checks"):
            assert col in fb.columns, f"档案缺列 {col}"
    else:
        assert not fp.exists(), f"{key} 无兜底行却有档案"


@pytest.mark.parametrize("key,root,lat", [s for s in SHEETS if s[0] == "kurgan"])
def test_fallback_kurgan_gate(key, root, lat):
    """库尔干门：全注册码零兜底——正典逐字节（verdict 无兜底值）。"""
    gz = pd.read_csv(root + r"\_gzeeb_calibration_kurgan.csv", dtype=str)
    assert "兜底（一般断层）" not in set(gz["verdict"])
    ind, _ = _independent_fallback(key, root, lat)
    assert not any(ind.values())
