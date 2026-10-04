# -*- coding: utf-8 -*-
"""断裂接触活动断层审计（geosciml4china.calibrate 第七域，2026-10-02 用户
裁定兜底机制：「在地质界线解析完成后，对断裂接触单独加一层审计，以判别
活动断层」）。

识别标志（用户确认）：「断裂是第四系松散沉积物与地层的边界一致，是活动
断层的典型识别标志」。本层以**断裂接触界线段**（gzbd 标定语义=断层接触
（断裂界线），GZBD=10）为入口——与 gzeeb 的「断层线×Q 面元边界重合」
通道（线视角）互补的**界线视角**独立证据面：断裂接触作为 Q 松散沉积物与
地层之间的边界者=活动断层候选。

判据：断裂接触段两侧单元探针（7 点×±300m）——一侧为第四系松散沉积物
（age_rank≥1300，剔 Qp1X）、另一侧为地层（age_rank<1300）→ 活动候选
登记（pending 交人工裁定，不自动改码）。两侧皆 Q 或皆地层、无宿主 → 不候选。

产出：_fault_contact_activity_<key>.csv（逐段证据+候选判定）
     + 冲突册 _gzeeb_conflicts_<key>.csv 追加活动候选行（合并制）。

CLI: python -m geosciml4china.calibrate.fault_contact_activity --sheet <key>
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.affinity import scale as _scale
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from pymapgis.rendering.pdf_writer import _unit_age_rank
from pymapgis.semantics.profile import get_profile

from ..sheets import get_sheet
from .priors import load_priors

PROBE_M = 300.0     # 两侧探针距离上限（与 gzeeb 推覆探针同口径）
PROBE_STEPS_M = (40.0, 100.0, 300.0)  # 自适应逐级探针（2026-10-02 活动断层
                  # 审计 A8：最小距离命中即取——细窄真实单元不被大步长越过，
                  # 与 gzbd 自适应探针裁定同一原则）
N_PROBE = 7         # 每侧探针点数
Q_RANK = 1300.0     # 第四系松散沉积物 age_rank 门槛（priors 可覆盖）


def calibrate_fault_contact_activity(sheet_key: str, out_dir=None) -> dict:
    sh = get_sheet(sheet_key)
    prof = get_profile(sh.key)
    lat = float(prof.center_lat_hint)
    LON_M = 111320.0 * math.cos(math.radians(lat))
    LAT_M = 111320.0
    outdir = Path(out_dir) if out_dir else sh.root
    outdir.mkdir(parents=True, exist_ok=True)

    # ① 断裂接触段（gzbd 标定语义）
    si_p = sh.root / "_gzbd_semantic_interpretation.csv"
    if not si_p.exists():
        print(f"断裂接触审计[{sh.key}]: 无 gzbd 标定表，跳过")
        return {"rows": 0, "out_dir": str(outdir)}
    si = pd.read_csv(si_p, dtype=str)
    # 断裂接触入口（2026-10-02 泛化修订，用户质询「断裂接触未必对应 GZBD=10，
    # 这依赖于具体标定」）：不再硬编码 GZBD=10 的标定标签——①注册表驱动：
    # gzbd 码义注册表中语义含「断层接触/断裂界线」的码（GZBD_eff ∈ 该码集）；
    # ②标签模式兜底：标定语义含「断层接触/断裂界线」者（它幅标定另立标签时）
    import json as _json
    _gz_codes = {}
    for _cand in (sh.root / "data" / "gzbd_codes.json",
                  Path(__file__).parent.parent / "data" / "gzbd_codes.json"):
        if _cand.exists():
            _gz_codes = _json.load(open(_cand, encoding="utf-8")).get(
                "gzbd_semantics") or                 _json.load(open(_cand, encoding="utf-8")).get("codes") or {}
            break
    _fc_codes = {str(k) for k, v in _gz_codes.items()
                 if any(t in str(v.get("semantic", v.get("meaning", ""))
                               if isinstance(v, dict) else v)
                        for t in ("断层接触", "断裂界线"))}
    if "GZBD_eff" in si.columns:
        fc = si[si["GZBD_eff"].astype(str).str.zfill(2).isin(_fc_codes)]
    else:
        fc = si.iloc[0:0]
    _lab_fc = si[~si["idx"].astype(int).isin({int(x) for x in fc["idx"]})
                 & si["标定语义"].astype(str).str.contains("断层接触|断裂界线",
                                                         na=False)]
    fc = pd.concat([fc, _lab_fc], ignore_index=True)
    if not len(fc):
        print(f"断裂接触审计[{sh.key}]: 0 段断层接触")
        return {"rows": 0, "out_dir": str(outdir)}
    fc_ids = {int(x) for x in fc["idx"]}

    # ② 面元（四 WP，米制）+ 第四系排除（priors 参数化）
    _pri = load_priors(sh.key) or {}
    _q_excl = set(_pri.get("quaternary_exclude", ["Qp1X"]))
    _q_rank = float(_pri.get("quaternary_rank_min", Q_RANK))
    geoms, codes, ranks = [], [], []
    for fn in ("LDZOFBB001.WP", "LDZOFBB002.WP", "LDZOFBB003.WP",
               "LDZOFBB004.WP"):
        p = sh.root / "geojson" / "L0" / f"{fn}.geojson"
        if not p.exists():
            continue
        gp = gpd.read_file(p)
        for g, c in zip(gp.geometry.values, gp["QDUECC"].astype(str).values):
            if g is None or g.is_empty:
                continue
            geoms.append(_scale(g, xfact=LON_M, yfact=LAT_M, origin=(0, 0)))
            codes.append(c)
            ranks.append(_unit_age_rank(c) or 0.0)
    tree = STRtree(geoms)

    def _norm(c):
        return re.sub(r"[→↓↑.-]", "", str(c)).strip()

    def _is_q(c):
        _nc = _norm(c)
        return ((_unit_age_rank(c) or 0) >= _q_rank
                and not any(x in _nc for x in _q_excl))

    # ③ 逐段两侧探针
    bnd = gpd.read_file(sh.root / "geojson" / "L0" / "LDZOFBA002.WL.geojson")
    rows = []
    for idx in sorted(fc_ids):
        g = bnd.geometry.iloc[idx]
        if g is None or g.is_empty or g.geom_type != "LineString":
            continue
        fm = LineString([(c[0] * LON_M, c[1] * LAT_M) for c in g.coords])
        coords = np.array(fm.coords)
        sl = np.sqrt((np.diff(coords, axis=0) ** 2).sum(axis=1))
        cum = np.concatenate([[0], np.cumsum(sl)])
        left, right = {}, {}
        for k in range(N_PROBE):
            d = fm.length * (k + 0.5) / N_PROBE
            j = max(0, min(int(np.searchsorted(cum, d)) - 1, len(coords) - 2))
            if sl[j] < 1e-10:
                continue
            t = (d - cum[j]) / sl[j]
            p = coords[j] * (1 - t) + coords[j + 1] * t
            tg = coords[j + 1] - coords[j]
            nm = np.array([-tg[1], tg[0]])
            for sgn, acc in ((1, left), (-1, right)):
                for _step in PROBE_STEPS_M:
                    q = Point(p[0] + sgn * nm[0] * _step,
                              p[1] + sgn * nm[1] * _step)
                    ii = tree.query(q, predicate="intersects")
                    # 活动断层审计（2026-10-02）：全命中登记——多 WP 层边缘
                    # 重叠时首命中任意（intersects 序不定），取首可能漏真实
                    # Q/地层侧；最小距离命中即取（A8 自适应探针）
                    if len(ii):
                        for _i in ii:
                            acc[codes[_i]] = ranks[_i]
                        break
        q_left = {c for c in left if _is_q(c)}
        q_right = {c for c in right if _is_q(c)}
        s_left = {c for c in left if c not in q_left}
        s_right = {c for c in right if c not in q_right}
        if q_left and s_right:
            cand = "活动候选（Q在+n侧）"
        elif q_right and s_left:
            cand = "活动候选（Q在−n侧）"
        else:
            cand = ""
        rows.append(dict(idx=idx, Q侧="+n" if q_left else ("−n" if q_right else "无"),
                         第四系_unit="/".join(sorted(q_left | q_right)),
                         地层_unit="/".join(sorted(s_left | s_right)),
                         候选=cand))

    out = pd.DataFrame(rows)
    out_p = outdir / f"_fault_contact_activity_{sh.key}.csv"
    out.to_csv(out_p, index=False, encoding="utf-8-sig")
    n_cand = int((out["候选"] != "").sum())
    print(f"断裂接触审计[{sh.key}]: {len(out)} 段断层接触 → {out_p.name}"
          f"；活动候选 {n_cand} 段")

    # ④ 候选归因+独立登记册（2026-10-02 活动断层审计 A7：原 fault_id 为空、
    # segs=界线 idx 空间——build 横幅消费方（read_fault_conflict_entities，
    # (fault_id, 断层段) 键）无法挂载，登记册断链。现边界段
    # intersects→nearest 挂实测断层线（LDZOFBA003，与 gzeeb 同宇宙），
    # fault_id 经 fault_entities 归组；>ATTRIB_MAX_M 无断层线者不登记
    # （证据表仍全量保留））
    ATTRIB_MAX_M = 300.0
    reg_rows = []
    if n_cand:
        cand_rows = out[out["候选"] != ""]
        fl = None
        _flp = sh.root / "geojson" / "L0" / "LDZOFBA003.WL.geojson"
        if _flp.exists():
            fl = gpd.read_file(_flp)
        # 泛化（2026-10-02 审计）：实体表名经剖面通道——原 key 分支对
        # jws（profile 声明正典件名）会找错文件致登记册 fault_id 断链
        from pymapgis.semantics.profile import get_profile as _gp
        _ent_p = sh.root / (_gp(sh.key).entities_csv or "fault_entities.csv")
        _seg2fid = {}
        if _ent_p.exists():
            _edf = pd.read_csv(_ent_p, dtype=str)
            for _, _er in _edf.iterrows():
                try:
                    _seg2fid[int(float(_er["seg_idx"]))] = str(_er["fault_id"])
                except (TypeError, ValueError):
                    continue
        if fl is not None and len(fl):
            _fgeoms = [_scale(g, xfact=LON_M, yfact=LAT_M, origin=(0, 0))
                       for g in fl.geometry.values]
            _ftree = STRtree(_fgeoms)
            for _, r in cand_rows.iterrows():
                _g = bnd.geometry.iloc[int(r["idx"])]
                if _g is None or _g.is_empty or _g.geom_type != "LineString":
                    continue
                _fm = LineString([(c[0] * LON_M, c[1] * LAT_M)
                                  for c in _g.coords])
                _ii = _ftree.query(_fm, predicate="intersects")
                if not len(_ii):
                    _ii = _ftree.nearest(_fm)
                # Shapely 2.x nearest() 返回标量索引（query 返回数组）——
                # 双形态兼容（2026-10-03 jwsss 裸接入首遇标量形态崩溃案）
                _seg = int(_ii if not hasattr(_ii, "__len__") else _ii[0])
                _d = _fm.distance(_fgeoms[_seg])
                if _d > ATTRIB_MAX_M:
                    continue
                _fid = _seg2fid.get(_seg, f"SEG{_seg}")
                reg_rows.append({
                    "fault_id": _fid, "segs": str(_seg),
                    "issue": "活动断层候选：断裂接触作为第四系松散沉积物-地层边界",
                    "evidence": f"断裂接触段{int(r['idx'])}（{r['候选']}，"
                                f"Q={r['第四系_unit']} vs "
                                f"地层={r['地层_unit']}；归因 {_fid} 段{_seg}，"
                                f"距断层线 {_d:.0f}m）",
                    "status": "pending_review"})
        if reg_rows:
            reg_p = outdir / f"_fault_contact_activity_conflicts_{sh.key}.csv"
            pd.DataFrame(reg_rows).to_csv(reg_p, index=False,
                                          encoding="utf-8-sig")
            _n_ent = len({r["fault_id"] for r in reg_rows})
            _tail = (f"，未归因 {n_cand - len(reg_rows)} 条）"
                     if n_cand > len(reg_rows) else "）")
            print(f"  → 独立登记册 {len(reg_rows)} 条（归因 {_n_ent} 实体{_tail}")
        else:
            print(f"  → 候选 {n_cand} 条均未归因（无 LDZOFBA003 断层线或超"
                  f"{ATTRIB_MAX_M:.0f}m），不入登记册")
    return {"rows": len(out), "candidates": n_cand, "out_dir": str(outdir)}


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c calibrate-fault-contact-activity")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    calibrate_fault_contact_activity(args.sheet, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
