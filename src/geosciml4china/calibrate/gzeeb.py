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
编码语义——①aux 正逆×结构期望（编图矛盾实证）③证据层×aux 交叉。
②注释值×GZECE 一致性（|Δ|>2° 登记编图错误候选）已撤销（2026-10-02
用户裁定「段上每个倾角注释与 GZECE 不再做比对」）。
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
from .registry import (activity_codes, load_gzeeb_semantics,
                        reverse_codes)


def norm_sem(s):
    return re.sub(r"[（(].*?[)）]", "", str(s)).strip()


# 断层名性质关键词（2026-10-01 用户裁定「断层名具有性质优先权」）：
# 编图命名=结构性质最高声明——查码顺序：覆盖库→断层名→码义注册表→泛称。
# 匹配序敏感（逆冲推覆先于逆冲；左/右型先于走滑）；性质随名、
# 名-证张力（如名推覆 vs 高角）入冲突册不改判
_NAME_SEM = [
    ("逆冲推覆", "推覆体边界"),
    ("逆冲", "逆断层"),
    ("逆掩", "逆断层"),
    ("逆断层", "逆断层"),
    ("正断层", "正断层"),
    ("左型走滑", "左型走滑断层"),
    ("右型走滑", "右型走滑断层"),
    ("左行", "左型走滑断层"),
    ("右行", "右型走滑断层"),
    ("走滑", "走滑断层"),
    ("平移", "走滑断层"),
    ("复活", "复活断层"),
    ("活动", "活动断层"),
]


