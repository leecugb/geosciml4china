"""GZEEB 断层类别三维标定（geosciml4china.calibrate 第 3 域移植，2026-09-29）。

移植自 _audit_gzeeb.py（525 行，2026-09-25 三维分层模型建成，双幅通用）：
三维正交分层（用户定调「分层并行不冲突」）——
  · 证据级别层：复合覆盖（第四系松散沉积物剔半胶结+冰雪+水体）≥90% 强推测/
    ≥50% 推测；LYGREBA001=解译；
  · 结构类型层：GZELD 运动学（本幅 gzeld 码义注册表——英吉沙 103=左行 vs
    库尔干 103=右行）+ GZECE 倾角域值 + aux 三联体正逆 + 走滑旋向钩 +
    三类补强（推覆：地层重复探针+老盖新探针（倾向盘老于下盘）；复活：aux
    正断层产状点+切割/控制第四系；活动：切割第四系+入冰雪区）；
  · 活动性层：37=活动（与上两层正交）；**活动性强先验**（2026-09-28 用户定）：
    断层与第四系松散沉积物界线重合→活动（复活）倾向，实体多段重合加强，
    强候选登记交人工裁定（不自动改码）。
反演标定环路（2026-09-26 用户定）：aux 产状测量点解析成果反演标定所属断层
编码语义——①aux 正逆×结构期望（编图矛盾实证）②注释值×GZECE 一致性
（|Δ|>2° 登记编图错误候选）③证据层×aux 交叉。
覆盖库 fault_type_overrides[_<sheet>].json：adjudicated 居最高级（expect 防漂移）；
S×I×F 统一置信影子三列；冲突登记册合并（已裁定条目保留在前）。
产物：_gzeeb_calibration_<sheet>.csv（逐段 gzeeb_eff/三维/verdict/置信三列）
     + _gzeeb_conflicts_<sheet>.csv（冲突登记册，永不自动改码）。
库尔干影子逐字节复现为准入闸。

CLI: python -m geosciml4china.calibrate.gzeeb --sheet <key> [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.strtree import STRtree

from pymapgis.semantics.profile import get_profile
from pymapgis.semantics import load_source_layer
from pymapgis.rendering.pdf_writer import _unit_age_rank

from ..data import data_path
from ..sheets import get_sheet
from .priors import load_priors


def norm_sem(s):
    return re.sub(r"[（(].*?[)）]", "", str(s)).strip()

EXPECT = {
    "逆断层": dict(gzeld_kin="压性", dip=(25, 85), aux="逆断层产状点"),
    "正断层": dict(gzeld_kin="张性", dip=(50, 90), aux="正断层产状点"),
    "推覆体边界": dict(gzeld_kin="压性", dip=(0, 35)),
    "右型走滑断层": dict(gzeld_kin="右行"),
    "左型走滑断层": dict(gzeld_kin="左行"),
    "走滑断层": dict(),
    "断层泛称": dict(),
    "断层（泛称）": dict(),
    "推测断层": dict(cover_min=50),
    "活动断层": dict(activity=True),
}


def calibrate_faults(sheet_key: str, out_dir=None) -> dict:
    """执行 GZEEB 断层三维标定。out_dir 缺省=图幅 root。"""
    sh = get_sheet(sheet_key)
    prof = get_profile(sh.key)
    sheet = prof.sheet
    prof_get = lambda k, d=None: getattr(prof, k, d)
    from pathlib import Path as _P
    _outdir = _P(out_dir) if out_dir is not None else sh.root
    _outdir.mkdir(parents=True, exist_ok=True)

    def _out(name):
        return str(_outdir / name)
    fl = load_source_layer(str(sh.root), "LDZOFBA003.WL", graphic=False)
    ent_p = str(sh.root / prof_get("entities_csv", "fault_entities.csv"))
    ent = pd.read_csv(ent_p, dtype=str)
    seg2fid = dict(zip(ent["seg_idx"].astype(int), ent["fault_id"].astype(str)))
    seg2v = dict(zip(ent["seg_idx"].astype(int),
                     ent["aux_verdict"].astype(str))) \
        if "aux_verdict" in ent.columns else {}
    # 命名断层实体信息（fault_id 级）
    ent_first = ent.groupby("fault_id").first() if "fault_id" in ent.columns else None

    # 反演标定通道数据（2026-09-26 用户定：产状测量点解析成果反演标定所属
    # 断层编码语义）——注释点按段聚合（注释值×GZECE 一致性检备用）
    seg_notes = {}
    asc_p = str(sh.root / prof_get("assoc_csv", "fault_aux_point_association.csv"))
    if os.path.exists(asc_p):
        asc = pd.read_csv(asc_p, dtype=str)
        for _, ar in asc[asc["kind"] == "number"].iterrows():
            sg = ar.get("seg_idx")
            if sg is None or str(sg) in ("", "nan", "None"):
                continue
            try:
                dv = float(ar.get("dip") or 0)
            except (TypeError, ValueError):
                dv = 0.0
            if dv > 0:
                seg_notes.setdefault(int(float(sg)), []).append(dv)
    # aux 证据强度（组合组数：n_triplets 多组互证 > 单组）
    seg2ntr = dict(zip(ent["seg_idx"].astype(int),
                       ent["n_triplets"].astype(str))) \
        if "n_triplets" in ent.columns else {}

    # 语义注册表（各幅码义）
    # 语义注册表（码义随幅）：图幅侧优先，包数据兜底
    _sem_cands = [sh.root / f"fault_semantics_{sheet}.json",
                  sh.root / "data" / "gzeeb_codes.json"]
    sem_p = None
    for _c in _sem_cands:
        if _c.exists():
            sem_p = str(_c)
            break
    if sem_p is None:
        sem_p = str(data_path("gzeeb_codes.json"))
    sem_j = json.load(open(sem_p, encoding="utf-8"))
    gsem = sem_j.get("gzeeb_semantics") or sem_j.get("codes") or {}
    gzeld_sem = sem_j.get("gzeld_semantics", {})

    # 覆盖库（三维分载，adjudicated+expect 防漂移）
    ov = {}
    for cand in (sh.root / f"fault_type_overrides_{sheet}.json",
                 sh.root / "fault_type_overrides.json",
                 sh.root / "data" / "fault_type_overrides.json"):
        if cand.exists():
            ov = json.loads(cand.read_text(encoding="utf-8")).get("overrides", {})
            break

    # 覆盖联合（证据级别层）
    LAT0 = prof.center_lat_hint
    LON_M = 111320.0 * math.cos(math.radians(LAT0))
    ice = (load_source_layer(str(sh.root), "LDLYAAE002.WP", graphic=False) if (sh.root / "LDLYAAE002.WP").exists() or (sh.root / "geojson" / "L0" / "LDLYAAE002.WP.geojson").exists() else gpd.GeoDataFrame())
    ice_u = ice.geometry.union_all() if len(ice) else None
    wl = (load_source_layer(str(sh.root), "LDLYAAE001.WL", graphic=False) if (sh.root / "LDLYAAE001.WL").exists() or (sh.root / "geojson" / "L0" / "LDLYAAE001.WL.geojson").exists() else gpd.GeoDataFrame())
    water_u = wl.geometry.union_all().buffer(100.0 / LON_M) if len(wl) else None
    poly = load_source_layer(str(sh.root), "LDZOFBB001.WP", graphic=False)
    from shapely.ops import unary_union
    # 半胶结第四纪沉积物剔除（2026-09-27 用户定：西域群/乌恰群等不属于
    # 第四系松散沉积物范畴——西域组 Qp1X 剔除在案；清单走 priors
    # quaternary_exclude 参数化，它幅半胶结单元码入列即生效）
    _priors = load_priors(sheet)
    _q_excl = set(_priors.get("quaternary_exclude", ["Qp1X"]))
    q_geoms = [g for g, c in zip(poly.geometry.values,
                                 poly["QDUECC"].astype(str).values)
               if g is not None and not g.is_empty
               and (_unit_age_rank(c) or 0) >= 1300
               and not any(x in c for x in _q_excl)]
    quat_u = unary_union(q_geoms) if q_geoms else None
    cover_u = unary_union([u for u in (ice_u, water_u, quat_u) if u is not None])

    # ---- 三类自支持补强通道数据（2026-09-26 用户定：复活断层/推覆体边界/
    # 活动断层判别依据不足补强）----
    from shapely.affinity import scale as _scale
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree
    _pgeoms, _pcodes, _pages = [], [], []
    for _fn in ("LDZOFBB001.WP", "LDZOFBB002.WP", "LDZOFBB003.WP",
                "LDZOFBB004.WP"):
        try:
            _gp = load_source_layer(str(sh.root), _fn, graphic=False)
        except Exception:
            continue
        for _g, _c in zip(_gp.geometry.values, _gp["QDUECC"].astype(str).values):
            if _g is None or _g.is_empty:
                continue
            _pgeoms.append(_scale(_g, xfact=LON_M, yfact=111320.0,
                                  origin=(0, 0)))
            _pcodes.append(_c)
            _pages.append(_unit_age_rank(_c))
    _ptree = STRtree(_pgeoms)
    quat_m = _scale(quat_u, xfact=LON_M, yfact=111320.0, origin=(0, 0)) \
        if quat_u is not None else None

    # ---- 活动性强先验线（2026-09-28 用户定）：断层与「第四系松散沉积物和地层
    # 的接触界线」重合 → 活动（复活）倾向；实体多段重合加强。
    # 线源=L1 界线标定语义层 sem_label（双幅通用，免码面差异）；
    # 证据=自有数据几何通道，独立根类 ACONT（与 QUAT 切割/控制正交）；
    # 强候选登记交人工裁定——不自动改码（不改 GZEEB/verdict）。
    import geopandas as _gpd2
    q2_union = None
    try:
        _bq = _gpd2.read_file(sh.root / "geojson" / "L1" / "boundaries.geojson")
        # 语义双形：通用规则段标「第四系界线」（941 段）+特殊码段标
        # 「第四系松散沉积物界线」（4 段）——均为第四系松散沉积物界线
        _lb = _bq["sem_label"].astype(str)
        _q2 = _bq[_lb.str.contains("第四系") & _lb.str.endswith("界线")]
        if len(_q2):
            q2_union = unary_union([
                _scale(g, xfact=LON_M, yfact=111320.0, origin=(0, 0))
                for g in _q2.geometry.values if g is not None and not g.is_empty])
    except OSError:
        pass
    print(f"   活动性强先验线（第四系松散沉积物界线）: "
          f"{len(_q2) if q2_union is not None else 0} 条")
    # 段级倾向（aux b 标定真值 dip_az 优先）
    seg_dipaz = {}
    asc_p = prof_get("assoc_csv", "fault_aux_point_association.csv")
    if os.path.exists(asc_p):
        asc = pd.read_csv(asc_p, dtype=str)
        for _, ar in asc[asc["sub_no"].isin(["1894", "1851"])].iterrows():
            try:
                sg_i, da_f = int(float(ar.get("seg_idx"))), float(ar.get("dip_az"))
            except (TypeError, ValueError):
                continue
            if da_f == da_f:
                seg_dipaz.setdefault(sg_i, da_f)

    def _sides_units(fm, probe=300.0):
        """米制线两侧单元 {code: age_rank}（+n/−n 两侧，7 点探针）。"""
        import numpy as _np
        total = fm.length
        if total < 1e-9:
            return {}, {}
        coords = _np.array(fm.coords)
        sl = _np.sqrt(((_np.diff(coords, axis=0)) ** 2).sum(axis=1))
        cum = _np.concatenate([[0], _np.cumsum(sl)])
        left, right = {}, {}
        for k in range(7):
            d = total * (k + 0.5) / 7
            j = max(0, min(int(_np.searchsorted(cum, d)) - 1, len(coords) - 2))
            if sl[j] < 1e-10:
                continue
            t = (d - cum[j]) / sl[j]
            p = coords[j] * (1 - t) + coords[j + 1] * t
            tg = coords[j + 1] - coords[j]
            nm = _np.array([-tg[1], tg[0]])
            for sgn, acc in ((1, left), (-1, right)):
                q = Point(p[0] + sgn * nm[0] * probe,
                          p[1] + sgn * nm[1] * probe)
                ii = _ptree.query(q, predicate="intersects")
                if len(ii):
                    acc[_pcodes[ii[0]]] = _pages[ii[0]]
        return left, right

    # 走滑钩（238/239）位置集
    wt = load_source_layer(str(sh.root), "LDZOFBB099.WT")
    aux_f = wt[wt["CHFCEC"] == prof.aux_filter]
    hooks = [(int(i), row.geometry.x, row.geometry.y, int(row["symbol_no"]))
             for i, row in aux_f.iterrows()
             if int(row["symbol_no"]) in (238, 239)]

    rows, conflicts = [], []
    for idx, row in fl.iterrows():
        g = row.geometry
        if g is None or g.is_empty:
            continue
        gz = str(row.get("GZEEB") or "")
        fid = seg2fid.get(int(row.get("_src_id", idx)))
        ent_info = {}
        if ent_first is not None and fid in ent_first.index:
            e = ent_first.loc[fid]
            ent_info = {"fault_name": e.get("name", ""), "level": e.get("level", ""),
                        "aux_verdict": e.get("aux_verdict", "")}
        # 覆盖库（三维分载）
        ov_e = ov.get(str(idx))
        eff = gz
        evidence_class = structural_type = activity = None
        adjudicated = False
        if ov_e and ov_e.get("status") == "adjudicated" \
                and str(ov_e.get("original")) == gz:
            eff = str(ov_e.get("effective", gz))
            evidence_class = ov_e.get("evidence_class")
            structural_type = ov_e.get("structural_type")
            activity = ov_e.get("activity")
            adjudicated = True

        # 结构语义（生效码 → 注册表语义）
        sem_entry = gsem.get(eff, {})
        sem_name = norm_sem(sem_entry.get("semantic", sem_entry.get("meaning", "")))
        # 2026-09-26 三维分层归位：码义=推测断层属**证据级别层**而非结构类型层
        # （覆盖致盲成图方式不掩盖结构性质）——结构层落「断层泛称」（结构未
        # 分型，随实体/待裁定），证据层标「推测」；覆盖校验仍按推测期望执行
        # （exp 按原码义取）。
        exp_name = sem_name
        if sem_name == "推测断层" and structural_type is None:
            structural_type = "断层泛称"
            if evidence_class is None:
                evidence_class = "推测"
        structural_type = structural_type or sem_name or "断层泛称"
        # 证据级别层
        fc = g.intersection(cover_u).length / g.length if cover_u is not None else 0.0
        if evidence_class is None:
            evidence_class = ("推测" if fc >= 0.5 else
                              "实测" if fc < 0.1 else "部分覆盖")
        # 活动性层
        if activity is None:
            activity = "活动" if eff == "37" else ("未评")

        # ---- 结构类型层多通道互证 ----
        exp = EXPECT.get(exp_name, {})
        checks, viol = [], []
        gzeld = str(row.get("GZELD") or "")
        gzeld_sem_now = gzeld_sem.get(gzeld, gzeld)
        if exp.get("gzeld_kin"):
            # 运动学语义期望（压性/张性/左行/右行），按本幅 gzeld 码义注册表比对
            kin_ok = str(gzeld_sem_now).startswith(exp["gzeld_kin"])
            checks.append(f"GZELD={gzeld}({gzeld_sem_now})")
            if not kin_ok:
                viol.append(f"GZELD={gzeld}({gzeld_sem_now}) 不符期望"
                            f" {exp['gzeld_kin']}")
        dip = None
        try:
            dip = float(row.get("GZECE") or 0)
        except (TypeError, ValueError):
            dip = None
        if exp.get("dip") and dip is not None and dip > 0:
            lo, hi = exp["dip"]
            checks.append(f"dip={dip:.0f}°")
            if not (lo <= dip <= hi):
                viol.append(f"dip={dip:.0f}° 超期望 [{lo},{hi}]°")
        elif exp.get("dip") and structural_type == "推测断层":
            pass
        # aux 三元组正逆（NaN 归一化：dtype=str 下空值为 float NaN）
        auxv_raw = ent_info.get("aux_verdict", "")
        auxv = str(auxv_raw).strip()
        if auxv in ("nan", "None", ""):
            auxv = ""
        if exp.get("aux") and auxv:
            checks.append(f"aux={auxv}")
            if auxv == "混合判别（交检核）":
                viol.append("aux=混合判别（交检核）")
            elif auxv != exp["aux"]:
                viol.append(f"aux={auxv} 不符期望 {exp['aux']}")
        # aux 证据强度注记（组合组数：多组互证强于单组；反演标定分级）
        _ntr = seg2ntr.get(int(row.get("_src_id", idx)), "")
        if auxv and _ntr and _ntr not in ("nan", "None", "0"):
            checks.append(f"aux 组数×{_ntr}")
        # 注释值×GZECE 一致性（2026-09-26 用户定反演标定通道）：
        # 产状测量点（倾角注释）反证所属断层编码倾角——|注释−GZECE|>2°
        # 即编码与测量不一致（编图错误候选，登记不改码）
        if dip is not None and dip > 0:
            _seg_id = int(row.get("_src_id", idx))
            for dv in seg_notes.get(_seg_id, []):
                if abs(dv - dip) <= 2.0:
                    checks.append(f"注释{dv:.0f}°≈GZECE")
                else:
                    viol.append(f"注释 {dv:.0f}° 与 GZECE {dip:.0f}° "
                                f"不符（Δ{abs(dv - dip):.0f}°，编图错误候选）")
        # ---- 三类自支持补强（2026-09-26 用户定：复活/推覆/活动判别依据不足补强） ----
        _fm = LineString([(c[0] * LON_M, c[1] * 111320.0) for c in g.coords])
        if structural_type == "推覆体边界":
            _L, _R = _sides_units(_fm)
            if _L and _R:
                _rep = set(_L) & set(_R)
                if _rep:
                    checks.append(f"地层重复({'/'.join(sorted(_rep))}，推覆重复)")
                _da = seg_dipaz.get(int(row.get("_src_id", idx)))
                _aL = max((a for a in _L.values() if a), default=None)
                _aR = max((a for a in _R.values() if a), default=None)
                if _da is not None:
                    _c0 = _fm.coords
                    _tx, _ty = _c0[-1][0] - _c0[0][0], _c0[-1][1] - _c0[0][1]
                    _tn = math.hypot(_tx, _ty) or 1.0
                    _nx, _ny = -_ty / _tn, _tx / _tn
                    _dx, _dy = math.sin(math.radians(_da)), math.cos(math.radians(_da))
                    _hw_is_left = (_dx * _nx + _dy * _ny) > 0
                    _ah = _aL if _hw_is_left else _aR
                    _af = _aR if _hw_is_left else _aL
                    if _ah and _af:
                        # age_rank 越大越年轻——老盖新（推覆）= 倾向盘 rank 更小
                        if _ah < _af:
                            checks.append(f"老盖新（倾向盘 {_ah} 老于下盘 {_af}）")
                        elif _ah > _af:
                            viol.append(f"新盖老（倾向盘 {_ah} 新于下盘 {_af}），"
                                        f"不符推覆期望（或 dip_az 反置待核）")
                        # _ah == _af：同龄不判
                elif _aL and _aR and abs(_aL - _aR) >= 200:
                    checks.append(f"新老差显著（{_aL}|{_aR}，倾向未定）")
        elif structural_type == "复活断层":
            if auxv == "正断层产状点":
                checks.append("aux 正断层产状点（复活期伸展活动）")
            elif auxv == "逆断层产状点":
                checks.append("aux 逆断层产状点（早期活动）")
            if quat_m is not None:
                _qcut = _fm.intersection(quat_m).length
                if _qcut > 0:
                    checks.append(f"切割第四系 {_qcut:.0f}m")
                elif _fm.distance(quat_m.boundary) <= 100.0:
                    checks.append("控制第四系边界")
        elif structural_type == "活动断层":
            if quat_m is not None:
                _qcut = _fm.intersection(quat_m).length
                if _qcut > 0:
                    checks.append(f"切割第四系 {_qcut:.0f}m")
                elif _fm.distance(quat_m.boundary) <= 100.0:
                    checks.append("控制第四系边界")
            if ice_u is not None and g.length:
                _fi = g.intersection(ice_u).length / g.length
                if _fi > 0:
                    checks.append(f"入冰雪区 {_fi * 100:.0f}%（冰川山前带旁证）")

        # 推测覆盖证据（2026-09-25 用户定复合判据）：覆盖≥50% 或沿覆盖边缘
        # ≤1km（库尔干 04「沿覆盖区边缘」判据兼容——边缘段同样靠推测成图）
        if exp.get("cover_min") and fc * 100 < exp["cover_min"]:
            _d_edge = None
            if cover_u is not None:
                try:
                    _d_edge = g.distance(cover_u.boundary) * LON_M
                except Exception:
                    _d_edge = None
            if _d_edge is None or _d_edge > 1000.0:
                viol.append(f"cover={fc * 100:.0f}% < {exp['cover_min']}% "
                            f"且距覆盖边缘 {_d_edge if _d_edge is not None else float('nan'):.0f}m >1km")
            else:
                checks.append(f"cover={fc * 100:.0f}% 沿覆盖边缘 "
                              f"{_d_edge:.0f}m")

        # 判定与置信度
        if adjudicated:
            verdict, conf = "裁定（覆盖库）", 1.0
        elif viol:
            verdict, conf = "违反（待裁定）", 0.3
            conflicts.append({
                "fault_id": fid, "segs": str(idx),
                "issue": f"GZEEB={gz}({structural_type}) 证据冲突",
                "evidence": "；".join(viol), "status": "pending_review"})
        else:
            n_ev = len(checks)
            verdict = "verified" if n_ev >= 2 else "consistent"
            conf = 0.9 if n_ev >= 2 else (0.75 if n_ev == 1 else 0.6)
        rows.append(dict(
            idx=idx, fault_id=fid, GZEEB=gz, gzeeb_eff=eff,
            structural_type=structural_type, evidence_class=evidence_class,
            activity=activity, GZELD=gzeld, gzeld_sem=gzeld_sem_now,
            GZECE=dip if dip is not None else None, cover_pct=round(fc * 100),
            checks="；".join(checks), verdict=verdict, confidence=conf,
            **ent_info))

    # ---- 活动性强先验后处理（2026-09-28 用户定）：逐段几何重合计算 +
    # 实体级聚合（多段重合加强）+ 强候选登记交人工裁定。
    from collections import defaultdict as _dd
    Q2_TOL_M = 50.0
    Q2_MIN_OV = 150.0        # 重合有效长度下限（m，取 max(150, 0.1×段长)）
    coinc = _dd(list)        # fault_id → [(seg_idx, overlap_m)]
    if q2_union is not None:
        q2_buf = q2_union.buffer(Q2_TOL_M)
        for r in rows:
            _si = int(r["idx"])
            _g = fl.geometry.iloc[_si]
            if _g is None or _g.is_empty:
                continue
            fm = LineString([(c[0] * LON_M, c[1] * 111320.0)
                             for c in _g.coords])   # 米制化后与 q2_buf 同空间
            if not fm.intersects(q2_buf):
                continue
            ov_m = fm.intersection(q2_buf).length
            if ov_m >= max(Q2_MIN_OV, 0.1 * fm.length):
                coinc[r["fault_id"]].append((_si, ov_m))
        for r in rows:
            hits = coinc.get(r["fault_id"], [])
            if not hits:
                continue
            own = next((m for s, m in hits if s == int(r["idx"])), 0.0)
            if own:
                r["checks"] += f"；第四系界线重合 {own:.0f}m"
            if len(hits) >= 2:
                r["checks"] += f"；实体第四系界线重合×{len(hits)}段（活动候选）"
        n_strong = 0
        for r in rows:
            fid = r["fault_id"]
            hits = coinc.get(fid, [])
            n = len(hits)
            own = next((m for s, m in hits if s == int(r["idx"])), 0.0)
            if str(r["activity"]) == "活动":
                # 佐证只落自身重合行（行级证据语义；防他段证据抬升本行 I 档）
                if own and "活动性佐证" not in r["checks"]:
                    tag = f"×{n}段" if n >= 2 else ""
                    r["checks"] += f"；活动性佐证（第四系界线重合{tag}）"
            elif n >= 2:
                r["activity"] = f"活动候选（第四系界线重合×{n}段，待裁定）"
                n_strong += 1
                conflicts.append({
                    "fault_id": fid,
                    "segs": str([s for s, _ in hits]),
                    "issue": f"活动断层候选：实体 {n} 段与第四系松散沉积物界线重合"
                             f"（总重合 {sum(m for _, m in hits):.0f}m），"
                             f"非 37 码——交人工裁定",
                    "evidence": "第四系界线重合强先验（2026-09-28 用户定）",
                    "status": "pending_review"})
        print(f"   活动性先验：重合实体 {len(coinc)} 个（多段重合强候选 {n_strong} 行）")

    # 影子置信度（统一框架 S×I×F，2026-09-27 裁定参数；旧列 confidence 不动）
    from pymapgis.semantics.confidence import (check_classes, emit_columns,
                                               evaluate)
    # F3 审计修正（2026-09-28）：dip= 直读 GZECE 码面与注释≈GZECE 回声
    # 同根（GZECE 值）——合并为 GZECE 类，防同类双计伪互证（双幅当前
    # 「仅含此二类」行数 0，纯防漂移）
    _GZCLASS = {"KIN": ("GZELD=", "aux", "钩"),  # 运动学同源合一（走滑案护栏）
                "GZECE": ("dip=", "注释",),
                "STRAT": ("地层重复", "老盖新", "新老差显著"),
                "QUAT": ("切割第四系", "控制第四系边界"),
                "ACONT": ("第四系界线重合", "活动性佐证"),  # 2026-09-28 活动性强先验
                "GLAC": ("入冰雪区",), "COVER": ("cover=",)}
    for r in rows:
        v = str(r["verdict"])
        # 顺序敏感：「违反（待裁定）」含"裁定"子串——先判违反
        if "违反" in v:
            bd = evaluate("multi", fit=0.0, reasons=("违反",))
        elif "裁定" in v:
            bd = evaluate("adjudicated", adjudicated=True,
                          reasons=("覆盖库裁定",))
        else:
            ch = str(r.get("checks") or "")
            n_ev = len([c for c in ch.split("；") if c.strip()])
            if n_ev == 0:
                bd = evaluate("code_read", "single", evaluated=False,
                              reasons=("0 checks（无假设可评）",))
            else:
                n_cls = len(check_classes(ch, _GZCLASS))
                indep = ("multi_root" if n_cls >= 2
                         else "intra_class" if n_cls == 1 else "single")
                s = "multi" if n_ev >= 2 else "single"
                cex = any(k in str(r.get("aux_verdict", ""))
                          for k in ("混合", "存疑", "反置"))
                bd = evaluate(s, indep, 1.0, counterexample_open=cex,
                              reasons=(f"checks={n_ev}", f"根类={n_cls}"))
        emit_columns(r, bd, shadow=True)

    out = pd.DataFrame(rows)
    out.to_csv(f"{_out(f'_gzeeb_calibration_{sheet}.csv')}", index=False,
               encoding="utf-8-sig")
    if conflicts:
        new_conf = pd.DataFrame(conflicts)
        reg_p = str(_out(f"_gzeeb_conflicts_{sheet}.csv"))
        if os.path.exists(reg_p):
            # 登记册合并：已裁定条目（adjudicated）保留在前，新计算冲突在后
            old = pd.read_csv(reg_p, dtype=str)
            keep = old[old["status"] == "adjudicated"]
            new_conf = pd.concat([keep, new_conf], ignore_index=True)
        new_conf.to_csv(reg_p, index=False, encoding="utf-8-sig")
    print(f"断层类别标定: {len(rows)} 段 → {_out(f'_gzeeb_calibration_{sheet}.csv')}；", end="")
    print(f"冲突登记 {len(conflicts)} 条 → {_out(f'_gzeeb_conflicts_{sheet}.csv')}")
    print("三维分布:")
    print("  结构类型:", out["structural_type"].value_counts().to_dict())
    print("  证据级别:", out["evidence_class"].value_counts().to_dict())
    print("  活动性:", out["activity"].value_counts().to_dict())
    print("  verdict:", out["verdict"].value_counts().to_dict())



    return {
        "rows": len(rows),
        "conflicts": len(conflicts),
        "verdicts": out["verdict"].value_counts().to_dict(),
        "structural": out["structural_type"].value_counts().to_dict(),
        "evidence": out["evidence_class"].value_counts().to_dict(),
        "activity": out["activity"].value_counts().to_dict(),
        "out_dir": str(_outdir),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c calibrate-gzeeb")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    stats = calibrate_faults(args.sheet, out_dir=args.out)
    print("标定完成:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
