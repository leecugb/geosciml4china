"""GZEEB 断层类别三维标定（geosciml4china.calibrate 第 3 域移植，2026-09-29）。

移植自 _audit_gzeeb.py（525 行，2026-09-25 三维分层模型建成，双幅通用）：
三维正交分层（用户定调「分层并行不冲突」）——
  · 证据级别层：复合覆盖（第四系松散沉积物剔半胶结+冰雪+水体）≥90% 强推测/
    ≥50% 推测；LYGREBA001=解译；
  · 结构类型层（2026-10-02 用户抽象逻辑对齐：每个图幅的编码值地质语义
    映射依赖**自身数据空间结构模式与先验知识的回归关系**）：
      regression(数据模式, 先验知识) = argmax 投票——
      先验知识类（图幅注册表 +3 / 断层名语义 +2 / GZELD 运动学 +2）回归
      权重高于数据模式类（签名 +2 / 倾角域 +1 / 覆盖 +2 / Q 内强档 +3）；
      **aux 判别通道**（a-b-a/a-b 模式地质产状测量点——正/逆断层的编码
      标识证据，+2）单列出站；无图幅注册表时先验知识仍经名称/运动学
      通道参与回归，未收敛码落泛称+提案待裁定；+ GZELD 运动学（本幅 gzeld 码义注册表——
      英吉沙 103=左行 vs 库尔干 103=右行）+ GZECE 倾角域值 + aux 三联体
      正逆 + 走滑旋向钩 + 三类补强（推覆：地层重复探针+老盖新探针（倾向盘
      老于下盘）；复活：aux 正断层产状点+切割/控制第四系；活动：切割第四系
      +入冰雪区）；
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
    # 2026-10-02 用户裁定：推测断层可出现在第四系松散沉积物（强证据，
    # Q 内强档 +3 票）也可出现在地层——出露地层**不是否定条件**，不再设
    # cover_min 违反闸（原 2026-09-25 cover_min=50 判据废止）
    "推测断层": dict(),
    "活动断层": dict(activity=True),
    # 复合断层（2026-10-01 用户建议新增）：分析型结构语义——码面走滑类
    # （16/18/走滑）× aux 倾滑判别（正/逆）双通道同段命中升格；分量随段标注
    # （复合断层（逆-右行）等）；GeoSciML 映射预注 CGI oblique_slip_fault
    "复合断层": dict(),
}

# 应力体制映射（2026-10-03 用户裁定）：逆断层/推覆体界线→压性；
# 正断层→张性；走滑断层→剪切（左型→左行、右型→右行——
# 左/右行为剪切体制的旋向细分；复合断层含走滑分量归剪切）
_STRUCT_TO_KIN = {"逆断层": "压性", "推覆体边界": "压性",
                  "正断层": "张性",
                  "左型走滑断层": "左行", "右型走滑断层": "右行",
                  "走滑断层": "剪切", "复合断层": "剪切"}


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
    # 编码-地质语义映射表用户修改装载（2026-10-04 用户裁定：映射表允许
    # 用户修改、支持修改后再转化）——上一轮映射表的 user_semantic/
    # user_note 列在此装载并跨轮保留；消费优先级：JSON 注册表 >
    # CSV user_semantic > 签名 > MLE（注册表码与 user_semantic 并存时
    # 注册表优先并告警——建议将定稿修改迁入注册表固化）
    _user_sem, _user_kin = {}, {}
    _map_note, _kin_note = {}, {}
    _map_p = sh.root / f"code_semantics_map_{sheet}.csv"
    if _map_p.exists():
        for _, _mr in pd.read_csv(_map_p, dtype=str).iterrows():
            _c0 = str(_mr.get("GZEEB") or "").strip()
            _u0 = str(_mr.get("user_semantic") or "").strip()
            if _c0 and _u0 and _u0 not in ("nan", "None"):
                _user_sem[_c0] = norm_sem(_u0)
            _n0 = str(_mr.get("user_note") or "").strip()
            if _c0 and _n0 and _n0 not in ("nan", "None"):
                _map_note[_c0] = _n0
    _kin_map_p = sh.root / f"gzeld_semantics_map_{sheet}.csv"
    if _kin_map_p.exists():
        for _, _kr in pd.read_csv(_kin_map_p, dtype=str).iterrows():
            _c0 = str(_kr.get("GZELD") or "").strip()
            _u0 = str(_kr.get("user_semantic") or "").strip()
            if _c0 and _u0 and _u0 not in ("nan", "None"):
                _user_kin[_c0] = _u0
            _n0 = str(_kr.get("user_note") or "").strip()
            if _c0 and _n0 and _n0 not in ("nan", "None"):
                _kin_note[_c0] = _n0
    if _user_sem or _user_kin:
        print(f"   映射表用户修改载入: GZEEB {len(_user_sem)} 码 / "
              f"GZELD {len(_user_kin)} 码")
        _clash = sorted(set(_user_sem) & set(gsem))
        if _clash:
            print(f"   ⚠ user_semantic 与注册表并存（注册表优先）: "
                  f"{_clash}——建议迁入注册表固化或清空 user_semantic")

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
    from shapely.ops import unary_union
    # 半胶结第四纪沉积物剔除（2026-09-27 用户定：西域群/乌恰群等不属于
    # 第四系松散沉积物范畴——西域组 Qp1X 剔除在案；清单走 priors
    # quaternary_exclude 参数化，它幅半胶结单元码入列即生效）
    _priors = load_priors(sheet)
    _q_excl = set(_priors.get("quaternary_exclude", ["Qp1X"]))
    _q_rank = float(_priors.get("quaternary_rank_min", 1300.0))
    # Q 内强证据档（2026-10-02 用户裁定「位于第四系松散沉积物内是推测断层
    # 强证据」）：段线在 Q 并集内的比例 ≥本值 → 推测断层 +3 票（与注册
    # 先验同级权重，并列时注册先验仍胜——不翻已裁定码义）
    _q_interior_frac = float(_priors.get("q_interior_frac", 0.9))
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
    # 2026-10-03 用户裁定：取消水体线缓冲（LDLYAAE001.WL buffer）机制——
    # 水系线穿越不构成覆盖证据（F098.1 案：覆盖 19% 全为水体线缓冲，
    # 断层实为地层内断层；水体面 LDLYAAE002.WP 保留在联合内）
    cover_u = unary_union([u for u in (ice_u, quat_u) if u is not None])

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
        # b 族归一 1894（auxchain 正典化同构——英吉沙 1851 也归一）
        for _, ar in asc[asc["sub_no"].isin(["1894"])].iterrows():
            try:
                sg_i, da_f = int(float(ar.get("seg_idx"))), float(ar.get("dip_az"))
            except (TypeError, ValueError):
                continue
            if da_f == da_f:
                seg_dipaz.setdefault(sg_i, da_f)

    def _sides_units(fm, probe=300.0):
        """米制线两侧单元 {code: (age_rank, hits)}（+n/−n 两侧，7 点探针）。
        2026-10-02 增强：计命中数——主导单元（最多命中）的 rank 判老盖新，
        避免混合侧被零星年轻单元（max 口径）误导（F012 案：C 主导侧混 K2k）。"""
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
            # 法向归一化（同 _hw_fw_ranks 修复——偏移恒=probe）
            _nml = float(_np.hypot(nm[0], nm[1]))
            if _nml < 1e-12:
                continue
            nm = nm / _nml
            for sgn, acc in ((1, left), (-1, right)):
                q = Point(p[0] + sgn * nm[0] * probe,
                          p[1] + sgn * nm[1] * probe)
                ii = _ptree.query(q, predicate="intersects")
                if len(ii):
                    _c0 = _pcodes[ii[0]]
                    _r0 = _pages[ii[0]]
                    _prev = acc.get(_c0, (_r0, 0))
                    acc[_c0] = (_r0, _prev[1] + 1)
        return left, right

    def _hw_fw_ranks(fm, da, probe=100.0):
        """倾向方位 → (上盘主导 rank, 下盘主导 rank)——沿线局部法向探针
        （2026-10-02 F012 案：弦向法向出图外致侧别失判——弧形/图缘断层
        按逐点局部法向与倾向方位点积定盘侧）。"""
        import numpy as _np
        total = fm.length
        if total < 1e-9:
            return None, None
        coords = _np.array(fm.coords)
        sl = _np.sqrt(((_np.diff(coords, axis=0)) ** 2).sum(axis=1))
        cum = _np.concatenate([[0], _np.cumsum(sl)])
        dx, dy = math.sin(math.radians(da)), math.cos(math.radians(da))
        hw, fw = {}, {}
        for k in range(7):
            d = total * (k + 0.5) / 7
            j = max(0, min(int(_np.searchsorted(cum, d)) - 1, len(coords) - 2))
            if sl[j] < 1e-10:
                continue
            t = (d - cum[j]) / sl[j]
            p = coords[j] * (1 - t) + coords[j + 1] * t
            tg = coords[j + 1] - coords[j]
            nm = _np.array([-tg[1], tg[0]])
            # 法向归一化（2026-10-03 F090.1 幻影老盖新案修复：原未归一
            # 致探针偏移=段长×probe（58–621m 段→5.8–62km 幻影偏移，
            # 探针落数公里外面元产幻影老盖新）；归一后偏移恒=probe
            _nml = float(_np.hypot(nm[0], nm[1]))
            if _nml < 1e-12:
                continue
            nm = nm / _nml
            sgn_hw = 1 if (dx * nm[0] + dy * nm[1]) > 0 else -1
            for sgn, acc in ((sgn_hw, hw), (-sgn_hw, fw)):
                q = Point(p[0] + sgn * nm[0] * probe,
                          p[1] + sgn * nm[1] * probe)
                ii = _ptree.query(q, predicate="intersects")
                if len(ii):
                    _c0 = _pcodes[ii[0]]
                    _r0 = _pages[ii[0]]
                    _prev = acc.get(_c0, (_r0, 0))
                    acc[_c0] = (_r0, _prev[1] + 1)
        return _dominant_rank(hw), _dominant_rank(fw)

    def _dominant_rank(d) -> float | None:
        """两侧单元 dict 的主导单元 rank（命中最多者；并列取老者）。"""
        if not d:
            return None
        _best = max(d.items(), key=lambda kv: (kv[1][1],
                                        -(kv[1][0] if kv[1][0] is not None else 0)))
        return _best[1][0]

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
    _kin_defer = []  # 运动学期望核对推迟队列（(rows 内序号, GZELD 码, 期望)）
    _n_ev0 = {}  # 投票时刻证据数（kin 后置重评基准——不计后置注记）
    _newold = {}  # 推覆分支两侧 rank（新盖老违反后置核对的原始值，idx→(ah,af)）
    _unreg = {}  # 码义未注册聚合（2026-10-01 泛化缺口修复）：eff 码 → [段]
    _fallback_rows = []  # 一般断层兜底档案（2026-10-02 用户裁定）
    _mle_raw = defaultdict(lambda: defaultdict(int))  # 归位前 MLE 语义分布
    _prior_raw = defaultdict(lambda: defaultdict(float))  # 先验知识类票（回归构成）
    _data_raw = defaultdict(lambda: defaultdict(float))   # 数据模式类票（回归构成）
    _aux_raw = defaultdict(lambda: defaultdict(float))    # aux 判别票（a-b-a/a-b 正逆编码标识）
    _act_raw = defaultdict(lambda: defaultdict(float))    # 活动证据票（Q2 拓扑，回归第三通道）
    # ---- 界线重合预计算（2026-10-03 用户裁定：位于 Q-地层界线的断层
    # 无推测断层逻辑——埋藏通道（签名/Q 内/覆盖/边缘）不适用，界线证据
    # 直投活动断层；面元拓扑重合先于回归计算，供 MLE 投票与活动层共用）
    from collections import defaultdict as _dd
    Q2_TOL_M = float(_priors.get("q2_tol_m", 3.0))
    Q2_MIN_OV = float(_priors.get("q2_min_ov", 150.0))   # 重合有效长度下限（m）
    Q2_STRONG_M = float(_priors.get("q2_strong_m", 1000.0))  # 单段强型下限（且 ≥50% 段长）
    Q2_LONG_M = float(_priors.get("q2_long_m", 10000.0))  # 长距离强证据下限
    coinc = _dd(list)        # fault_id → [(seg_idx, overlap_m, pct)]
    _coinc_own, _coinc_tier, _long_fids = {}, {}, set()
    if quat_m is not None:
        _q_bound = quat_m.boundary
        _nq_geoms = [g for g, c in zip(_pgeoms, _pcodes)
                     if (_unit_age_rank(c) or 0) < _q_rank]  # 非 Q 侧与 Q 侧同参数（活动断层审计 2026-10-02）
        _nq_tree = STRtree(_nq_geoms) if _nq_geoms else None
        for _idx0, _row0 in fl.iterrows():
            if (ov.get(str(_idx0)) or {}).get("status") == "cartographic_error":
                continue
            _g0 = _row0.geometry
            if _g0 is None or _g0.is_empty or _g0.geom_type != "LineString":
                continue
            _fm0 = LineString([(c[0] * LON_M, c[1] * 111320.0)
                               for c in _g0.coords])
            # 在线采样：点距 Q 边界 ≤3m 且距非 Q 面元 ≤3m → 公共边界重合
            _n_pts = max(21, int(_fm0.length // 500))
            _hit = 0
            for _k in range(_n_pts):
                _pt = _fm0.interpolate(_fm0.length * (_k + 0.5) / _n_pts)
                if _q_bound.distance(_pt) > Q2_TOL_M:
                    continue
                if _nq_tree is None:
                    continue
                if len(_nq_tree.query(_pt.buffer(Q2_TOL_M),
                                      predicate="intersects")):
                    _hit += 1
            _ovm = _fm0.length * _hit / _n_pts
            if _ovm >= max(Q2_MIN_OV, 0.1 * _fm0.length):
                _si0 = int(_row0.get("_src_id", _idx0))
                _fid0 = seg2fid.get(_si0)
                if _fid0:
                    coinc[_fid0].append(
                        (_si0, round(_ovm), round(_ovm / _fm0.length * 100)))
        _long_fids = {fid for fid, hits in coinc.items()
                      if any(m >= Q2_LONG_M and p_ >= 50 for _, m, p_ in hits)}
        for _fid0, _hits0 in coinc.items():
            _n0 = len(_hits0)
            for _si0, _m0, _p0 in _hits0:
                _coinc_own[_si0] = (_m0, _p0)
                if _fid0 in _long_fids:
                    _coinc_tier[_si0] = "长距离"
                elif _n0 >= 2:
                    _coinc_tier[_si0] = "多段"
                elif _m0 >= Q2_STRONG_M and _p0 >= 50:
                    _coinc_tier[_si0] = "单段强型"
                else:
                    _coinc_tier[_si0] = "弱重合"

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
        # 界线重合闸（2026-10-03 用户裁定：Q-地层界线断层无推测断层逻辑——
        # 埋藏通道不投推测票，界线证据直投活动断层；弱重合 +2/强档 +3）
        _own_c = _coinc_own.get(int(row.get("_src_id", idx)))
        _tier_c = _coinc_tier.get(int(row.get("_src_id", idx)), "弱重合")

        # ---- MLE 语义标定（2026-10-01 用户裁定）----
        # 证据投票：注册/覆盖库语义先验 +3 / 断层名 +2 / 推测签名 +2 /
        # GZELD 运动学 +2 / GZECE 倾角域 +1 / aux 判别 +2 / 界线重合 +2~3；
        # argmax 即标定；覆盖库 adjudicated 结构裁定=绝对；并列取注册先验、
        # 无先验并列落泛称；最高票 <2 落泛称（证据不足不硬标）
        votes = defaultdict(float)
        _v_prior = defaultdict(float)   # 先验知识类票
        _v_data = defaultdict(float)    # 数据模式类票
        _v_aux = defaultdict(float)     # aux 判别票（a-b-a/a-b 产状测量点）
        if _sem_from_reg:
            votes[sem_name] += 3
            _v_prior[sem_name] += 3
        if _ns_hit:
            votes[sem_name] += 2
            _v_prior[sem_name] += 2
        if _sig_hit and _own_c is None:
            votes["推测断层"] += 2
            _v_data["推测断层"] += 2
        if str(gzeld_sem_now).startswith("压性"):
            votes["逆断层"] += 2
            _v_prior["逆断层"] += 2
            votes["推覆体边界"] += 2
            _v_prior["推覆体边界"] += 2
        elif str(gzeld_sem_now).startswith("张性"):
            votes["正断层"] += 2
            _v_prior["正断层"] += 2
        elif str(gzeld_sem_now).startswith("左行"):
            votes["左型走滑断层"] += 2
            _v_prior["左型走滑断层"] += 2
        elif str(gzeld_sem_now).startswith("右行"):
            votes["右型走滑断层"] += 2
            _v_prior["右型走滑断层"] += 2
        if dip is not None and dip > 0:
            if 25 <= dip <= 85:
                votes["逆断层"] += 1
                _v_data["逆断层"] += 1
            if 50 <= dip <= 90:
                votes["正断层"] += 1
                _v_data["正断层"] += 1
            if 0 <= dip <= 35:
                votes["推覆体边界"] += 1
                _v_data["推覆体边界"] += 1
        if auxv == "逆断层产状点":
            votes["逆断层"] += 2
            _v_aux["逆断层"] += 2
        elif auxv == "正断层产状点":
            votes["正断层"] += 2
            _v_aux["正断层"] += 2
        # 覆盖证据权重提升（2026-10-01 用户裁定）：第四系松散沉积物/冰雪区/
        # 水体中展布的断层（fc≥50%）或沿覆盖边缘段（≤1km）——编码值大概率
        # 为推测断层 +2（注册码先验 +3 仍优先，不翻已裁定码义）
        # 2026-10-02 用户裁定强档：位于第四系松散沉积物内（Q 内比例
        # ≥q_interior_frac）为推测断层强证据 +3
        _qfrac = (g.intersection(quat_u).length / g.length
                  if (quat_u is not None and g is not None
                      and not g.is_empty and g.length > 0) else 0.0)
        if _own_c is None and _qfrac >= _q_interior_frac:
            votes["推测断层"] += 3
            _v_data["推测断层"] += 3
        elif _own_c is None and fc >= 0.5:
            votes["推测断层"] += 2
            _v_data["推测断层"] += 2
        elif _own_c is None and cover_u is not None:
            try:
                _dedge0 = g.distance(cover_u.boundary) * LON_M
            except Exception:
                _dedge0 = None
            if _dedge0 is not None and _dedge0 <= 1000.0:
                votes["推测断层"] += 2
                _v_data["推测断层"] += 2
        if _own_c is not None:
            # 界线证据直投活动断层（2026-10-03 用户裁定）
            votes["活动断层"] += 2 if _tier_c == "弱重合" else 3
            _v_data["活动断层"] += 2 if _tier_c == "弱重合" else 3
        # 老盖新判据进回归（2026-10-03 用户裁定：35 码各段性质——老盖新
        # 为其最大似然语义推覆体界线的决定性证据，直投推覆体边界票；
        # 段级倾向 aux b 标定真值优先，GZECD 属性兜底（F051 案：无 aux
        # 点同构形态漏判）；已有正/逆产状点或注册逆码义者不参与）
        if auxv not in ("逆断层产状点", "正断层产状点") \
                and not (_sem_from_reg
                         and sem_name in ("逆断层", "推覆体边界")):
            _da2v = seg_dipaz.get(int(row.get("_src_id", idx)))
            _da2_from_aux = _da2v is not None
            if _da2v is None:
                try:
                    _gzd = float(row.get("GZECD") or 0)
                except (TypeError, ValueError):
                    _gzd = 0.0
                _da2v = _gzd if 0 < _gzd < 360 else None
            # 倾角闸仅约束 GZECD 兜底路径（属性倾向未经产状点验证）——
            # aux 标定路径维持 2026-10-02 判据原貌（F012 案 aux 44/46° 在案）
            if (_da2v is not None
                    and (_da2_from_aux or dip is None or dip <= 35)
                    and g is not None
                    and not g.is_empty and g.geom_type == "LineString"):
                _fmv = LineString([(c[0] * LON_M, c[1] * 111320.0)
                                   for c in g.coords])
                _ahv, _afv = _hw_fw_ranks(_fmv, _da2v)
                if _ahv is not None and _afv is not None and _ahv < _afv:
                    votes["推覆体边界"] += 3
                    _v_data["推覆体边界"] += 3
        # 走滑钩对进回归（2026-10-03 用户：解析出走滑断层码——钩旋向
        # z 算法判定的左行/右行证据直投走滑票；16 码×GZELD=103×左行钩）
        _hps0 = hook_by_seg.get(int(row.get("_src_id", idx)), [])
        if _hps0:
            _sense0 = str(_hps0[0].get("sense") or "")
            if _sense0 == "左行":
                votes["左型走滑断层"] += 3
                _v_data["左型走滑断层"] += 3
            elif _sense0 == "右行":
                votes["右型走滑断层"] += 3
                _v_data["右型走滑断层"] += 3
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
        # 逐键累加（2026-10-03 修复：dict.update 覆盖同键仅留末段票面，
        # 提案表 prior/aux/data 列聚合失真——37 案 data=推测×2 实为
        # F064.1 末段票面；mle/activity 两列本为 += 不受影响）
        for _k0, _v0 in _v_prior.items():
            _prior_raw[gz][_k0] += _v0
        for _k0, _v0 in _v_data.items():
            _data_raw[gz][_k0] += _v0
        for _k0, _v0 in _v_aux.items():
            _aux_raw[gz][_k0] += _v0
        # 一般断层兜底（2026-10-02 用户裁定）：码义无法标定——注册表未命中、
        # 断层名不蕴含地质语义、无辅助点呈现的地质语义（签名/MLE 均空）——
        # 统一归入一般断层，保障管线运转；详情入 _gzeeb_fallback_<key>.csv
        _fallback = (not sem_entry and not _ns_hit and not _sig_hit
                     and not adjudicated and _mle_sem == "断层泛称")

        # 2026-09-26 三维分层归位：推测断层属**证据级别层**而非结构类型层
        # ——结构层落「断层泛称」，证据层标「推测」；exp 按 MLE 标定语义取
        exp_name = _mle_sem
        if _mle_sem == "推测断层" and structural_type is None:
            if (_sem_from_reg or _qfrac >= _q_interior_frac or fc >= 0.5):
                # 2026-10-03 用户裁定：推测断层的标定有强证据即可标定，
                # 不需要依赖人工裁定——强证据=码义注册继承 / Q 内强档 /
                # 覆盖强证据（fc≥50%）；其余（仅签名等弱证据）落泛称
                structural_type = "推测断层"
            else:
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
        if _qfrac >= _q_interior_frac:
            checks.append(f"位于第四系松散沉积物内 {_qfrac * 100:.0f}%"
                          f"——推测断层强证据")
        if _ns_hit:
            checks.append(f"断层名性质优先（{_ns_hit}→{sem_name}）")
        if _sig_hit:
            checks.append("推测断层签名（未注册码：全段无实测倾角+覆盖支撑≥2段）")
        if exp.get("gzeld_kin"):
            # 运动学期望核对后置（2026-10-03 用户裁定：GZEEB 与 GZELD 具有
            # 成因联系——GZEEB 标定后，GZELD 由 GZEEB×GZELD 统计关系推导
            # 标定；期望核对用「注册 ∪ 推导」语义在 GZEEB 定稿后统一执行，
            # 见后处理 _gzeld_derive 段）
            _kin_defer.append((len(rows), str(gzeld), str(exp["gzeld_kin"])))
        if exp.get("dip") and dip is not None and dip > 0:
            lo, hi = exp["dip"]
            checks.append(f"dip={dip:.0f}°")
            # 违反登记后置（2026-10-04 用户裁定：类别编码值拥有最高优先级
            # ——期望核对对**继承后终态语义**统一执行；一般断层（断层泛称）
            # 兼容所有矛盾信息，循环内只录证据不登记违反，见继承后
            # 「期望核对后置」段）
        elif exp.get("dip") and structural_type == "推测断层":
            pass
        # aux 三元组正逆
        if exp.get("aux") and auxv:
            checks.append(f"aux={auxv}")
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
                pass  # 钩旋向×运动学期望违反——后置核对（终态语义）
            elif "走滑" not in structural_type:
                pass  # 非走滑语义携带钩对——后置核对（终态语义）
        # ---- 三类自支持补强（2026-09-26 用户定：复活/推覆/活动判别依据不足补强） ----
        _fm = LineString([(c[0] * LON_M, c[1] * 111320.0) for c in g.coords])
        if structural_type == "推覆体边界":
            _L, _R = _sides_units(_fm)
            if _L and _R:
                _rep = set(_L) & set(_R)
                if _rep:
                    checks.append(f"地层重复({'/'.join(sorted(_rep))}，推覆重复)")
                _da = seg_dipaz.get(int(row.get("_src_id", idx)))
                _aL = _dominant_rank(_L)
                _aR = _dominant_rank(_R)
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
                        _newold[int(row.get("_src_id", idx))] = (_ah, _af)
                        # age_rank 越大越年轻——老盖新（推覆）= 倾向盘 rank 更小
                        if _ah < _af:
                            checks.append(f"老盖新（倾向盘 {_ah} 老于下盘 {_af}）")
                        # 新盖老违反——后置核对（终态语义=推覆体边界时才成立）
                        # _ah == _af：同龄不判
                elif _aL and _aR and abs(_aL - _aR) >= 200:
                    checks.append(f"新老差显著（{_aL}|{_aR}，倾向未定）")
        elif structural_type not in ("逆断层", "推覆体边界", "正断层",
                                    "左型走滑断层", "右型走滑断层", "走滑断层",
                                    "复合断层"):
            # 2026-10-02 用户裁定：判定正/逆编码值后，上盘老下盘新的、
            # 与逆断层编码值不同的断层可能为推覆体界线——老盖新判据
            # （2026-10-03 泛化：GZECD 属性倾角兜底，倾角闸仅约束兜底
            # 路径——aux 标定路径维持判据原貌，与回归票通道同口径）
            _da2 = seg_dipaz.get(int(row.get("_src_id", idx)))
            _da2_from_aux = _da2 is not None
            if _da2 is None:
                try:
                    _gzd2 = float(row.get("GZECD") or 0)
                except (TypeError, ValueError):
                    _gzd2 = 0.0
                _da2 = _gzd2 if 0 < _gzd2 < 360 else None
            if _da2 is not None and (_da2_from_aux or dip is None or dip <= 35):
                _ah2, _af2 = _hw_fw_ranks(_fm, _da2)
                if (_ah2 is not None and _af2 is not None
                        and _ah2 < _af2):
                    structural_type = "推覆体边界"
                    checks.append(f"老盖新（倾向盘 {_ah2:.0f} 老于下盘 "
                                  f"{_af2:.0f}，与逆断层编码值不同"
                                  f"——推覆体界线判据）")
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
        n_ev = 0  # 行初始化（防跨行残留——非 else 分支行继承上一行
        # n_ev 致 verified 重评虚增，2026-10-03 修复）
        if _carto:
            # 制图误差（2026-10-02 用户裁定通道，seg217 案）：整体在宿主面元
            # 内部、图面切过覆盖系制图错误——剔除，不参与活动通道
            verdict, conf = "制图误差（剔除）", 0.0
        elif adjudicated:
            verdict, conf = "裁定（覆盖库）", 1.0
        elif _fallback and structural_type == "断层泛称":
            verdict, conf = "兜底（一般断层）", 0.3
            checks.append("一般断层兜底（码义无法标定：名无语义+无辅助点语义）")
        elif _fallback:
            # 兜底判定后结构层经后置判据升级（老盖新/复合等）——
            # verdict 随最终结构层联动，不残留「兜底+非泛称」脱节
            verdict, conf = "consistent", 0.6
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
        _n_ev0[idx] = n_ev
        rows.append(dict(
            idx=idx, fault_id=fid, GZEEB=gz, gzeeb_eff=eff,
            structural_type=structural_type, evidence_class=evidence_class,
            activity=activity, GZELD=gzeld, gzeld_sem=gzeld_sem_now,
            GZECE=dip if dip is not None else None, cover_pct=round(fc * 100),
            checks="；".join(checks), verdict=verdict, confidence=conf,
            **ent_info))
        if _fallback and structural_type == "断层泛称":
            _fallback_rows.append(dict(
                idx=idx, fault_id=fid, GZEEB=gz, fault_name=ent_info.get(
                    "fault_name", ""), gzeld=gzeld, gzece=(dip if dip else ""),
                cover_pct=round(fc * 100),
                evidence_class=evidence_class, structural_type=structural_type,
                checks="；".join(checks)))

    # ---- 活动性强先验（2026-10-02 优化定版）：识别标志=断层与第四系松散
    # 沉积物和地层的接触界线重合——**活动断层的典型识别标志（2026-10-02
    # 用户确认：「F072 是第四系松散沉积物与地层的边界一致，是活动断层的
    # 典型识别标志」）**。判据为**面元拓扑**（断裂落于 Q 面元与非 Q 面元
    # 公共边界；在线采样×3m 容差），免疫 gzbd 路由语义转移（GZBD=10 不再
    # 遮蔽标志；seg248 案根因修复）。实体级聚合（多段加强）+ 单段强型
    # （≥50% 段长且 ≥1km）+ 长距离档 + 制图误差跳过。
    # 2026-10-03 用户裁定：重合采样与阈值已前置到回归前预计算——界线证据
    # 同时进入 MLE 投票（活动断层票）与本活动层标注；此处只做活动层落笔。
    if quat_m is not None:
        for r in rows:
            hits = coinc.get(r["fault_id"], [])
            if not hits:
                continue
            own = next((m for s, m, p_ in hits if s == int(r["idx"])), 0.0)
            if own:
                r["checks"] += f"；Q-地层边界重合 {own:.0f}m"
            if len(hits) >= 2:
                r["checks"] += f"；实体 Q-地层边界重合×{len(hits)}段"
        n_strong = 0

        def _mark_activity(r, own, tag):
            """活动层强证据自动标定（2026-10-02/03 用户裁定）：长距离/
            多段/单段强型接触界线重合 → activity=活动 + 结构层=活动断层
            （仅当原结构语义为泛称/推测——推覆体边界、正/逆/走滑等更强
            结构语义与覆盖库裁定不被覆盖；证据层保留推测/泛称原貌）。"""
            r["activity"] = "活动"
            r["verdict"] = "标定（活动先验）"
            if r.get("structural_type") in ("断层泛称", "推测断层"):
                r["structural_type"] = "活动断层"
            r["checks"] += (f"；活动性佐证（Q-地层边界重合 {own[0]:.0f}m/"
                            f"{own[1]:.0f}%段长，{tag}）")

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
                # 长距离强证据（2026-10-02 用户裁定）：单段长距离重合——
                # 直接标活动，不落候选待裁定
                _mark_activity(r, own, "长距离强证据")
                n_strong += 1
            elif n >= 2 and own[0]:
                # 多段接触界线强证据（2026-10-02 用户裁定：F048 案——多段
                # 作为第四系松散沉积物与地层的接触界线=活动断层强证据）：
                # 直接标活动，不落候选待裁定
                _mark_activity(r, own, "多段接触界线强证据")
                n_strong += 1
            elif own[0] >= Q2_STRONG_M and own[1] >= 50:
                # 单段强型（2026-10-03 用户裁定：第四系松散沉积物与地层/
                # 侵入岩的界线=活动断层强证据——单段重合 ≥1km 且 ≥50%
                # 段长亦直接标活动，不落候选待裁定）
                _mark_activity(r, own, "单段强型")
                n_strong += 1
        print(f"   活动性先验：重合实体 {len(coinc)} 个"
              f"（强候选 {n_strong} 段）")
        # 活动证据按码聚合（回归数据通道）：多段实体=+3（强证据档）、
        # 单段强型=+2——供码义提案裁决参考（37 案：拓扑说边界、覆盖说隐伏，
        # 两通道张力如实呈现在提案里）
        for _fid0, _hits0 in coinc.items():
            _multi0 = len(_hits0) >= 2
            for _si0, _m0, _p0 in _hits0:
                _gz0 = str(fl.iloc[_si0].get("GZEEB", ""))
                if _multi0:
                    _act_raw[_gz0]["活动断层"] += 3
                elif _m0 >= Q2_STRONG_M and _p0 >= 50:
                    _act_raw[_gz0]["活动断层"] += 2
    # 码级语义逻辑判断（2026-10-03 用户）：码义 MLE 结论=各段**最终标定
    # 结构语义**（含活动通道升格）的众数——逻辑推导，非人工裁定
    # （37 案：活动断层×19 主导 → 码义=活动断层）
    _final_raw = defaultdict(lambda: defaultdict(int))
    for r in rows:
        _final_raw[str(r.get("GZEEB") or "")][
            str(r.get("structural_type") or "断层泛称")] += 1
    # 逆断层唯一码规则（2026-10-04 用户裁定——逻辑而非裁定）：逆断层
    # 语义一幅一码——按最大似然原则由逆断层段数最多的码归属（05 案）；
    # 其余码剔除逆断层候选后重估族义：正逆共存签名（压张交替=复活
    # 样式，逆×≥3 且 正×≥3）→ 活动断层（31 案）；否则按主导性门槛
    # 从剩余候选重取
    _rev_claim = max(
        (c for c in _unreg
         if sum(_final_raw.get(c, {}).values())
         and _final_raw[c].get("逆断层", 0)
         / sum(_final_raw[c].values()) >= 0.25),
        key=lambda c: _final_raw[c].get("逆断层", 0), default=None)
    _mle_sem_by_code = {}
    _gzeld_derived = {}  # GZELD 推导语义（_unreg 块内填充；映射表出站兜底引用）
    for _code in _unreg:
        _evid = {k: v for k, v in _final_raw.get(_code, {}).items()
                 if k != "断层泛称"}
        _mle_sem_by_code[_code] = "断层泛称"
        if not _evid:
            continue
        if _code == _rev_claim:
            _mle_sem_by_code[_code] = "逆断层"
            continue
        # 剔除逆断层候选（唯一码已占）
        _n_rev0 = _evid.pop("逆断层", 0)
        _n_nor0 = _evid.get("正断层", 0)
        # 正逆共存=压张交替=复活样式 → 活动断层（可比性门槛：双向
        # 计数均 ≥3 且比值 ≥0.5——31 案 9:6=0.67 成立；01 案 34:3
        # =0.09 属逆断层主导+零星反例，不构成复活签名）
        if (_n_rev0 >= 3 and _n_nor0 >= 3
                and min(_n_rev0, _n_nor0) / max(_n_rev0, _n_nor0) >= 0.5):
            _mle_sem_by_code[_code] = "活动断层"
            continue
        if _evid:
            _sem0, _n0 = max(_evid.items(), key=lambda kv: kv[1])
            # 决定性证据覆盖门槛（2026-10-03 用户裁定：01 码仅 11/131 段
            # 老盖新（8%）不足以判族义推覆体边界——族义结论要求决定性
            # 语义覆盖族内 ≥25% 段；01 落无族义，段级证据语义如实保留）
            if _n0 / sum(_final_raw.get(_code, {}).values()) >= 0.25:
                _mle_sem_by_code[_code] = _sem0
    if _rev_claim:
        print(f"   逆断层唯一码: GZEEB={_rev_claim}"
              f"（逆断层段数 {_final_raw[_rev_claim].get('逆断层', 0)} 居首）")
    # 签名通道码义接入全继承（2026-10-04 用户裁定「所有同编码要素继承」）：
    # 推测断层签名码（如 jwsss 04）不经 MLE 提案（_unreg 外），其码义
    # 同源最高优先级——弱证据段继承推测断层（泛称让位不登记）
    for _sc in _sig_infer:
        if _sc not in gsem and _sc not in _mle_sem_by_code:
            _mle_sem_by_code[_sc] = "推测断层"
    # 码义逻辑判断继承（2026-10-03 用户裁定：逻辑判断码义扩展同码全段
    # 继承是既定逻辑——mle_semantic 结论回填该码全部泛称段；决定性证据
    # 段（正/逆/走滑/推覆/活动/推测）保持证据语义，不被覆盖）
    # 码义全继承（2026-10-04 用户裁定：继承机制适用所有地质语义——
    # 一旦完成编码值的地质语义标定，同编码值**全部要素**继承相同
    # 地质语义，适用所有编码；段级语义让位码义，段级证据如实入
    # 冲突册待裁定（矛盾保持，证据不因码义消失）；覆盖库裁定段不动）
    # 类别编码值拥有最高优先级（2026-10-04 用户裁定）：继承无条件生效——
    # **含码义=断层泛称（一般断层）的码**（取代同日「无族义即段级自立」
    # 结论）：一般断层兼容所有矛盾信息，泛称继承段让位**不登记**冲突
    # （证据留 checks 备查）；具体语义继承段让位仍登记「码义全继承」
    # 段级自证留档（2026-10-04 三层逻辑定版：L1 段级标定结果在继承前
    # 固化入列——校准 CSV 上 L1（own_structural_type）与 L2/L3
    # （structural_type=码义继承终态）分层可读）
    for r in rows:
        r["own_structural_type"] = r["structural_type"]
    _n_inh = 0
    for r in rows:
        # 全继承适用所有编码（2026-10-04 用户裁定）：逻辑判断码义
        # （mle_semantic）与注册裁定码义（gsem）同源继承——注册码的
        # 段级分歧段同样让位（31 案：F029/F011 老盖新票 > 注册先验
        # 的推覆段归位活动断层，证据入册）
        _gz0 = str(r.get("GZEEB") or "")
        # 消费优先级（2026-10-04 裁定）：JSON 注册表 > CSV user_semantic >
        # MLE 逻辑判断/签名（_mle_sem_by_code 已并入签名通道码义）
        _ms0 = None
        if _gz0 in gsem:
            _e0 = gsem[_gz0]
            _ms0 = norm_sem(_e0.get("semantic", _e0.get("meaning", "")))                 if isinstance(_e0, dict) else norm_sem(_e0)
        if not _ms0:
            _ms0 = _user_sem.get(_gz0)
        if not _ms0:
            _ms0 = _mle_sem_by_code.get(_gz0)
        if not _ms0:
            continue
        if str(r.get("verdict")) == "裁定（覆盖库）":
            continue  # 覆盖库绝对
        _cur = r.get("structural_type")
        if _cur == _ms0:
            continue
        if _ms0 != "断层泛称" and _cur not in ("断层泛称", "", None):
            # 具体码义下的段级例外让位——证据入册待裁定（泛称码让位不
            # 登记：一般断层兼容所有矛盾信息，2026-10-04 用户裁定）
            conflicts.append({
                "fault_id": r["fault_id"], "segs": str(r["idx"]),
                "issue": f"GZEEB={r['GZEEB']}（{_ms0}）码义全继承",
                "evidence": (f"段级标定 {_cur} 让位码级语义（全继承）——"
                             f"段级证据（{str(r.get('checks'))[:80]}）"
                             f"如实保留待裁定"),
                "status": "pending_review"})
        r["structural_type"] = _ms0
        if _ms0 == "断层泛称":
            _note = "码义继承（断层泛称——一般断层兼容段级证据，2026-10-04 用户裁定）"
        else:
            _note = f"码义逻辑判断继承（{_ms0}，mle_semantic 全段继承）"
        if r.get("checks"):
            r["checks"] += f"；{_note}"
        else:
            r["checks"] = _note
        if str(r.get("verdict")) in ("兜底（一般断层）", "标定（矛盾保留）"):
            if str(r.get("verdict")) == "兜底（一般断层）" and r.get("checks"):
                # 兜底注记随翻牌剥离（2026-10-04 兜底审计 F151 案：码义
                # 继承翻牌后「码义无法标定」注记不再成立——注记与 verdict
                # 联动，不残留「非兜底行携带兜底注记」脱节）
                _fb_note = "一般断层兜底（码义无法标定：名无语义+无辅助点语义）"
                _parts = [p for p in str(r["checks"]).split("；")
                          if p and p != _fb_note]
                r["checks"] = "；".join(_parts)
            r["verdict"] = "consistent"
            r["confidence"] = "0.6"
        _n_inh += 1
    if _n_inh:
        print(f"   码义逻辑判断继承: {_n_inh} 段")
    # ---- 期望核对后置（2026-10-04 用户裁定：类别编码值拥有最高优先级——
    # 倾角域/aux 期望/钩旋向/新盖老等违反核对对**继承后终态语义**统一
    # 执行；一般断层（断层泛称）兼容所有矛盾信息：EXPECT[断层泛称]=∅，
    # 泛称继承段零违反登记，段级证据留 checks 备查；具体语义继承段的
    # 违反与「码义全继承」登记合并去重——一段一条）----
    _gate_conf = 0
    _conf_by_seg = {c["segs"]: c for c in conflicts
                    if str(c.get("segs") or "").isdigit()}
    for r in rows:
        if str(r.get("verdict")) in ("裁定（覆盖库）", "制图误差（剔除）"):
            continue
        _fin = str(r.get("structural_type") or "断层泛称")
        if _fin == "断层泛称":
            continue  # 一般断层兼容一切（2026-10-04 用户裁定）
        _exp2 = EXPECT.get(_fin) or EXPECT.get(
            re.sub(r"[（(].*?[)）]", "", _fin), {})
        _v2 = []
        try:
            _dip2 = float(r.get("GZECE"))
            if _dip2 <= 0:
                _dip2 = None
        except (TypeError, ValueError):
            _dip2 = None
        if _exp2.get("dip") and _dip2 is not None:
            _lo2, _hi2 = _exp2["dip"]
            if not (_lo2 <= _dip2 <= _hi2):
                _v2.append(f"dip={_dip2:.0f}° 超期望 [{_lo2},{_hi2}]°")
        _av2 = str(r.get("aux_verdict") or "").strip()
        if _av2 in ("nan", "None"):
            _av2 = ""
        if _exp2.get("aux") and _av2:
            if _av2 == "混合判别（交检核）":
                _v2.append("aux=混合判别（交检核）")
            elif _av2 != _exp2["aux"]:
                _v2.append(f"aux={_av2} 不符期望 {_exp2['aux']}")
        for _hr2 in hook_by_seg.get(int(r["idx"]), []):
            _s2 = str(_hr2["sense"])
            if _exp2.get("gzeld_kin") in ("左行", "右行"):
                if _s2 != _exp2["gzeld_kin"]:
                    _v2.append(f"钩旋向={_s2} 不符期望 {_exp2['gzeld_kin']}")
            elif "走滑" not in _fin and "复合" not in _fin:
                _v2.append(f"非走滑语义（{_fin}）携带走滑钩对"
                           f"（{_s2}）——张力登记")
        if _fin == "推覆体边界" and int(r["idx"]) in _newold:
            _ah2, _af2 = _newold[int(r["idx"])]
            if _ah2 > _af2:
                _v2.append(f"新盖老（倾向盘 {_ah2} 新于下盘 {_af2}），"
                           f"不符推覆期望（或 dip_az 反置待核）")
        if not _v2:
            continue
        _ev2 = "；".join(_v2)
        _ck = _conf_by_seg.get(str(r["idx"]))
        if _ck is not None:
            # 与「码义全继承」登记合并（一段一条，2026-10-04 去重裁定）
            _ck["evidence"] += f"；{_ev2}"
        else:
            conflicts.append({
                "fault_id": r["fault_id"], "segs": str(r["idx"]),
                "issue": f"GZEEB={r['GZEEB']}({_fin}) 证据冲突",
                "evidence": _ev2, "status": "pending_review"})
            _conf_by_seg[str(r["idx"])] = conflicts[-1]
        if str(r.get("verdict")) not in ("兜底（一般断层）", "标定（活动先验）",
                                         "裁定（覆盖库）", "制图误差（剔除）"):
            r["verdict"] = "标定（矛盾保留）"
            r["confidence"] = "0.3"
        _gate_conf += 1
    if _gate_conf:
        print(f"   期望核对后置（终态语义）: {_gate_conf} 条")
    # 无族义码全段归一般断层（2026-10-03 用户裁定：F106.1 案——「一旦完成
    # 标定相同编码值的要素继承该地质语义」，无族义码（mle_semantic=断层
    # 泛称）的段级证据一律让位码级语义：全部段=断层泛称；段级证据如实
    # 入冲突册待裁定（证据不因码义消失）；覆盖库裁定段不动）——
    # 2026-10-04 用户裁定升级：该通道已由「类别编码值拥有最高优先级」
    # 全继承取代（泛称继承不登记冲突——一般断层兼容所有矛盾信息；段级
    # 证据语义不再自立）

    # 继承后重算最终分布（提案表 final_distribution 反映继承结果）
    _final_raw = defaultdict(lambda: defaultdict(int))
    for r in rows:
        _final_raw[str(r.get("GZEEB") or "")][
            str(r.get("structural_type") or "断层泛称")] += 1
    # 一般断层兜底档案（2026-10-02 用户裁定）：详情记录——逐段码/名/运动学/
    # 倾角/覆盖/证据级/标定结构，供人工裁定与审计回溯；继承段剔除
    _fb_keep = {r["idx"] for r in rows
                if str(r.get("verdict")) == "兜底（一般断层）"}
    _fallback_rows = [x for x in _fallback_rows if x["idx"] in _fb_keep]
    if _fallback_rows:
        _fb_p = _outdir / f"_gzeeb_fallback_{sh.key}.csv"
        pd.DataFrame(_fallback_rows).to_csv(_fb_p, index=False,
                                            encoding="utf-8-sig")
        print(f"   一般断层兜底: {len(_fallback_rows)} 段 → {_fb_p.name}")
    else:
        # 继承清零后清理陈旧件（2026-10-03：原仅 if 写入——兜底归零时
        # 旧 CSV 残留 47 行被缺口报告误读）
        _fb_p = _outdir / f"_gzeeb_fallback_{sh.key}.csv"
        if _fb_p.exists():
            _fb_p.unlink()
        print("   一般断层兜底: 0 段（陈旧件已清理）")
    if _unreg:
        # ---- GZELD 码义统计推导 + 运动学期望核对（2026-10-03 用户裁定：
        # GZEEB 与 GZELD 具有成因联系——GZEEB 结构语义标定后，GZELD 由
        # GZEEB×GZELD 统计关系推导标定；注册表裁定 > 推导（不翻已裁定
        # 码义）；混合族如实声明「运动性质不明」（期望核对中性）；
        # 应力体制映射 _STRUCT_TO_KIN 见模块级定义（EXPECT 旁）----
        _gzeld_raw = defaultdict(lambda: defaultdict(int))
        for r in rows:
            _gzeld_raw[str(r.get("GZELD") or "")][
                str(r.get("structural_type") or "")] += 1
        _gzeld_derived = {}
        for _g0, _dist0 in _gzeld_raw.items():
            if not _g0 or str(gzeld_sem.get(_g0, "")):
                continue  # 注册表已裁定码义者不参与推导（不翻已裁定）
            _kins = defaultdict(int)
            for _st0, _n0 in _dist0.items():
                _k0 = _STRUCT_TO_KIN.get(_st0)
                if _k0:
                    _kins[_k0] += _n0
            if not _kins:
                continue
            _kdom, _ndom = max(_kins.items(), key=lambda kv: kv[1])
            # 主导性门槛（与 GZEEB 族义同构 ≥25%）：达标→推导码义；
            # 未达标→运动性质不明（混合族如实声明）
            _gzeld_derived[_g0] = (_kdom if _ndom / sum(_dist0.values()) >= 0.25
                                   else "运动性质不明")
        if _gzeld_derived:
            _drv_rows = []
            for _g0 in sorted(_gzeld_derived):
                _dist0 = _gzeld_raw[_g0]
                _drv_rows.append({
                    "GZELD": _g0, "segs": sum(_dist0.values()),
                    "structural_distribution": "；".join(
                        f"{k}×{v}" for k, v in sorted(_dist0.items(),
                                                     key=lambda x: -x[1])),
                    "derived_semantic": _gzeld_derived[_g0],
                    "registered": str(gzeld_sem.get(_g0, ""))})
            pd.DataFrame(_drv_rows).to_csv(
                _outdir / f"_gzeld_code_semantics_proposal_{sheet}.csv",
                index=False, encoding="utf-8-sig")
            print(f"   GZELD 码义推导: "
                  f"{ {k: v for k, v in sorted(_gzeld_derived.items())} }")
        # 运动学期望核对执行（注册 ∪ 推导语义；不明→中性「无法核对」）
        # 2026-10-04 用户裁定：期望取**继承后终态语义**（类别编码值最高
        # 优先级）——终态无运动学期望（泛称兼容/推测/活动等）即中性，
        # 循环时刻的段级期望不再沿用
        _kin_conf = 0
        for _ri, _g0, _exp_kin0 in _kin_defer:
            r = rows[_ri]
            _fin0 = str(r.get("structural_type") or "断层泛称")
            _base0 = re.sub(r"[（(].*?[)）]", "", _fin0)
            _exp_kin = (EXPECT.get(_fin0) or EXPECT.get(_base0) or {}
                        ).get("gzeld_kin") or _STRUCT_TO_KIN.get(_base0, "")
            _sem_eff = (gzeld_sem.get(_g0) or _user_kin.get(_g0)
                        or _gzeld_derived.get(_g0)
                        or _g0)
            if not _exp_kin:
                # 终态语义无运动学期望——中性注记（不核对、不计证据数）
                r["checks"] += f"；GZELD={_g0}({_sem_eff})"
                continue
            _kin_match = (str(_sem_eff).startswith(_exp_kin)
                          or (_exp_kin == "剪切"
                              and str(_sem_eff) in ("左行", "右行", "剪切")))
            if "不明" in str(_sem_eff) or _kin_match:
                r["checks"] += f"；GZELD={_g0}({_sem_eff})"
                # 核对文本计入证据数后重评 verified（投票时刻证据数
                # n_ev0 + kin 文本——不计活动/继承等后置注记）
                if str(r["verdict"]) == "consistent":
                    _n_ev = _n_ev0.get(int(r["idx"]), 0) + 1
                    if _n_ev >= 2:
                        r["verdict"] = "verified"
                        r["confidence"] = "0.9"
                    elif _n_ev == 1:
                        r["confidence"] = "0.75"
                continue
            _iv = f"GZELD={_g0}({_sem_eff}) 不符期望 {_exp_kin}"
            _ck2 = _conf_by_seg.get(str(r["idx"]))
            if _ck2 is not None:
                # 一段一条（2026-10-04 去重裁定）：并入既有登记
                _ck2["evidence"] += f"；{_iv}"
            else:
                conflicts.append({
                    "fault_id": r["fault_id"], "segs": str(r["idx"]),
                    "issue": f"GZEEB={r['GZEEB']}({r['structural_type']}) 证据冲突",
                    "evidence": _iv, "status": "pending_review"})
                _conf_by_seg[str(r["idx"])] = conflicts[-1]
            if str(r["verdict"]) not in ("兜底（一般断层）", "标定（活动先验）",
                                         "裁定（覆盖库）", "制图误差（剔除）"):
                r["verdict"] = "标定（矛盾保留）"
                r["confidence"] = "0.3"
            r["checks"] += f"；GZELD={_g0}({_sem_eff})"
            _kin_conf += 1
        if _kin_conf:
            print(f"   运动学期望冲突（推导后真实张力）: {_kin_conf} 条")

        # 码义提案出站（2026-10-02 用户对齐裁定：图幅编码语义映射依赖自身
        # 数据空间结构模式）——未注册码的归位前 MLE 分布 + 段数 = 本幅数据
        # 模式的语义提案；码义未注册冲突登记（2026-10-01 MLE 修订）：段级
        # 语义已由 MLE 标定，码级语义已由逻辑判断并全段继承——注册表待裁定
        for _code, _segs in sorted(_unreg.items()):
            _tally = "；".join(f"{k}×{v}" for k, v in
                               sorted(_mle_raw.get(_code, {}).items(),
                                      key=lambda x: -x[1]))
            conflicts.append({
                "fault_id": "", "segs": str(_segs),
                "issue": f"GZEEB={_code} 码义未注册（{len(_segs)} 段）",
                "evidence": (f"段级 MLE 标定分布：{_tally}——码级语义已由"
                             f"逻辑判断（mle_semantic="
                             f"{_mle_sem_by_code.get(_code, '断层泛称')}）"
                             f"并全段继承；注册表待裁定"),
                "status": "pending_review"})
        print(f"   码义未注册: {len(_unreg)} 码 "
              f"{sum(len(v) for v in _unreg.values())} 段 → 冲突册 pending")
        _prop_rows = []
        for _code, _segs in sorted(_unreg.items()):
            _tally = "；".join(f"{k}×{v}" for k, v in
                               sorted(_mle_raw.get(_code, {}).items(),
                                      key=lambda x: -x[1]))
            _prior_tally = "；".join(f"{k}×{v:g}" for k, v in
                    sorted(_prior_raw.get(_code, {}).items(),
                           key=lambda x: -x[1])) if _prior_raw.get(_code) else ""
            _data_tally = "；".join(f"{k}×{v:g}" for k, v in
                    sorted(_data_raw.get(_code, {}).items(),
                           key=lambda x: -x[1])) if _data_raw.get(_code) else ""
            _act_tally = "；".join(f"{k}×{v:g}" for k, v in
                    sorted(_act_raw.get(_code, {}).items(),
                           key=lambda x: -x[1])) if _act_raw.get(_code) else ""
            _aux_tally = "；".join(f"{k}×{v:g}" for k, v in
                    sorted(_aux_raw.get(_code, {}).items(),
                           key=lambda x: -x[1])) if _aux_raw.get(_code) else ""
            _final_tally = "；".join(f"{k}×{v}" for k, v in
                    sorted(_final_raw.get(_code, {}).items(),
                           key=lambda x: -x[1]))
            # 码级 MLE 结论（2026-10-03 用户裁定）：决定性证据主导——最终
            # 标定语义中剔除无证据的泛称后取众数（35 案：老盖新×5 →
            # 推覆体边界；37 案：界线强档×19 → 活动断层）；结论已全段继承
            _prop_rows.append({"GZEEB": _code, "segs": len(_segs),
                               "mle_distribution": _tally,
                               "final_distribution": _final_tally,
                               "mle_semantic": _mle_sem_by_code.get(
                                   _code, "断层泛称"),
                               "prior_votes": _prior_tally,
                               "aux_votes": _aux_tally,
                               "data_votes": _data_tally,
                               "activity_votes": _act_tally})
        pd.DataFrame(_prop_rows).to_csv(
            _outdir / f"_gzeeb_code_semantics_proposal_{sheet}.csv",
            index=False, encoding="utf-8-sig")

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

    # ---- 编码-地质语义映射表出站（2026-10-04 用户裁定：给出清晰完整的
    # 编码-地质语义映射表，允许用户修改，支持修改后再转化）——全码一表：
    # semantic=当前生效码义（JSON 注册表>user_semantic>签名>MLE 同源
    # 继承口径）；user_semantic/user_note 为用户修改列（本轮装载值带回，
    # 编辑跨轮保留）。confidence=裁定分诊分级（2026-10-04 评估报告高
    # 优先级项：强证=≥20段且有效证据≥50%；中证=≥10段或有效≥25%；
    # 薄证=其余；有效=own 分布中剔除泛称/推测的决定性证据段）；
    # evidence_votes=纯证据票仓（aux/data/act 三通道——剔除注册先验票，
    # 消除先验回声/伪互证读表风险）。修改-再转化回路：编辑本表 → 重跑
    # calibrate-gzeeb（编辑生效）→ pipeline --skip-convert
    # --skip-calibrate-stages ----
    _own_dist = defaultdict(lambda: defaultdict(int))
    for r in rows:
        _own_dist[str(r.get("GZEEB") or "")][
            str(r.get("own_structural_type") or "断层泛称")] += 1

    def _conf_of(_c0, _src0, _n0):
        """裁定分诊分级：注册/用户/签名/无族义各标；MLE 逻辑判断按
        证据厚度分级（own 分布有效证据占比×段数）。"""
        if _src0 == "注册表":
            return "裁定固化"
        if _src0 == "用户修改":
            return "用户修改"
        if _src0 == "签名":
            return "签名码型"
        if _src0 == "MLE无族义(泛称)":
            return "无族义(兜底)"
        _dd = _own_dist.get(_c0, {})
        _dec = sum(v for k, v in _dd.items()
                   if k not in ("断层泛称", "推测断层"))
        _ratio = _dec / _n0 if _n0 else 0.0
        if _n0 >= 20 and _ratio >= 0.5:
            return f"强证({_n0}段·{_ratio * 100:.0f}%有效)"
        if _n0 >= 10 or (_n0 >= 5 and _ratio >= 0.25):
            return f"中证({_n0}段·{_ratio * 100:.0f}%有效)"
        return f"薄证({_n0}段·{_ratio * 100:.0f}%有效)"

    def _evotes(_c0):
        """纯证据票仓（剔除注册先验）：aux/data/act 三通道分组。"""
        _parts = []
        for _pre, _dd in (("aux", _aux_raw), ("data", _data_raw),
                          ("act", _act_raw)):
            _tt = "、".join(f"{k}×{v:g}" for k, v in sorted(
                _dd.get(_c0, {}).items(), key=lambda x: -x[1]))
            if _tt:
                _parts.append(f"{_pre}：{_tt}")
        return "；".join(_parts)

    _map_rows = []
    for _c0 in sorted({str(r.get("GZEEB") or "") for r in rows} - {""}):
        _n0 = sum(1 for r in rows if str(r.get("GZEEB") or "") == _c0)
        if _c0 in gsem:
            _e0 = gsem[_c0]
            _sem0 = norm_sem(_e0.get("semantic", _e0.get("meaning", ""))
                             if isinstance(_e0, dict) else _e0)
            _src0 = "注册表"
        elif _c0 in _user_sem:
            _sem0, _src0 = _user_sem[_c0], "用户修改"
        elif _c0 in _sig_infer:
            _sem0, _src0 = "推测断层", "签名"
        else:
            _sem0 = _mle_sem_by_code.get(_c0, "断层泛称")
            _src0 = ("MLE逻辑判断" if _sem0 != "断层泛称"
                     else "MLE无族义(泛称)")
        _map_rows.append({
            "GZEEB": _c0, "segs": _n0,
            "semantic": _sem0, "source": _src0,
            "confidence": _conf_of(_c0, _src0, _n0),
            "mle_distribution": "；".join(
                f"{k}×{v}" for k, v in sorted(
                    _mle_raw.get(_c0, {}).items(), key=lambda x: -x[1])),
            "final_distribution": "；".join(
                f"{k}×{v}" for k, v in sorted(
                    _final_raw.get(_c0, {}).items(), key=lambda x: -x[1])),
            "evidence_votes": _evotes(_c0),
            "user_semantic": _user_sem.get(_c0, ""),
            "user_note": _map_note.get(_c0, "")})
    pd.DataFrame(_map_rows).to_csv(_map_p, index=False, encoding="utf-8-sig")
    print(f"   编码-地质语义映射表: {len(_map_rows)} 码 → {_map_p.name}")
    _kin_rows = []
    for _g0 in sorted({str(r.get("GZELD") or "") for r in rows} - {""}):
        _dist0 = defaultdict(int)
        for r in rows:
            if str(r.get("GZELD") or "") == _g0:
                _dist0[str(r.get("structural_type") or "")] += 1
        if str(gzeld_sem.get(_g0, "")):
            _ksem0, _ksrc0 = str(gzeld_sem[_g0]), "注册表"
        elif _g0 in _user_kin:
            _ksem0, _ksrc0 = _user_kin[_g0], "用户修改"
        elif _gzeld_derived.get(_g0):
            _ksem0, _ksrc0 = _gzeld_derived[_g0], "统计推导"
        else:
            _ksem0, _ksrc0 = "运动性质不明", "未标定(默认不明)"
        _nt0 = sum(_dist0.values())
        if _ksrc0 == "统计推导":
            _share = sum(v for k, v in _dist0.items()
                       if _STRUCT_TO_KIN.get(k) == _ksem0) / _nt0
            _kconf = (f"强证({_nt0}段·{_share * 100:.0f}%)"
                      if _nt0 >= 20 and _share >= 0.5 else
                      f"中证({_nt0}段·{_share * 100:.0f}%)"
                      if _nt0 >= 10 or (_nt0 >= 5 and _share >= 0.25) else
                      f"薄证({_nt0}段·{_share * 100:.0f}%)")
        elif _ksrc0 == "注册表":
            _kconf = "裁定固化"
        elif _ksrc0 == "用户修改":
            _kconf = "用户修改"
        else:
            _kconf = "未标定"
        _kin_rows.append({
            "GZELD": _g0, "segs": _nt0,
            "semantic": _ksem0, "source": _ksrc0,
            "confidence": _kconf,
            "structural_distribution": "；".join(
                f"{k}×{v}" for k, v in sorted(
                    _dist0.items(), key=lambda x: -x[1])),
            "user_semantic": _user_kin.get(_g0, ""),
            "user_note": _kin_note.get(_g0, "")})
    pd.DataFrame(_kin_rows).to_csv(_kin_map_p, index=False,
                                   encoding="utf-8-sig")
    print(f"   GZELD 码义映射表: {len(_kin_rows)} 码 → {_kin_map_p.name}")
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