def name_sem(fault_name: str) -> str:
    """断层名 → 结构性质语义（关键词命中；无命中=空串）。"""
    nm = str(fault_name or "")
    for kw, sem in _NAME_SEM:
        if kw in nm:
            return sem
    return ""

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
    # 复合断层（2026-10-01 用户建议新增）：分析型结构语义——码面走滑类
    # （16/18/走滑）× aux 倾滑判别（正/逆）双通道同段命中升格；分量随段标注
    # （复合断层（逆-右行）等）；GeoSciML 映射预注 CGI oblique_slip_fault
    "复合断层": dict(),
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

    # 「注释×GZECE 一致性」反演通道已撤销（2026-10-02 用户裁定「段上每个
    # 倾角注释与 GZECE 不再做比对」）——注释值只参与产状测量点配对与
    # 出站，不再反演标定/互验断层编码倾角
    # aux 证据强度（组合组数：n_triplets 多组互证 > 单组）
    seg2ntr = dict(zip(ent["seg_idx"].astype(int),
                       ent["n_triplets"].astype(str))) \
        if "n_triplets" in ent.columns else {}

    # 语义注册表（各幅码义）
    # 语义注册表（码义随幅）：图幅侧优先，包数据兜底
    _sem_cands = [sh.root / f"fault_semantics_{sheet}.json",
                  sh.root / "data" / "gzeeb_codes.json"]
    gsem, gzeld_sem = load_gzeeb_semantics(sh.root, sh.key)
    _act_codes = activity_codes(gsem, norm_sem)

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
    from shapely.ops import unary_union
    # 半胶结第四纪沉积物剔除（2026-09-27 用户定：西域群/乌恰群等不属于
    # 第四系松散沉积物范畴——西域组 Qp1X 剔除在案；清单走 priors
    # quaternary_exclude 参数化，它幅半胶结单元码入列即生效）
    _priors = load_priors(sheet)
    _q_excl = set(_priors.get("quaternary_exclude", ["Qp1X"]))
    _q_rank = float(_priors.get("quaternary_rank_min", 1300.0))
    # 活动断层审计（2026-10-02）：Q 面元宇宙=四 WP 全层（原仅 001 层——
    # 它幅 Q 单元若分布于 002-004 则 Q 并集缺漏，面元拓扑通道漏检）
    q_geoms = []
    for _qfn in ("LDZOFBB001.WP", "LDZOFBB002.WP", "LDZOFBB003.WP",
                 "LDZOFBB004.WP"):
        try:
            _qgp = load_source_layer(str(sh.root), _qfn, graphic=False)
        except Exception:
            continue
        for g, c in zip(_qgp.geometry.values,
                        _qgp["QDUECC"].astype(str).values):
            # 箭头归一后做排除检查（2026-10-02 F038 案：西域组原码
            # 「中Qp↓1→X」带 ↓/→ 箭头，子串 "Qp1X" 永不命中——
            # quaternary_exclude 被击穿致半固结西域组混入 Q 并集，
            # 活动标志与覆盖证据双双虚增；与 _younger_side 探针同口径）
            _cn = re.sub(r"[→↓↑]", "", c)
            if (g is not None and not g.is_empty
                    and (_unit_age_rank(c) or 0) >= _q_rank
                    and not any(x in _cn for x in _q_excl)):
                q_geoms.append(g)
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
    # （2026-10-02 泛化审计处置：原 sem_label 过滤构建的 q2_union 已死代码
    # 删除——活动标志源寄生在 gzbd 标定标签上是断裂接触同类泛化病；新通道
    # 已改为面元拓扑纯几何，此处不再依赖标定语义）
    # 段级倾向（aux b 标定真值 dip_az 优先）
    # 段级倾向（aux b 标定真值 dip_az 优先）
    seg_dipaz = {}
    asc_p = str(sh.root / prof_get("assoc_csv", "fault_aux_point_association.csv"))
    if os.path.exists(asc_p):
        asc = pd.read_csv(asc_p, dtype=str)
        for _, ar in asc[asc["sub_no"].isin([str(prof_get("b_symbol_raw", 1894))]).iterrows():
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

    # 走滑钩对（2026-10-01 空间识别通道——auxchain 产出 _fault_hooks_<key>.csv，
    # 238/239 钩旋向登记缺口就此闭合：识别不依赖符号码表，符号列仅作佐证）
    # 走滑钩对按**段号**索引（2026-10-01 用户想法：钩对语义=垂足投影点之间
    # 区段的运动学性质——表征所属断层的某段，而非整个断层实体）
    hook_by_seg = defaultdict(list)
    _hp = sh.root / f"_fault_hooks_{sh.key}.csv"
    if _hp.exists():
        _hdf = pd.read_csv(_hp, dtype=str)
        _n_pairs = 0
        for _, _hr in _hdf.iterrows():
            for _sg in str(_hr.get("segs") or "").split(","):
                if _sg.strip():
                    hook_by_seg[int(_sg)].append(_hr)
            _n_pairs += 1
        if _n_pairs:
            print(f"   走滑钩对（空间识别）: {_n_pairs} 对"
                  f" / 区间段 {len(hook_by_seg)} 段")

    # 未注册码签名预计算（2026-10-01 用户指令「优化判别逻辑」）：码级聚合——
    # 全段无实测倾角（GZECE=0）+ **真覆盖段（fc≥50%）≥2** → 推测断层签名
    # （与英吉沙 02「seg82 冰雪 100%/seg251 第四系 100% 强证据」裁定同构；
    # 库尔干 04「全无实测倾角」同款签名）。仅考察注册表未命中码；0% 覆盖
    # 远离边缘段的 cover_min 张力照常标违反交裁定（不自动豁免）。
    _code_dip, _code_buried, _code_n = set(), defaultdict(int), defaultdict(int)
    for _idx0, _row0 in fl.iterrows():
        _eff0 = str(_row0.get("GZEEB") or "")
        if not _eff0 or _eff0 in gsem:
            continue  # 注册表已裁定码义者不参与签名
        _code_n[_eff0] += 1
        try:
            _d0 = float(_row0.get("GZECE") or 0)
        except (TypeError, ValueError):
            _d0 = 0.0
        if _d0 > 0:
            _code_dip.add(_eff0)
        _g0 = _row0.geometry
        if cover_u is not None and _g0 is not None and not _g0.is_empty:
            _fc0 = (_g0.intersection(cover_u).length / _g0.length
                    if _g0.length else 0.0)
            if _fc0 >= 0.5:
                _code_buried[_eff0] += 1
    _sig_infer = {c for c in _code_n
                  if c not in _code_dip and _code_buried[c] >= 2}
    if _sig_infer:
        print(f"   推测断层签名判定: {sorted(_sig_infer)}"
              f"（全段无实测倾角+真覆盖段≥2）")

    rows, conflicts = [], []
    _unreg = {}  # 码义未注册聚合（2026-10-01 泛化缺口修复）：eff 码 → [段]
    _fallback_rows = []  # 一般断层兜底档案（2026-10-02 用户裁定）
    _mle_raw = defaultdict(lambda: defaultdict(int))  # 归位前 MLE 语义分布
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
        _carto = bool(ov_e and ov_e.get("status") == "cartographic_error")

        # 结构语义候选（查码顺序：覆盖库 effective_semantic（adjudicated 最高级）
        # → 码义注册表 → 断层名 → 未注册签名——均为 MLE 投票输入而非定论，
        # 2026-10-01 用户裁定「以最大似然概率标定编码的地质语义」）
        sem_entry = gsem.get(eff, {})
        sem_name = norm_sem(sem_entry.get("semantic", sem_entry.get("meaning", "")))
        _sem_from_reg = bool(sem_name)
        if not sem_name and adjudicated and ov_e.get("effective_semantic"):
            sem_name = norm_sem(ov_e["effective_semantic"])
            _sem_from_reg = True  # 覆盖库裁定语义=最高级先验
        _ns_hit = ""
        if not sem_name:
            _ns = name_sem(ent_info.get("fault_name", ""))
            if _ns:
                sem_name = _ns
                _ns_hit = str(ent_info.get("fault_name", ""))
        _sig_hit = False
        if not sem_name and eff in _sig_infer:
            sem_name = "推测断层"
            _sig_hit = True
        if not sem_entry and not sem_name and eff:
            _unreg.setdefault(eff, []).append(int(row.get("_src_id", idx)))

        # 证据解析（MLE 投票输入；供互验复用）
        gzeld = str(row.get("GZELD") or "")
        gzeld_sem_now = gzeld_sem.get(gzeld, gzeld)
        try:
            dip = float(row.get("GZECE") or 0)
        except (TypeError, ValueError):
            dip = None
        auxv_raw = ent_info.get("aux_verdict", "")
        auxv = str(auxv_raw).strip()
        if auxv in ("nan", "None", ""):
            auxv = ""
        # 覆盖分数（MLE 投票输入；证据层复用）
        fc = g.intersection(cover_u).length / g.length if cover_u is not None else 0.0

        # ---- MLE 语义标定（2026-10-01 用户裁定）----
        # 证据投票：注册/覆盖库语义先验 +3 / 断层名 +2 / 推测签名 +2 /
        # GZELD 运动学 +2 / GZECE 倾角域 +1 / aux 判别 +2；argmax 即标定；
        # 覆盖库 adjudicated 结构裁定=绝对；并列取注册先验、无先验并列落泛称；
        # 最高票 <2 落泛称（证据不足不硬标）
        votes = defaultdict(float)
        if _sem_from_reg:
            votes[sem_name] += 3
        if _ns_hit:
            votes[sem_name] += 2
        if _sig_hit:
            votes["推测断层"] += 2
        if str(gzeld_sem_now).startswith("压性"):
            votes["逆断层"] += 2
            votes["推覆体边界"] += 2
        elif str(gzeld_sem_now).startswith("张性"):
            votes["正断层"] += 2
        elif str(gzeld_sem_now).startswith("左行"):
            votes["左型走滑断层"] += 2
        elif str(gzeld_sem_now).startswith("右行"):
            votes["右型走滑断层"] += 2
        if dip is not None and dip > 0:
            if 25 <= dip <= 85:
                votes["逆断层"] += 1
            if 50 <= dip <= 90:
                votes["正断层"] += 1
            if 0 <= dip <= 35:
                votes["推覆体边界"] += 1
        if auxv == "逆断层产状点":
            votes["逆断层"] += 2
        elif auxv == "正断层产状点":
            votes["正断层"] += 2
        # 覆盖证据权重提升（2026-10-01 用户裁定）：第四系松散沉积物/冰雪区/
        # 水体中展布的断层（fc≥50%）或沿覆盖边缘段（≤1km）——编码值大概率
        # 为推测断层 +2（注册码先验 +3 仍优先，不翻已裁定码义）
        if fc >= 0.5:
            votes["推测断层"] += 2
        elif cover_u is not None:
            try:
                _dedge0 = g.distance(cover_u.boundary) * LON_M
            except Exception:
                _dedge0 = None
            if _dedge0 is not None and _dedge0 <= 1000.0:
                votes["推测断层"] += 2
        _mle_sem = "断层泛称"
        if votes:
            _mx = max(votes.values())
            if _mx >= 2:
                _win = [k for k, v in votes.items() if v == _mx]
                if len(_win) == 1:
                    _mle_sem = _win[0]
                elif sem_name in _win and _sem_from_reg:
                    _mle_sem = sem_name  # 并列取注册先验
                elif "推测断层" in _win:
                    # 推测属证据层（归位原则）——并列时让位结构性信号
                    _mle_sem = [k for k in _win if k != "推测断层"][0]
                else:
                    _mle_sem = "断层泛称"  # 无先验并列→不硬标
        if adjudicated and structural_type:
            _mle_sem = structural_type  # 覆盖库结构裁定=绝对
        _mle_raw[gz][_mle_sem] += 1
        # 一般断层兜底（2026-10-02 用户裁定）：码义无法标定——注册表未命中、
        # 断层名不蕴含地质语义、无辅助点呈现的地质语义（签名/MLE 均空）——
        # 统一归入一般断层，保障管线运转；详情入 _gzeeb_fallback_<key>.csv
        _fallback = (not sem_entry and not _ns_hit and not _sig_hit
                     and not adjudicated and _mle_sem == "断层泛称")

        # 2026-09-26 三维分层归位：推测断层属**证据级别层**而非结构类型层
        # ——结构层落「断层泛称」，证据层标「推测」；exp 按 MLE 标定语义取
        exp_name = _mle_sem
        if _mle_sem == "推测断层" and structural_type is None:
            structural_type = "断层泛称"
            if evidence_class is None:
                evidence_class = "推测"
        structural_type = structural_type or _mle_sem or "断层泛称"
        # 证据级别层
        if evidence_class is None:
            evidence_class = ("推测" if fc >= 0.5 else
                              "实测" if fc < 0.1 else "部分覆盖")
        # 活动性层（注册表驱动，2026-10-01 泛化：活动码集=语义=活动断层的码）
        if activity is None:
            activity = "活动" if eff in _act_codes else ("未评")

        # ---- 结构类型层多通道互证 ----
        exp = EXPECT.get(exp_name, {})
        checks, viol = [], []
        if _ns_hit:
            checks.append(f"断层名性质优先（{_ns_hit}→{sem_name}）")
        if _sig_hit:
            checks.append("推测断层签名（未注册码：全段无实测倾角+覆盖支撑≥2段）")
        if exp.get("gzeld_kin"):
            # 运动学语义期望（压性/张性/左行/右行），按本幅 gzeld 码义注册表比对
            kin_ok = str(gzeld_sem_now).startswith(exp["gzeld_kin"])
            checks.append(f"GZELD={gzeld}({gzeld_sem_now})")
            if not kin_ok:
                viol.append(f"GZELD={gzeld}({gzeld_sem_now}) 不符期望"
                            f" {exp['gzeld_kin']}")
        if exp.get("dip") and dip is not None and dip > 0:
            lo, hi = exp["dip"]
            checks.append(f"dip={dip:.0f}°")
            if not (lo <= dip <= hi):
                viol.append(f"dip={dip:.0f}° 超期望 [{lo},{hi}]°")
        elif exp.get("dip") and structural_type == "推测断层":
            pass
        # aux 三元组正逆
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
        # 「注释×GZECE 一致性」反演通道撤销（2026-10-02 用户裁定）——原
        # |注释−GZECE|>2° 即 viol 登记；现注释值只参与产状点出站
        # 走滑钩对互验（2026-10-01 空间识别通道落地）：钩对随实体消费——
        # 走滑语义段：旋向×运动学期望互证；非走滑语义段携带钩对：张力如实
        # 登记（奥 F002 推覆码×左行钩案——保守边界不自动升格复合）
        _hps = hook_by_seg.get(int(row.get("_src_id", idx)), [])
        for _hr in _hps:
            _sense = str(_hr["sense"])
            _z = float(_hr["z"])
            checks.append(f"钩旋向 z={_z:.0f}（{_sense}，符号 "
                          f"{_hr['sym1']}/{_hr['sym2']}）")
            if exp.get("gzeld_kin") in ("左行", "右行"):
                if _sense != exp["gzeld_kin"]:
                    viol.append(f"钩旋向={_sense} 不符期望 {exp['gzeld_kin']}")
            elif "走滑" not in structural_type:
                viol.append(f"非走滑语义（{structural_type}）携带走滑钩对"
                            f"（{_sense}）——张力登记")
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

        # 复合断层升格（2026-10-01 用户建议新增，F021 案驱动）：码面走滑类
        # × aux 倾滑判别（正/逆断层产状点）同段命中 → 结构类型升格
        # 复合断层（{正|逆}-{右行|左行}）——双分量语义如实合载；原码 EXPECT
        # 互验（GZELD 运动学/钩旋向）照常执行于上，零改码。
        # 边界（保守）：逆/正码+走滑运动学（如 05 码配 103 右行）不自动升格，
        # 仍走冲突登记（码义张力求裁定）
        if (structural_type in ("右型走滑断层", "左型走滑断层", "走滑断层")
                and auxv in ("逆断层产状点", "正断层产状点")):
            _comp = "逆" if "逆" in auxv else "正"
            _sense = ("右行" if "右型" in structural_type
                      else ("左行" if "左型" in structural_type else "走滑"))
            structural_type = f"复合断层（{_comp}-{_sense}）"
            checks.append(f"复合断层（码面走滑×aux {_comp}，双分量）")

        # 判定与置信度（2026-10-01 用户裁定：MLE 标定+矛盾保留）
        if _carto:
            # 制图误差（2026-10-02 用户裁定通道，seg217 案）：整体在宿主面元
            # 内部、图面切过覆盖系制图错误——剔除，不参与活动通道
            verdict, conf = "制图误差（剔除）", 0.0
        elif adjudicated:
            verdict, conf = "裁定（覆盖库）", 1.0
        elif _fallback:
            verdict, conf = "兜底（一般断层）", 0.3
            checks.append("一般断层兜底（码义无法标定：名无语义+无辅助点语义）")
        elif viol:
            # 语义已由 MLE 标定（不阻塞管线），矛盾证据全部保留在冲突册
            verdict, conf = "标定（矛盾保留）", 0.3
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
        if _fallback:
            _fallback_rows.append(dict(
                idx=idx, fault_id=fid, GZEEB=gz, fault_name=ent_info.get(
                    "fault_name", ""), gzeld=gzeld, gzece=(dip if dip else ""),
                cover_pct=round(fc * 100),
                evidence_class=evidence_class, structural_type=structural_type,
                checks="；".join(checks)))

    # 一般断层兜底档案（2026-10-02 用户裁定）：详情记录——逐段码/名/运动学/
    # 倾角/覆盖/证据级/标定结构，供人工裁定与审计回溯
    if _fallback_rows:
        _fb_p = _outdir / f"_gzeeb_fallback_{sh.key}.csv"
        pd.DataFrame(_fallback_rows).to_csv(_fb_p, index=False,
                                            encoding="utf-8-sig")
        print(f"   一般断层兜底: {len(_fallback_rows)} 段 → {_fb_p.name}")

    # 码义未注册冲突登记（2026-10-01 MLE 修订）：段级语义已由 MLE 标定，
    # 码级语义仍待裁定——归位前 MLE 分布如实入 evidence（不猜码义）
    for _code, _segs in sorted(_unreg.items()):
        _tally = "；".join(f"{k}×{v}" for k, v in
                           sorted(_mle_raw.get(_code, {}).items(),
                                  key=lambda x: -x[1]))
        conflicts.append({
            "fault_id": "", "segs": str(_segs),
            "issue": f"GZEEB={_code} 码义未注册（{len(_segs)} 段）",
            "evidence": f"段级 MLE 标定分布：{_tally}——码级语义待裁定",
            "status": "pending_review"})
    if _unreg:
        print(f"   码义未注册: {len(_unreg)} 码 {sum(len(v) for v in _unreg.values())} 段"
              f" → 冲突册 pending")

    # ---- 活动性强先验（2026-10-02 优化定版）：识别标志=断层与第四系松散
    # 沉积物和地层的接触界线重合——**活动断层的典型识别标志（2026-10-02
    # 用户确认：「F072 是第四系松散沉积物与地层的边界一致，是活动断层的
    # 典型识别标志」）**。判据升级为**面元拓扑**（断裂落于 Q 面元
    # 与非 Q 面元公共边界；在线采样×3m 容差），免疫 gzbd 路由语义转移
    # （GZBD=10 不再遮蔽标志；seg248 案根因修复）。实体级聚合（多段加强）
    # + 单段强型（≥50% 段长且 ≥1km）+ 37 码佐证 + 制图误差跳过。
    from collections import defaultdict as _dd
    # Q2 活动先验阈值入 priors（2026-10-02 泛化审计）：与同模块
    # quaternary_rank_min/quaternary_exclude 同通道；裁定值作默认
    Q2_TOL_M = float(_priors.get("q2_tol_m", 3.0))
    Q2_MIN_OV = float(_priors.get("q2_min_ov", 150.0))   # 重合有效长度下限（m）
    Q2_STRONG_M = float(_priors.get("q2_strong_m", 1000.0))  # 单段强型下限（且 ≥50% 段长）
    Q2_LONG_M = float(_priors.get("q2_long_m", 10000.0))  # 长距离强证据下限
    # （2026-10-02 用户裁定「长距离与第四系松散沉积物边界重叠也是活动断层
    #   强证据」：单段重合 ≥本值且 ≥50% 段长 → 活动，与实体多段加强同级）
    coinc = _dd(list)        # fault_id → [(seg_idx, overlap_m, pct)]
    if quat_m is not None:
        _q_bound = quat_m.boundary
        _nq_geoms = [g for g, c in zip(_pgeoms, _pcodes)
                     if (_unit_age_rank(c) or 0) < _q_rank]  # 非 Q 侧与 Q 侧同参数（活动断层审计 2026-10-02）
        _nq_tree = STRtree(_nq_geoms) if _nq_geoms else None
        for r in rows:
            if str(r.get("verdict")) == "制图误差（剔除）":
                continue
            _si = int(r["idx"])
            _g = fl.geometry.iloc[_si]
            if _g is None or _g.is_empty or _g.geom_type != "LineString":
                continue
            fm = LineString([(c[0] * LON_M, c[1] * 111320.0)
                             for c in _g.coords])
            # 在线采样：点距 Q 边界 ≤3m 且距非 Q 面元 ≤3m → 公共边界重合
            _n_pts = max(21, int(fm.length // 500))
            _hit = 0
            for k in range(_n_pts):
                pt = fm.interpolate(fm.length * (k + 0.5) / _n_pts)
                if _q_bound.distance(pt) > Q2_TOL_M:
                    continue
                if _nq_tree is None:
                    continue
                if len(_nq_tree.query(pt.buffer(Q2_TOL_M),
                                      predicate="intersects")):
                    _hit += 1
            ov_m = fm.length * _hit / _n_pts
            if ov_m >= max(Q2_MIN_OV, 0.1 * fm.length):
                coinc[r["fault_id"]].append(
                    (_si, round(ov_m), round(ov_m / fm.length * 100)))
        for r in rows:
            hits = coinc.get(r["fault_id"], [])
            if not hits:
                continue
            own = next((m for s, m, p_ in hits if s == int(r["idx"])), 0.0)
            if own:
                r["checks"] += f"；Q-地层边界重合 {own:.0f}m"
            if len(hits) >= 2:
                r["checks"] += f"；实体 Q-地层边界重合×{len(hits)}段（活动候选）"
        n_strong = 0
        _act_conf = {}   # 活动候选冲突按实体去重（活动断层审计 2026-10-02：
                         # 原每行一条 → F001 型大实体 15 条同 segs 重复登记，
                         # 且非重合行证据呈「0m（0%段长）」误导——改实体一条，
                         # 证据列逐重合段米数/占比）
        _long_fids = {fid for fid, hits in coinc.items()
                      if any(m >= Q2_LONG_M and p_ >= 50 for _, m, p_ in hits)}
        for r in rows:
            fid = r["fault_id"]
            hits = coinc.get(fid, [])
            n = len(hits)
            own = next(((m, p_) for s, m, p_ in hits
                        if s == int(r["idx"])), (0.0, 0))
            if str(r["activity"]) == "活动":
                # 佐证只落自身重合行（行级证据语义；防他段证据抬升本行 I 档）
                if own[0] and "活动性佐证" not in r["checks"]:
                    tag = f"×{n}段" if n >= 2 else ""
                    r["checks"] += f"；活动性佐证（Q-地层边界重合{tag}）"
            elif fid in _long_fids and own[0]:
                # 长距离强证据（2026-10-02 用户裁定）：单段长距离重合与
                # 实体多段加强同级——直接标活动，不落候选待裁定
                r["activity"] = "活动"
                r["verdict"] = "标定（活动先验）"
                r["checks"] += (f"；活动性佐证（Q-地层边界重合 {own[0]:.0f}m/"
                                f"{own[1]:.0f}%段长，长距离强证据）")
                n_strong += 1
            elif n >= 2 or (own[0] >= Q2_STRONG_M and own[1] >= 50):
                _tag = ("单段强型" if n < 2 else
                        ("单段强型+实体多段" if own[0] >= Q2_STRONG_M
                         and own[1] >= 50 else "实体多段"))
                r["activity"] = f"活动候选（Q-地层边界重合{_tag}，待裁定）"
                n_strong += 1
                _act_conf[fid] = hits
        for fid, hits in _act_conf.items():
            # 实体级标签取最强证据（行序无关：任一重合段达强型即标强型）
            _strong = any(m >= Q2_STRONG_M and p_ >= 50 for _, m, p_ in hits)
            _tag2 = ("单段强型+实体多段" if _strong else "实体多段") \
                if len(hits) >= 2 else "单段强型"
            _seg_ev = "；".join(f"段{s_}: {m:.0f}m（{p_}%段长）"
                                for s_, m, p_ in hits)
            conflicts.append({
                "fault_id": fid,
                "segs": str([s_ for s_, _, _ in hits]),
                "issue": f"活动断层候选：Q-地层边界重合（{_tag2}）",
                "evidence": f"断裂与第四系松散沉积物-地层接触界线重合："
                            f"{_seg_ev}"
                            + (f"；实体 {len(hits)} 段重合"
                               if len(hits) >= 2 else ""),
                "status": "pending_review"})
        print(f"   活动性先验：重合实体 {len(coinc)} 个"
              f"（强候选 {n_strong} 段）")
    # 活动识别标志（2026-10-02 用户裁定定版）：断层与第四系松散沉积物和
    # 地层的接触界线重合——切割第四系不是识别标志（切割通道已撤销；
    # 结构检查的切割注记保留为中性证据）



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
                "ACONT": ("第四系界线重合", "活动性佐证", "Q-地层边界重合",
                          "实体 Q-地层边界重合"),  # 2026-09-28 活动性强先验；2026-10-02 活动断层审计补面元拓扑通道证据串
                "GLAC": ("入冰雪区",), "COVER": ("cover=",)}
    for r in rows:
        v = str(r["verdict"])
        # 顺序敏感：「违反（待裁定）」含"裁定"子串——先判违反
        if "制图误差" in v:
            bd = evaluate("adjudicated", adjudicated=True,
                          reasons=("制图误差剔除（用户裁定）",))
        elif "违反" in v:
            bd = evaluate("multi", fit=0.0, reasons=("违反",))
        elif "矛盾保留" in v:
            bd = evaluate("multi", "single", 1.0, counterexample_open=True,
                          reasons=("MLE 标定·矛盾保留",))
        elif "兜底" in v:
            bd = evaluate("code_read", "single", evaluated=False,
                          reasons=("一般断层兜底（码义无法标定）",))
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
