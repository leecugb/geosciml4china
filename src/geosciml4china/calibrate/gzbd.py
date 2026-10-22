"""GZBD 地质界线先验标定（geosciml4china.calibrate 首域移植，2026-09-29）。

移植自库尔干 _audit_gzbd_pipeline.py（784 行审计优化版，英吉沙有其变体）：
  A. 贴线探针（0.0012°≈100m，7 点）取两侧单元（含冰雪覆盖面附加证据）；
  B. 先验库标定（单元对规则码级优先/名称回退、段号甄别、段间通则、第四系/
     侵入/西域组通用规则、间断通则、16 推测三检、43/60 特殊码约束、制图误差
     剔除）——verdict：标定通过/分歧/多规则分歧/未覆盖（先验缺口）/特殊码/
     断层标定/用户裁定改码/制图误差剔除；
  B2. 间断通则互证标记 + 先验缺口候选单（别名桥接）；
  B3. 特殊码兜底（2026-09-29 用户对齐裁定）：标定域外特殊类型编码统一按
      一般地质界线兜底，_gzbd_special_fallback.csv 审计存档（不进先验级联）。
      **2026-10-11 用户裁定更新：摒弃注册兜底机制——域外码改标「未解析」
      pending（无语义赋值），档案同址**
      标定域 _CALIB_DOMAIN=码表动态推导（codes_meta|用户映射）——五通道：
      ①地质志单元对先验（unit_pair_rules 码级优先/名称回退）②43 岩性过渡
      渐变先验 ③60 脉动接触先验 ④16 推测界线先验（三检）⑤通用规则级联
      （第四系/侵入/西域组/同组段间/间断通则+段间通则自支持）；

标定规则权威表述（2026-09-29 用户裁定+评估细化）：
  1. 侵入岩与地层接触，地层新、侵入岩老 → 沉积不整合接触（04 角度不整合
     约定；严格地质学近「非整合」，登记在案）；
  2. 侵入岩与地层接触，地层老、侵入岩新 → 侵入接触（11）；
  3. 同年代、同岩性岩浆岩接触，码≠侵入接触 → 岩性过渡渐变接触（43）——
     码自述+性质校验：两侧岩浆岩（侵入/火山）+希腊岩性码同+时代码同；
  4. 同年代岩浆岩接触，码≠侵入接触 → 脉动接触（60）——码自述+性质校验：
     两侧岩浆岩+时代码同（岩性不要求；60 不排斥岩性同，故 43/60 性质
     不可互分——保持校验型，性质驱动推断不可判定）；
  5. 地质界线与 FBA003 实测断层重合≥90% → 断层接触（10，路由断层域）。
  口径细化：①②的「岩浆岩」限定为「侵入岩」——火山岩与地层为互层沉积
  关系（整合/平行不整合走间断通则），不适用侵入二分；③④违反→分歧交人工，
  永不自动改码。
  C. 全项目语义解释（GZBD_eff/标定语义/状态/置信度）+ S×I×F 影子置信三列
     + 年轻侧对账（先验 younger × 年代秩）。

参数化面：图幅 root/纬度（pymapgis 剖面 center_lat_hint）、先验库
（calibrate.priors.load_priors 包数据区域主本+图幅扩展册）、gzbd_overrides
（图幅侧 data/ 优先，缺省=空注册）、gzbd_codes/xinjiang_stratigraphic_contacts
（包数据）、输出目录（默认图幅 root，影子验证可指他处）。
库尔干四表逐字节复现为准入闸。

CLI: python -m geosciml4china.calibrate.gzbd --sheet <key> [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point  # LineString：G1 断层重合度（2026-09-29）
from shapely.strtree import STRtree
from shapely.ops import unary_union as _unary_union
import os as _os

# pymapgis 完整地质栈导入守卫（2026-10-04 CI 泛化：PyPI mapgis2shp 仅含
# 极简读取器——semantics/rendering 子包未发布；缺席时绑定 None 使模块
# import 安全（CI 冒烟可收集），执行路径首用自然报错；完整栈在场行为不变）
try:
    from pymapgis.semantics import load_source_layer
    from pymapgis.semantics.profile import get_profile
    from pymapgis.rendering.pdf_writer import _unit_age_rank
except ModuleNotFoundError:  # PyPI-minimal 环境
    load_source_layer = get_profile = _unit_age_rank = None

from ..data import data_path
from ..sheets import get_sheet
from .priors import load_priors


# 段号中文字典 + 名称段式解析器（模块级，2026-09-29 用户要求：
# 解析「路乐河组二段」类地层名称；嵌套标定器经薄别名复用）
_SEG_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9}


def name_segment(name: str):
    """名称段式解析：「路乐河组二段」→ (路乐河组, 2)；「第X段」同（第 前缀可选）；
    「X组下段/下岩段」→ (X组, -1) 相对下、「中段/中岩段」→ -2、「上段/上岩段」
    → -3 相对上（相对序 -1<-2<-3）；非段式→None。须含 组/群（防「黄河一段」
    类误解析）。2026-09-29 审计补：中段与第X段（英吉沙库尔良群中段×3、
    奥依亚依拉克群鸭湖组第二段×1 实测在案）。"""
    t = str(name or "").strip()
    m = re.match(r"^(.*?[组群])第?([一二三四五六七八九])段$", t)
    if m:
        return (m.group(1), _SEG_CN[m.group(2)])
    m = re.match(r"^(.*?[组群])(下|中|上)(?:岩)?段$", t)
    if m:
        # 相对段编码与绝对段号同向：数值大=新（下=-3<中=-2<上=-1）
        # （2026-09-29 审计：新老原则执行要求年轻侧=数值大者侧，双体系共用一式）
        return (m.group(1), {"下": -3, "中": -2, "上": -1}[m.group(2)])
    return None


def _find_sheet_file(sh, name: str):
    """图幅侧登记册解析：root/data 优先、root 兜底；缺→None。"""
    for base in (sh.root / "data", sh.root):
        p = base / name
        if p.exists():
            return p
    return None


# ---- QDUECD 字段兜底通道（2026-10-04 用户裁定「直接从侵入岩的字段读取
# 对应岩性」）：代号希腊字母前缀不可靠（西里尔 г=γ 误录、∑ 数学符变体
# ——奥依亚依拉克 →гC-P=未分花岗岩 37 面元、→∑=超基性岩 11 面元实证），
# QDUECD 地质单元名称字段自带岩性与时代文本。码解析失败时逐级兜底：
# ①剥非 ASCII 前缀再解析时代后缀（гC-P→C-P 可解）②名称时代词③名称岩性词。
_ERA_NAMES = (
    ("全新世", 1340.0), ("全新统", 1340.0),
    ("更新世", 1320.0), ("更新统", 1320.0), ("第四系", 1300.0),
    ("新近纪", 1200.0), ("新近系", 1200.0),
    ("古近纪", 1100.0), ("古近系", 1100.0),
    ("白垩纪", 1000.0), ("白垩系", 1000.0),
    ("侏罗纪", 900.0), ("侏罗系", 900.0),
    ("三叠纪", 800.0), ("三叠系", 800.0),
    ("二叠纪", 700.0), ("二叠系", 700.0),
    ("石炭纪", 600.0), ("石炭系", 600.0),
    ("泥盆纪", 500.0), ("泥盆系", 500.0),
    ("志留纪", 400.0), ("志留系", 400.0),
    ("奥陶纪", 300.0), ("奥陶系", 300.0),
)
_LITH_NAMES = ("花岗闪长岩", "石英闪长岩", "二长花岗岩", "碱长花岗岩",
               "黑云母花岗岩", "花岗斑岩", "辉绿岩", "辉长岩", "闪长岩",
               "花岗岩", "超基性岩")  # 长词优先（防「花岗岩」截断「花岗闪长岩」）


def _era_from_name(name: str):
    """名称字段时代词 → 时代级别（与 _ERA_TOKENS 同基数）；无→None。"""
    for kw, r in _ERA_NAMES:
        if kw in str(name or ""):
            return r
    return None


def _lith_from_name(name: str):
    """名称字段岩性词；无→''。"""
    t = str(name or "")
    for kw in _LITH_NAMES:
        if kw in t:
            return kw
    return ""


def _era_suffix_of(code: str) -> str:
    """剥希腊/西里尔/数学符前缀后的拉丁时代后缀（43/60 时代一致比较用）。"""
    return re.sub(r"[^A-Za-z0-9\-]+", "", str(code))


def _refine_unconformity(gz, cname):
    """不整合族级语义按码细化（2026-10-14 用户裁定「codebook 应对两种
    不整合进行区分」）：04→角度不整合、24→平行不整合；其它码/语义原样
    （非 04/24 码保持族级=发现通道语义）。"""
    if cname == "不整合接触":
        return {"04": "角度不整合", "24": "平行不整合"}.get(str(gz), cname)
    return cname


def _missing_stage_gap(ages: list[float]) -> bool:
    """跨系缺失整统=显著沉积间断（2026-10-14 用户裁定，D1↔C2 中间缺失
    C1 案）：两侧属相邻系（系带差=1）且中间至少缺失一个整统——即非
    「下伏=系顶阶（3）∧ 上覆=系底阶（1）」的完美叠置。示例：D1↔C2 缺
    C1+D2+D3 三统（真）；D3↔C1 零缺失（假，可整合）。"""
    bands = sorted({int(a // 100.0) for a in ages})
    if len(bands) < 2 or bands[-1] - bands[0] != 1:
        return False
    s_old = max(int(a) % 100 for a in ages
                if int(a // 100.0) == bands[0])
    s_young = min(int(a) % 100 for a in ages
                  if int(a // 100.0) == bands[-1])
    return not (s_old == 3 and s_young == 1)


def _age_rank_of(unit) -> float | None:
    """单元时代级别兜底链：码解析 → 剥非 ASCII 前缀再解析（г/∑ 误录变体）
    → 名称字段时代词。"""
    r = _unit_age_rank(unit["code"])
    if r is not None:
        return r
    stripped = _era_suffix_of(unit["code"])
    if stripped:
        # 字母-字母跨时代后缀（C-P/O-D2 类）取均值——与 2026-09-15
        # 跨亚统均值裁定同构（гC-P 花岗岩=650 而非 C 基 600：与 C1 围岩
        # 新老比较不失真，防「地层新侵入老」伪覆盖）
        _m = re.match(r"^([A-Za-z]+)(\d*)-([A-Za-z]+)(\d*)$", stripped)
        if _m:
            _t1 = _unit_age_rank(_m.group(1) + _m.group(2))
            _t2 = _unit_age_rank(_m.group(3) + _m.group(4))
            if _t1 is not None and _t2 is not None:
                return (_t1 + _t2) / 2.0
        r = _unit_age_rank(stripped)
        if r is not None:
            return r
    return _era_from_name(unit["name"])


def calibrate_boundaries(sheet_key: str, out_dir=None) -> dict:
    """执行 GZBD 界线先验标定，返回计数统计。out_dir 缺省=图幅 root。"""
    sh = get_sheet(sheet_key)
    _lat0 = float(get_profile(sh.key).center_lat_hint)
    from pathlib import Path as _P
    _outdir = _P(out_dir) if out_dir is not None else sh.root
    _outdir.mkdir(parents=True, exist_ok=True)  # 影子验证输出目录自建（函数化缺口补）

    def _out(name):
        return str(_outdir / name)

    def _norm_gzbd(v) -> str:
        """GZBD 码归一：空→'00'；数值→两位零填；文本→原文（2026-10-09
        新疆115 C 类 K46C001004：该幅 GZBD 直写中文语义码——字面即语义，
        独立码族登记，不改码；用户裁定方案一）。"""
        s = str(v or "").strip()
        if not s:
            return "00"
        try:
            return f"{int(float(s)):02d}"
        except ValueError:
            return s

    _os.environ.setdefault("JWD_SOURCE", "geojson")

    LON_M = 111320.0 * math.cos(math.radians(_lat0))
    LAT_M = 111320.0
    PROBE_BASE = 0.0012          # 贴线探针 ~100m（#15 校准）
    PROBE_STEPS = (0.0005, 0.0012, 0.003)  # 自适应贴线探针（≈40/100/250m，
    # 2026-10-02 用户裁定「界线两侧地质单元探针要使用合理距离，避免跳过
    # 界线两侧真实地质单元」：小距先试、命中即止——细窄真实单元不被
    # 大步长越过；全步长无地层命中才走 units_at 最近面兜底）
    PROBE_WIDEN = (0.003, 0.006)  # 兜底逐级加宽

    # ---------- 数据加载 ----------
    bounds = load_source_layer(str(sh.root), "LDZOFBA002.WL", graphic=False)

    # 图形通道票（2026-10-16 路线1：线型→接触语义接线）——界线线型经
    # pymapgis 2.4.0 全线可读（@22 u16）；注册表 line_style_semantics_
    # <key>.json {"linetype_semantics": {"16": "岩性过渡渐变界线", ...}}——
    # xj115 挖掘 ≥85% 纯度族入册（16→43 96%/17→04 87%/38→10 94%/4→10 89%/
    # 10→10 87%/110/148→10 100%），per-sheet 可改可清；默认空=零行为。
    # 图面绘制样式=制图员对接触类型的图面断言，作数据通道票 +2（消融键
    # style）；专属语义分支（重合/岩相/43/60/16 三检）上游已 continue，
    # 本票只参与通用级联票池。
    _lt_map = {}
    for _lp in (sh.root / "data" / f"line_style_semantics_{sh.key}.json",
                sh.root / f"line_style_semantics_{sh.key}.json"):
        if _lp.exists():
            try:
                _lt_map = (json.loads(_lp.read_text(encoding="utf-8"))
                           .get("linetype_semantics", {}))
            except Exception:
                _lt_map = {}
            break
    _ABLATE = frozenset(x.strip() for x in
                        os.environ.get("G4C_ABLATE", "").split(",")
                        if x.strip())
    _lt_by_src = {}
    if _lt_map:
        try:
            _bg = load_source_layer(str(sh.root), "LDZOFBA002.WL",
                                    graphic=True)
            if "linetype" in _bg.columns:
                # 位置索引（Reader 路径 geodataframe 无 _src_id 列——与
                # 标定循环 idx 回退同构；geojson 路径顺序等价）
                _lt_by_src = {i: int(b) for i, b in
                              enumerate(_bg["linetype"])}
                print(f"   线型图形通道: 注册 {len(_lt_map)} 型 / "
                      f"幅内 {len(_lt_by_src)} 界线带型")
        except Exception as _e:
            print(f"   ⚠ 图形参数装载失败（{_e}）——线型票通道跳过")

    code2name, code2layer = {}, {}
    polys = []
    for fname, tag in (("LDZOFBB001.WP", "沉积"), ("LDZOFBB003.WP", "侵入"),
                       ("LDZOFBB002.WP", "火山"), ("LDZOFBB004.WP", "变质")):
        if not (sh.root / fname).exists() and not                 (sh.root / "geojson" / "L0" / f"{fname}.geojson").exists():
            continue  # CONDITIONAL 层合法缺席（如 BB002 火山岩性岩相本幅无）
        g = load_source_layer(str(sh.root), fname, graphic=False)
        for c, n in zip(g["QDUECC"].astype(str), g["QDUECD"].astype(str)):
            code2name[c] = n.strip()
            code2layer[c] = tag
        for _, row in g.iterrows():
            if row.geometry is not None and not row.geometry.is_empty:
                polys.append((row.geometry, str(row.get("QDUECC", "")), tag))
    # 侵入岩本身属性优先通道（2026-10-04 用户裁定「优先尝试从侵入岩本身
    # 属性读取岩性信息」）：QDUEAQ 单元类型码结构化岩性分类（21=超基性/
    # 22=基性/23=中性/24=酸性类+岩石种）——映射由本幅 QDUEAQ×QDUECD
    # 对自推导（多数名决），无外部词典、跨幅自持；字段缺席幅优雅降级
    # 到名称词/希腊码通道。
    code2qdueaq, _q_votes = {}, {}
    for _fn2 in ("LDZOFBB001.WP", "LDZOFBB003.WP", "LDZOFBB002.WP",
                 "LDZOFBB004.WP"):
        _qp = sh.root / "geojson" / "L0" / f"{_fn2}.geojson"
        if not _qp.exists():
            continue
        _qg = load_source_layer(str(sh.root), _fn2, graphic=False)
        if "QDUEAQ" not in _qg.columns:
            continue
        for _c2, _q2 in zip(_qg["QDUECC"].astype(str),
                            _qg["QDUEAQ"].astype(str)):
            code2qdueaq.setdefault(_c2, _q2.strip())
            _kw2 = _lith_from_name(code2name.get(_c2, ""))
            if _kw2:
                _q_votes.setdefault(_q2.strip(), {})[_kw2] = \
                    _q_votes.setdefault(_q2.strip(), {}).get(_kw2, 0) + 1
    _lith_by_q = {q: max(votes, key=votes.get) for q, votes in _q_votes.items()}
    # 2026-09-13 seg2096 审计修复：探针单元宇宙纳入冰雪区
    # （LDLYAAE002，GB=73020）——非地层覆盖层，否则冰缘界线两侧漏判
    # import os as _os  # 模块级已导入（体内重复导入致局部遮蔽，2026-09-29 修）
    import geopandas as _gpd
    ice_g = (load_source_layer(str(sh.root), "LDLYAAE002.WP", graphic=False)
             if (sh.root / "LDLYAAE002.WP").exists() or
             (sh.root / "geojson" / "L0" / "LDLYAAE002.WP.geojson").exists()
             else _gpd.GeoDataFrame())  # 本幅无水系面→空（合法缺席）
    # G2（2026-09-29 泛化优化）：仅 GB=73020 冰雪区并入覆盖证据——新幅水系面
    # 含湖泊/水库等非冰面时不再误计；无 GB 列保持旧行为（全域并入）
    if len(ice_g) and "GB" in ice_g.columns:
        ice_g = ice_g[ice_g["GB"].astype(str) == "73020"]
    if _os.environ.get("NO_ICE") != "1":
        code2name["ICE73020"] = "冰雪区"
        code2layer["ICE73020"] = "冰雪"
        for _, row in ice_g.iterrows():
            if row.geometry is not None and not row.geometry.is_empty:
                polys.append((row.geometry, "ICE73020", "冰雪"))

    # 推测界线（GZBD=16）核定所需覆盖面（松散 Q 剔 Qp1X + 冰雪）
    from shapely.ops import unary_union as _unary_union


    poly_index = {i: p for i, p in enumerate(polys)}
    tree = STRtree([p[0] for p in polys])


    def units_at(x, y):
        """贴线探针取单元：地层面精确命中优先，空缺时最近地层面兜底；
        冰雪覆盖命中作为附加证据并入（不抢占地层单元——1475/1494/2116/2125 校准）。"""
        q = Point(x, y)
        cand = tree.query(q.buffer(PROBE_WIDEN[-1]), predicate="intersects")
        strata, ice_hit = [], []
        for idx in cand:
            g, code, tag = poly_index[idx]
            if g.contains(q) or g.touches(q):
                (ice_hit if tag == "冰雪" else strata).append((code, tag))
        if not strata:
            near = []
            for idx in cand:
                g, code, tag = poly_index[idx]
                if tag == "冰雪":
                    continue
                d = g.distance(q)
                if d <= PROBE_WIDEN[-1]:
                    near.append((d, code, tag))
            if near:
                dmin = min(d for d, _, _ in near)
                strata = [(code, tag) for d, code, tag in near if d <= dmin + 1e-9]
        return strata + ice_hit


    # ---------- 先验库 ----------
    priors = load_priors(sheet_key)  # 包数据区域主本+图幅扩展册合并
    ALIAS = priors.get("alias_map", {})
    GAPS = set(priors.get("gaps_pending", {}).get("units", []))
    GAPS = {g.split(" ")[0] for g in GAPS}  # "C2ak 艾克提克组" → C2ak
    CT2GZBD = {"整合接触": {"01"}, "平行不整合": {"24"}, "角度不整合": {"04"},
               # 2026-09-26 contact/62 案补全：断层接触映射到 10（名称命中跨段规则时不再落空集）
               "断层接触": {"10"}, "断层": {"10"}, "断裂接触": {"10"},
               "不整合接触": {"04", "24"}, "整合或平行不整合": {"01", "24"},
               "不整合或平行不整合": {"04", "24"},
               "侵入接触": {"11"}}


    def norm_name(n):
        n = re.sub(r"[一二三]段$", "", str(n).strip())
        return ALIAS.get(n, n)


    rule_index = {}
    for r in priors["unit_pair_rules"]:
        if r.get("confidence") in ("incomplete", "superseded_q_2026-09-17"):
            continue  # 空名单元规则不参与
        key = tuple(sorted(norm_name(p) for p in r["pair"]))
        rule_index.setdefault(key, []).append(r)

    _ov_p = _find_sheet_file(sh, "gzbd_overrides.json")
    overrides = (json.loads(_ov_p.read_text(encoding="utf-8")) if _ov_p else
                 {"overrides": {}, "side_overrides": {}, "cartographic_errors": {}})
    type_ov = overrides["overrides"]
    side_ov = overrides["side_overrides"]
    carto_err = overrides.get("cartographic_errors", {})
    # 编图错误噪声段（2026-10-09 T3 裁定回路）：矛盾项经用户裁定为编图
    # 错误/数据噪声——段不再走先验级联、不入冲突待裁，直接取码级裁定语义
    noise_seg = overrides.get("noise_segments", {})
    # 码级用户裁定语义预载（boundary_semantics_map 的 user_semantic 列）：
    # 噪声段分支须取码级裁定语义（注册先验泛义可能不同，如 L45C003004）
    _user_bsem_early = {}
    _bm_p0 = sh.root / f"boundary_semantics_map_{sh.key}.csv"
    if _bm_p0.exists():
        import csv as _csv0
        with open(_bm_p0, encoding="utf-8-sig") as _f0:
            for _r0 in _csv0.DictReader(_f0):
                _u0 = str(_r0.get("user_semantic") or "").strip()
                if _u0:
                    _user_bsem_early[str(_r0.get("GZBD") or "").strip()] = _u0
    codes_meta = json.loads(data_path("gzbd_codes.json").read_text(encoding="utf-8"))["codes"]

    # 码义解析器（2026-10-11 用户裁定泛化：判定条件比**码义**不比码值——
    # 「编码≠侵入接触码且≠渐变界线码」等条件按码义判定，跨编码约定通用；
    # 数值码查图幅用户裁定→注册表码义，文本码（C 类族）字面即语义）
    def _code_sem_is(c, *keywords) -> bool:
        s = str(c)
        if s.isdigit():
            m = _user_bsem_early.get(s) \
                or str(codes_meta.get(s, {}).get("meaning") or "")
        else:
            m = s
        return any(k in m for k in keywords)
    # SPECIAL_CODES 常量已撤（2026-10-11 审计：43/60 语义触发分支先行拦截，
    # 本拦截与常量死代码化——连带其 C 段注册置信通道一并移除）
    # 标定域（2026-09-29 用户对齐裁定）：域内码走五通道（地质志单元对先验/
    # 43 岩性过渡渐变/60 脉动接触/16 推测界线/通用规则级联）+10 断层标定+
    # 81 特殊码独立标定；域外码=其他特殊类型编码，统一一般地质界线兜底
    # 标定域（2026-09-29 用户对齐裁定）：域内码走五通道（地质志单元对先验/
    # 43 岩性过渡渐变/60 脉动接触/16 推测界线/通用规则级联）+10 断层标定+
    # 81 特殊码独立标定；域外码=其他特殊类型编码——2026-10-11 摒弃兜底后
    # 标「未解析」pending 不再兜底。域集改为注册表驱动（数据件，不硬编码）
    # 用户注册码进域（2026-10-14 61=脉动接触案）：码级用户裁定语义
    # （boundary_semantics_map user_semantic 列）为权威序最高级——用户给码
    # 赋义即入标定域（否则域外闸拦截、user_semantic 永不生效）
    _CALIB_DOMAIN = set(codes_meta) | set(_user_bsem_early)
    # 16 推测界线自 2026-09-13 起经专项核定（见 B 段）
    # 2026-09-13 用户对齐：第四系不含已半固结成岩的沉积层（西域组 Qp1X 算基岩）
    Q_EXCLUDE = set(priors.get("quaternary_exclude", ["Qp1X"]))
    # 2026-10-22 用户裁定：新疆群（Qp3X 全变体）入松散第四系剔除——变体码
    # 多义（Qp3l 湖相松散/Qp3Xpal 冲洪积 与新疆群同码），故按**名称**剔除
    # （子串包含，覆盖"晚更新世新疆群"等名称变体）；码剔除仅作兜底
    Q_EXCLUDE_NAMES = tuple(priors.get("quaternary_exclude_names", []))


    def clean_code(c):
        return re.sub(r"[→↓↑]", "", str(c))


    # 码级索引（2026-09-26 随码级匹配优先修复配套）：仅收录带 codes 的规则
    # （段级裁定条等），键为规范化单元码排序对；同名段级单元靠码区分相邻/跨段
    # 注意：必须在 clean_code 定义之后（函数调用发生在模块加载期）
    rule_code_index = {}
    for r in priors["unit_pair_rules"]:
        if r.get("confidence") in ("incomplete", "superseded_q_2026-09-17"):
            continue
        if r.get("codes"):
            key = tuple(sorted(clean_code(c) for c in r["codes"]))
            rule_code_index.setdefault(key, []).append(r)

    # 段级码结构：组前缀（系/统号+拼音字母）+ 末位段号（统级码无前缀字母，不匹配）
    _FORM_SEG_RE = re.compile(r"^([A-Z][a-z]?\d+(?:-\d+)?[A-Za-z]+)(\d)$")
    _name_seg = name_segment  # 模块级解析器薄别名（2026-09-29 提升，可测试）


    def _unit_seg(u):
        """单元 → (组标识, 段号)：代号直读优先（末位段号数字），
        代号无段号时名称段式回退——「白沙河组四段（Pt1bsch）」类单元
        由此获得段身份。组标识的可比性由调用方约束（代号前缀 vs 名称
        组名不混比）。"""
        k = _seg_key(u["code"])
        if k:
            return k
        return _name_seg(u["name"])


    def _seg_key(code):
        """段级单元码 → (组前缀, 段号)；非段级返回 None。"""
        m = _FORM_SEG_RE.match(clean_code(code))
        return (m.group(1), int(m.group(2))) if m else None


    def _seg_no(code):
        """段级单元码 → 段号（int）；非段级返回 None。"""
        k = _seg_key(code)
        return k[1] if k else None


    def _seg_from_name(p):
        """规则名称对 → 段号（名称以「一/二/三…段」结尾时）。"""
        s = str(p).strip()
        if s.endswith("段") and len(s) >= 2:
            return _SEG_CN.get(s[-2])
        return None


    def _rule_seg_nos(rule):
        """规则的段号对：优先其 codes，否则解析名称对尾段号。"""
        if rule.get("codes"):
            return tuple(sorted(n for n in (_seg_no(c) for c in rule["codes"])
                                if n is not None))
        return tuple(sorted(n for n in (_seg_from_name(p) for p in rule["pair"])
                            if n is not None))


    def _seg_hits_ok(rule, actual):
        """段号甄别（2026-09-26 用户定）：同名段级单元名称回退的段识别——
        ①段级规则（两端皆段号）须与实际段号对完全一致；
        ②混合规则（一端段号）其段号须在实际对中；
        ③组级规则（无段号）兜底保留。"""
        ns = _rule_seg_nos(rule)
        if len(ns) == 2:
            return ns == actual
        if len(ns) == 1:
            return ns[0] in actual
        return True

    # 装载期自检（2026-09-26 强化：索引为空/关键裁定条缺失即中止，
    # 不让空索引静默降级为全名称匹配——contact/62 案的防线）
    assert rule_index, "先验库名称索引为空"
    assert rule_code_index, "先验库码级索引为空"
    for _need in [("D3kz1", "D3kz2"), ("D3kz1", "D3kz3"), ("D3kz2", "D3kz3")]:
        assert _need in rule_code_index, f"段级裁定规则缺失 {_need}"
    print(f"先验库装载：名称键 {len(rule_index)}，码级键 {len(rule_code_index)}")


    def _group_of(name):
        """地层组名（截取到"组"）。"""
        m = re.match(r"^(.+?组)", str(name).strip())
        return m.group(1) if m else None


    def _same_group_member(lu_units, ru_units):
        """两侧存在同组不同段的单元对。
        判定：组名相同，且（段名不同 或 代号不同——成员级上标在代号中，
        如 →D↓2→kz↑1 vs →D↓2→kz↑2，名称同为"克孜勒陶组"）。"""
        for lu in lu_units:
            for ru in ru_units:
                gl, gr = _group_of(lu["name"]), _group_of(ru["name"])
                if gl and gl == gr and (lu["name"] != ru["name"]
                                        or lu["code"] != ru["code"]):
                    return True
        return False


    # 推测界线（GZBD=16）核定所需覆盖面（松散 Q 剔 Qp1X + 冰雪）
    _q_src = []
    _sg = load_source_layer(str(sh.root), "LDZOFBB001.WP", graphic=False)
    for g, c, n in zip(_sg.geometry.values,
                       _sg["QDUECC"].astype(str).values,
                       _sg["QDUECD"].astype(str).values):
        if g is not None and not g.is_empty \
                and (a := _unit_age_rank(c)) is not None and a >= 1300 \
                and clean_code(c) not in Q_EXCLUDE \
                and not any(x in n for x in Q_EXCLUDE_NAMES):
            _q_src.append(g)
    q_u = _unary_union(_q_src) if _q_src else None
    ice_u = ice_g.geometry.union_all() if len(ice_g) else None

    # ---------- A. 两侧单元探针 ----------
    sides_rows = []
    for i, row in bounds.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        coords = np.array(geom.coords)
        if len(coords) < 2:
            continue
        diffs = np.diff(coords, axis=0)
        seg_lens = np.sqrt((diffs ** 2).sum(axis=1))
        cum = np.concatenate([[0], np.cumsum(seg_lens)])
        total = cum[-1]
        if total < 1e-10:
            continue
        left_all, right_all = [], []
        for k in range(7):
            d = total * (k + 0.5) / 7
            j = max(0, min(int(np.searchsorted(cum, d)) - 1, len(coords) - 2))
            if seg_lens[j] < 1e-10:
                continue
            t = (d - cum[j]) / seg_lens[j]
            p = coords[j] * (1 - t) + coords[j + 1] * t
            tg = coords[j + 1] - coords[j]
            nm = np.array([-tg[1], tg[0]])
            for _sgn, _acc in ((1, left_all), (-1, right_all)):
                _got = None
                for _step in PROBE_STEPS:
                    _got_step = units_at(p[0] + _sgn * nm[0] * _step,
                                         p[1] + _sgn * nm[1] * _step)
                    _strata = [(c, t) for c, t in _got_step if t != "冰雪"]
                    if _strata:
                        _got = _got_step
                        break  # 最小距离地层命中即取——真实近侧单元优先
                    if _got is None and _got_step:
                        _got = _got_step  # 仅冰雪佐证记下，继续向外寻地层
                if _got is None:
                    _got = units_at(p[0] + _sgn * nm[0] * PROBE_BASE,
                                    p[1] + _sgn * nm[1] * PROBE_BASE)
                _acc += _got
        lu = sorted({c for c, _ in left_all})
        ru = sorted({c for c, _ in right_all})
        sides_rows.append({
            # 空码防御（2026-10-08 新疆115 泛化：部分图幅 GZBD 存在空值段
            # ——空码按 00 记录，后续走特殊码兜底通道，不崩溃）+ 文本码
            # 放行（2026-10-09 C 类：直写中文语义码原文保留）
            "idx": i, "gzbd": _norm_gzbd(row['GZBD']),
            "left_codes": json.dumps(lu, ensure_ascii=False),
            "right_codes": json.dumps(ru, ensure_ascii=False),
            "left_names": json.dumps([code2name.get(c, c) for c in lu], ensure_ascii=False),
            "right_names": json.dumps([code2name.get(c, c) for c in ru], ensure_ascii=False),
        })

    sides = pd.DataFrame(sides_rows)
    sides.to_csv(_out("_boundary_sides.csv"), index=False, encoding="utf-8-sig")
    print(f"A. 两侧单元探针完成：{len(sides)} 段（贴线 {PROBE_BASE}° ≈{PROBE_BASE * LON_M:.0f}m）")

    # ---------- B. 先验标定 ----------
    verdicts = []
    # G1 断层重合证据前置（2026-10-10 用户裁定：取消 GZBD=10 路由码——断层
    # 接触不再按码直给，改由界线与 LDZOFBA003 实测断层线 100m 带重合占比
    # 在级联中判定）：缓冲只算一次（A 类修复原位），全段预算供级联消费。
    # oracle 口径（2026-10-11 用户裁定）：**仅实测断层（FBA003）作证**——
    # 解译断层（LYGREBA001）/深部断层（LZLPGDJ002）不入围（从严：界线-断层
    # 重合证据只接受实测层，解译/深部层的界线重合段照常落候选/不足交裁定）
    from shapely.ops import unary_union as _uu_fault
    import geopandas as _gpd_f
    _fault_u_m = None
    _fp = sh.root / "geojson" / "L0" / "LDZOFBA003.WL.geojson"
    if _fp.exists():
        _fg = _gpd_f.read_file(_fp)
        _fgeoms = [g for g in _fg.geometry
                   if g is not None and not g.is_empty]
        if _fgeoms:
            _fault_u_m = _uu_fault([
                LineString(np.array(g.coords) * [LON_M, LAT_M])
                for g in _fgeoms])
    _fault_buf_m = (_fault_u_m.buffer(100.0)
                    if _fault_u_m is not None else None)

    def _coincidence(geom):
        """界线与 FBA003 断层线重合占比（米制 100m 缓冲）；无数据→None。"""
        if _fault_buf_m is None or geom is None or geom.is_empty:
            return None
        _cm = np.array(geom.coords)
        if len(_cm) < 2:
            return None
        _seg = LineString(_cm * [LON_M, LAT_M])
        _tot = _seg.length
        if _tot < 1e-9:
            return None
        return _seg.intersection(_fault_buf_m).length / _tot

    _coinc_all = {}
    if _fault_buf_m is not None:
        for _ci0 in range(len(bounds)):
            _coinc_all[_ci0] = _coincidence(bounds.geometry.values[_ci0])

    # 冰雪重合证据（2026-10-10 用户裁定：81 撤路由——冰雪区界线由界线与
    # LDLYAAE002 水系面层冰川面元（GB=73020）轮廓的 100m 带重合判定；
    # CONDITIONAL 层，缺席幅→未覆盖登记）。注意用面元**轮廓**缓冲（界线
    # 是冰川边线），不用填充面域（防穿越冰川内部的伪重合）
    from shapely.geometry import Polygon as _Polygon, MultiPolygon as _MultiPolygon

    def _scale_m(g):
        """面元几何米制化（np 缩放各环顶点）。"""
        if g.geom_type == "Polygon":
            return _Polygon(np.array(g.exterior.coords) * [LON_M, LAT_M],
                            [np.array(r.coords) * [LON_M, LAT_M]
                             for r in g.interiors])
        if g.geom_type == "MultiPolygon":
            return _MultiPolygon([_scale_m(p) for p in g.geoms])
        return g

    _ice_bound_buf = None
    _ip = sh.root / "geojson" / "L0" / "LDLYAAE002.WP.geojson"
    if _ip.exists():
        import geopandas as _gpd_i
        _ig = _gpd_i.read_file(_ip)
        # 面元悬挂弧缺陷提取（2026-10-16 用户裁定修复，I44C001001 案——
        # 面+悬挂线粘连成 GeometryCollection，与 build.py GC 处理器同构）：
        # 只取 Polygon/MultiPolygon 成员入 union，非面成员剔除登记
        # （面元缺陷修复闭环：不改源数据，登记交裁定）
        _ice_polys = []
        _ice_dropped = []
        for _gi, _row_i in _ig.iterrows():
            _g = _row_i.geometry
            if _g is None or _g.is_empty:
                continue
            if _g.geom_type in ("Polygon", "MultiPolygon"):
                _ice_polys.append(_g)
            elif _g.geom_type == "GeometryCollection":
                _mp = [m for m in _g.geoms
                       if m.geom_type in ("Polygon", "MultiPolygon")]
                _md = sorted({m.geom_type for m in _g.geoms}
                             - {"Polygon", "MultiPolygon"})
                if _md:
                    _ice_dropped.append({
                        "src_id": str(_row_i.get("_src_id", _gi)),
                        "dropped_members": "/".join(_md),
                        "kept_members": "/".join(sorted({m.geom_type for m in _mp})) or "无",
                    })
                _ice_polys.extend(_mp)
            else:
                _ice_dropped.append({
                    "src_id": str(_row_i.get("_src_id", _gi)),
                    "dropped_members": _g.geom_type, "kept_members": "无"})
        if _ice_dropped:
            pd.DataFrame(_ice_dropped).to_csv(
                _out(f"_gzbd_ice_dropped_{sh.key}.csv"),
                index=False, encoding="utf-8-sig")
            print(f"   冰川面元悬挂成员剔除 {len(_ice_dropped)} 例（取面元部分，"
                  f"登记 _gzbd_ice_dropped_{sh.key}.csv）")
        if _ice_polys:
            _ice_u = _uu_fault([_scale_m(g) for g in _ice_polys])
            # 2026-10-16 守卫（I44C001001 舰队重跑崩溃案修复）：冰川 union 退化
            # （GeometryCollection/空）时 .boundary 返回 None——与 gzeeb Q2 守卫
            # 同构：通道降级跳过并如实登记（面元拓扑不静默修复，交裁定）
            _ice_bnd = getattr(_ice_u, "boundary", None)
            if _ice_bnd is not None and not _ice_bnd.is_empty:
                _ice_bound_buf = _ice_bnd.buffer(100.0)
            else:
                pd.DataFrame([{
                    "sheet": sh.key,
                    "reason": "ice_union_boundary_none_or_empty",
                    "ice_geom_type": getattr(_ice_u, "geom_type", "?"),
                }]).to_csv(_out(f"_gzbd_ice_degraded_{sh.key}.csv"),
                           index=False, encoding="utf-8-sig")
                print(f"   ⚠ 冰川 union 退化（boundary=None/empty）——冰雪重合"
                      f"通道降级跳过，已登记 _gzbd_ice_degraded_{sh.key}.csv")

    def _coinc_ice_of(geom):
        """界线与 LDLYAAE002 冰川轮廓重合占比（米制）；无数据→None。"""
        if _ice_bound_buf is None or geom is None or geom.is_empty:
            return None
        _cm = np.array(geom.coords)
        if len(_cm) < 2:
            return None
        _seg = LineString(_cm * [LON_M, LAT_M])
        _tot = _seg.length
        if _tot < 1e-9:
            return None
        return _seg.intersection(_ice_bound_buf).length / _tot

    _coinc_ice = {}
    if _ice_bound_buf is not None:
        for _ci0 in range(len(bounds)):
            _coinc_ice[_ci0] = _coinc_ice_of(bounds.geometry.values[_ci0])

    # ---- 共享助手（2026-10-16 审计优化抽取：消岩相规则 × 段间通则、
    # 16 三检 × 整合反向判别的物理拷贝——防单侧修补漂移）----
    def _adjacent_seg_tri(sl, sr):
        """组内段对相邻性三态判定（段间通则/岩相规则同源实现）：
        同组异号段号 → True=相邻 / False=跨段 / None=不可判（相对×绝对
        混比、其它负数对）。中段存在性普查口径两消费方一致。"""
        if not (sl and sr and sl[0] == sr[0] and sl[1] != sr[1]):
            return None
        a, b = sl[1], sr[1]
        if a > 0 and b > 0:
            return abs(a - b) == 1
        if a < 0 and b < 0:
            ra, rb = sorted((a, b))  # 新编码：下=-3 中=-2 上=-1
            if (ra, rb) in ((-2, -1), (-3, -2)):
                return True  # 下|中 / 中|上 恒相邻
            if (ra, rb) == (-3, -1):
                # 下|上：组内中段存在性普查决定（三段式组 下|上 隔中段=
                # 跨段；两组式无中段=相邻）
                _grp = sl[0]
                _has_mid = any(str(code2name.get(c, c)) in
                               (f"{_grp}中段", f"{_grp}中岩段")
                               for c in code2name)
                return not _has_mid
        return None

    def _cov_frac8(geom):
        """Q/冰雪覆盖度 8 点采样（16 三检与整合反向判别共享）。
        覆盖证据缺省（q_u/ice_u 双 None）→ None（不误读为基岩出露）。"""
        if geom is None or geom.is_empty:
            return None
        if q_u is None and ice_u is None:
            return None
        _h = sum(1 for t in np.linspace(0.08, 0.92, 8)
                 if (q_u is not None and q_u.intersects(
                     geom.interpolate(float(t), normalized=True)))
                 or (ice_u is not None and ice_u.intersects(
                     geom.interpolate(float(t), normalized=True))))
        return _h / 8

    # 16 连接性端点表（2026-10-16 P2 优化：原 O(B²) iterrows 三重纯 Python
    # 循环 → 端点数组 numpy 向量化（米制）；语义逐点保留——同端点对命中
    # 仍按次追加（含单点折线双计原状）。惰性构建——无 16 段幅零成本。
    _ep_cache = None

    def _conn_types16(idx, geom):
        """16 连接性：两端 ≤10m 可达界线（非 16/81/10）的码列表。"""
        nonlocal _ep_cache
        if _ep_cache is None:
            _ji, _xy, _gz = [], [], []
            for _j, _row2 in bounds.iterrows():
                _g2 = _row2.geometry
                if _g2 is None or _g2.is_empty:
                    continue
                _c2 = list(_g2.coords)
                _gzv = str(_row2.get("GZBD", ""))
                for _p2 in (_c2[0], _c2[-1]):
                    _ji.append(int(_j))
                    _xy.append((_p2[0] * LON_M, _p2[1] * LAT_M))
                    _gz.append(_gzv)
            _ep_cache = (np.asarray(_ji), np.asarray(_xy, dtype=float), _gz)
        _ji, _xy, _gzs = _ep_cache
        _out = []
        _bc = list(geom.coords)
        for _pt in (_bc[0], _bc[-1]):
            _qx, _qy = _pt[0] * LON_M, _pt[1] * LAT_M
            _d = np.hypot(_xy[:, 0] - _qx, _xy[:, 1] - _qy)
            for _k in np.nonzero(_d <= 10.0)[0]:
                if int(_ji[_k]) == idx:
                    continue
                _gzc = _norm_gzbd(_gzs[_k])
                if _gzc not in ("16", "81", "10"):
                    _out.append(_gzc)
        return _out

    def _liths(us):
        """岩性集合（43/60 判定与发现通道共用）：属性字段优先（QDUEAQ
        槽），希腊字母前缀兜底——2026-10-11 由 43 分支内提升为共享。"""
        s = {u["lith"] for u in us if u.get("lith")}
        if s:
            return s
        out = set()
        for u in us:
            c = re.sub(r"[→↓↑]", "", u["code"])
            m = re.match(r"([Ͱ-Ͽἀ-῿]+)(.*)$", c)
            if m:
                out.add(m.group(1))
        return out
    for _, rec in sides.iterrows():
        gz = rec["gzbd"]
        idx = int(rec["idx"])
        lu_codes = json.loads(rec["left_codes"])
        ru_codes = json.loads(rec["right_codes"])
        lu_units = [{"code": c, "name": code2name.get(c, c), "layer": code2layer.get(c, "?"),
                     "lith": _lith_by_q.get(code2qdueaq.get(c, ""), "")
                             or _lith_from_name(code2name.get(c, c))}
                    for c in lu_codes]
        ru_units = [{"code": c, "name": code2name.get(c, c), "layer": code2layer.get(c, "?"),
                     "lith": _lith_by_q.get(code2qdueaq.get(c, ""), "")
                             or _lith_from_name(code2name.get(c, c))}
                    for c in ru_codes]
        base = {"idx": idx, "gzbd": gz,
                "left": ";".join(f"{u['code']}({u['name']})" for u in lu_units),
                "right": ";".join(f"{u['code']}({u['name']})" for u in ru_units)}
        if str(idx) in carto_err:
            verdicts.append({**base, "verdict": "制图误差（剔除）", "rule_pair": "",
                             "rule_contact": "", "rule_conf": "", "expected": "",
                             "rule_younger": "", "young_side": ""})
            continue
        # 重合规则族（2026-10-10 用户裁定：10/81 双路由撤销——断层接触/
        # 冰雪区界线均由界线与本体层实测重合证据在级联中判定；核验+发现
        # 双向）。**本码规则优先**（gz=10 先评断层、gz=81 先评冰雪），跨码
        # 高重合仅在无本码规则时登记候选——双 oracle 命中段（冰川沿断层谷
        # 走的 81 段）归本码判定，不被跨码候选劫持
        _pct10 = _coinc_all.get(idx)
        _pct81 = _coinc_ice.get(idx)
        if gz == "10" or _code_sem_is(gz, "断层"):
            if _pct10 is None:
                verdicts.append({**base, "verdict": "未覆盖",
                                 "rule_pair": "(断层重合规则:本幅无FBA003数据)",
                                 "rule_contact": "", "rule_conf": "",
                                 "expected": "", "rule_younger": "",
                                 "young_side": ""})
            elif _pct10 >= 0.9:
                verdicts.append({**base, "verdict": "标定通过",
                                 "rule_pair": f"(断层重合规则:重合{_pct10:.0%})",
                                 "rule_contact": "断层接触（断裂界线）",
                                 "rule_conf": "verified", "expected": "10",
                                 "rule_younger": "", "young_side": ""})
            else:
                verdicts.append({**base, "verdict": "重合不足（断层界线）",
                                 "rule_pair": f"(断层重合规则:重合仅{_pct10:.0%})",
                                 "rule_contact": "断层接触（断裂界线）",
                                 "rule_conf": "conflict", "expected": "10",
                                 "rule_younger": "", "young_side": ""})
            continue
        if gz == "81" or _code_sem_is(gz, "冰雪"):
            if _pct81 is None:
                verdicts.append({**base, "verdict": "未覆盖",
                                 "rule_pair": "(冰雪重合规则:本幅无LDLYAAE002数据)",
                                 "rule_contact": "", "rule_conf": "",
                                 "expected": "", "rule_younger": "",
                                 "young_side": ""})
            elif _pct81 >= 0.9:
                verdicts.append({**base, "verdict": "标定通过",
                                 "rule_pair": f"(冰雪重合规则:重合{_pct81:.0%})",
                                 "rule_contact": "冰雪区界线",
                                 "rule_conf": "verified", "expected": "81",
                                 "rule_younger": "", "young_side": ""})
            else:
                verdicts.append({**base, "verdict": "重合不足（冰雪界线）",
                                 "rule_pair": f"(冰雪重合规则:重合仅{_pct81:.0%})",
                                 "rule_contact": "冰雪区界线",
                                 "rule_conf": "conflict", "expected": "81",
                                 "rule_younger": "", "young_side": ""})
            continue
        if _pct10 is not None and _pct10 >= 0.9:
            verdicts.append({**base, "verdict": "分歧",
                             "rule_pair": f"(断层重合规则:重合{_pct10:.0%})",
                             "rule_contact": "断层接触（断裂界线）",
                             "rule_conf": "verified", "expected": "10",
                             "rule_younger": "", "young_side": ""})
            continue
        if _pct81 is not None and _pct81 >= 0.9:
            verdicts.append({**base, "verdict": "分歧",
                             "rule_pair": f"(冰雪重合规则:重合{_pct81:.0%})",
                             "rule_contact": "冰雪区界线",
                             "rule_conf": "verified", "expected": "81",
                             "rule_younger": "", "young_side": ""})
            continue
        if gz not in _CALIB_DOMAIN:
            # 特殊码兜底（2026-09-29 用户对齐裁定）：其他特殊类型编码无法使用
            # 地质语义标定逻辑处理时，统一按一般地质界线兜底，审计报告存档。
            # 必须在下游先验/通则级联之前拦截——否则域外码会被第四系/侵入
            # 通则按两侧单元误标（如未知码旁第四系被标 02）。
            verdicts.append({**base, "verdict": "特殊码兜底",
                             "rule_pair": "", "rule_contact": "一般地质界线",
                             "rule_conf": "code_read", "expected": "",
                             "rule_younger": "", "young_side": ""})
            continue

        # 岩相接触规则（2026-10-15 用户裁定定版，两条）：
        # ① 两侧地质单元一致（同段，如 C1q3↔C1q3 1060 案）∧ 编码≠整合接触
        # ② 组内**连续**段间（相邻段，如 C1q2↔C1q3 1056 案）∧ 编码≠整合接触
        # → 岩相接触（渲染样式参照岩性渐变接触）。相邻判定与段间通则同源
        # （绝对段号差1/新编码 下|中、中|上/下|上仅两组式无中段）——
        # 跨段（隔中段）不属本规则（段间通则跨段=断层域）。
        # 防误伤限定：无专属规则（断层/冰雪/第四系/侵入/推测各行其分支，
        # 10/81/14 已在上游拦截）∧ 非纯岩浆岩（岩浆岩同单元仍走 43/60
        # 判定域，26 段渐变通过不动）。置于 43/60 语义分支之前——
        # 组内结构关系规则优先于岩浆岩判定域
        def _adjacent_group_pair(lu_units, ru_units):
            """组内相邻段判定（与段间通则共享 _adjacent_seg_tri 实现）。"""
            if len(lu_units) != 1 or len(ru_units) != 1:
                return False
            return _adjacent_seg_tri(_unit_seg(lu_units[0]),
                                     _unit_seg(ru_units[0])) is True

        _same_units = (bool(lu_units) and bool(ru_units)
                       and {clean_code(u["code"]) for u in lu_units}
                       == {clean_code(u["code"]) for u in ru_units})
        if ((_same_units or _adjacent_group_pair(lu_units, ru_units))
                and gz != "01" and not _code_sem_is(gz, "整合")
                and not _code_sem_is(gz, "断层", "冰雪", "第四系", "侵入", "推测")
                and not all(u["layer"] in ("侵入", "火山")
                            for u in lu_units + ru_units)):
            verdicts.append({**base, "verdict": "标定通过",
                             "rule_pair": "(岩相接触:两侧单元一致或组内连续段间"
                                          "+码非整合+无专属规则)",
                             "rule_contact": "岩相接触",
                             "rule_conf": "verified",
                             "expected": "岩相",
                             "rule_younger": "", "young_side": ""})
            continue
        if _code_sem_is(gz, "渐变"):  # 泛化触发（10-11）：码义含"渐变"即入 43 判定
            # 岩性过渡渐变（2026-09-24 用户核定）：岩浆岩间的一种接触界线，
            # 两侧岩浆岩时代、岩性要求一致——逐侧校验；违反者登记分歧交
            # 裁定（永不自动改码）。
            # 岩性比较属性字段优先（2026-10-05 用户裁定「确定侵入岩岩性时
            # 优先读取岩浆岩本身属性字段」）：单元 lith 槽（QDUEAQ 单元
            # 类型码→QDUECD 名称词）直读先行，希腊字母前缀仅在其双缺时
            # 兜底——г/∑ 误录变体不再走旁路；时代后缀=剥非 ASCII 前缀
            # 的拉丁段（比较空间一致性，取代旧希腊后缀混比）。
            # 岩性过渡渐变界线判定逻辑（2026-10-11 用户定版）：**两侧均为岩浆
            # 岩（层类判定，排他——任一侧含非岩浆岩单元即不符）+ 时代码一致 +
            # 岩性码一致 + 界线编码≠侵入接触编码（码义比较，泛化）→ 正向判定
            # 为岩浆岩间渐变界线**——判定挣得（verified），非注册兜底；未通过
            # 者不赋家族标签，登记分歧交裁定（永不自动改码）。
            # 约束史：2026-09-24 用户核定（英吉沙 3 段违反抓获在案）
            _why43 = []
            if not (lu_units and ru_units
                    and all(u["layer"] in ("侵入", "火山")
                            for u in lu_units + ru_units)):
                _why43.append("两侧非纯岩浆岩")
            else:
                if _liths(lu_units) != _liths(ru_units):
                    _why43.append("岩性不一致")
                if {_era_suffix_of(u["code"]) for u in lu_units} != \
                        {_era_suffix_of(u["code"]) for u in ru_units}:
                    _why43.append("时代不一致")
            _ok43 = not _why43
            verdicts.append({**base,
                             "verdict": "标定通过" if _ok43 else "渐变判定未通过",
                             "rule_pair": "(岩性渐变判定:两侧岩浆岩+同代+同岩性)"
                                          if _ok43 else
                                          f"(43判定未通过:{'+'.join(_why43)})",
                             "rule_contact": "岩性过渡渐变界线",
                             "rule_conf": "verified" if _ok43 else "conflict",
                             "expected": "43",
                             "rule_younger": "", "young_side": ""})
            continue
        # 岩性渐变发现通道（2026-10-11 用户定 43 判定逻辑配套）：码义非渐变/
        # 脉动/侵入/推测的码段（比码义不比码值——泛化），若两侧**纯**岩浆岩
        # （排他——含第四系/沉积单元者不候选，防 Q 覆盖碎片假命中）且时代、
        # 岩性一致 → 候选 43 登记（发现编图错误；编码为侵入接触义者有其专属
        # 规则、不候选——编码与侵入接触义不同是渐变判定的构成条件）
        if not _code_sem_is(gz, "渐变", "脉动", "侵入", "推测"):
            if all(u["layer"] in ("侵入", "火山") for u in lu_units + ru_units) \
                    and lu_units and ru_units:
                _l_ok = _liths(lu_units) == _liths(ru_units)
                _e_ok = ({_era_suffix_of(u["code"]) for u in lu_units}
                         == {_era_suffix_of(u["code"]) for u in ru_units})
                if _l_ok and _e_ok:
                    verdicts.append({**base, "verdict": "分歧",
                                     "rule_pair": "(岩性渐变判定:两侧岩浆岩+同代+同岩性)",
                                     "rule_contact": "岩性过渡渐变界线",
                                     "rule_conf": "verified", "expected": "43",
                                     "rule_younger": "", "young_side": ""})
                    continue
        if _code_sem_is(gz, "脉动"):  # 泛化触发（10-11）：码义含"脉动"即入 60 判定
            # 脉动接触判定逻辑（2026-10-11 用户定版）：**两侧均为岩浆岩（层类
            # 判定，排他）+ 时代码一致 + 岩性码不一致 + 界线编码≠侵入接触编码
            # 且≠渐变界线编码（码义比较，泛化）→ 正向判定为脉动接触**——判定
            # 挣得（verified），非注册兜底；未通过者不赋家族标签，登记分歧交
            # 裁定（永不自动改码）。约束史：2026-09-24 用户核定（库尔干 2/2、
            # 英吉沙 22/25+3 违反在案）；本次升级为判定逻辑——岩性一致者
            # （同代同岩性）不符合脉动定义，属 43 渐变判定域
            _why60 = []
            if not (lu_units and ru_units
                    and all(u["layer"] in ("侵入", "火山")
                            for u in lu_units + ru_units)):
                _why60.append("两侧非纯岩浆岩")
            else:
                if {_era_suffix_of(u["code"]) for u in lu_units} != \
                        {_era_suffix_of(u["code"]) for u in ru_units}:
                    _why60.append("时代不一致")
                if _liths(lu_units) == _liths(ru_units):
                    _why60.append("岩性一致（脉动须异岩性，同岩性属 43 渐变域）")
            _ok60 = not _why60
            verdicts.append({**base,
                             "verdict": "标定通过" if _ok60 else "脉动判定未通过",
                             "rule_pair": "(脉动判定:两侧岩浆岩+同代+异岩性)"
                                          if _ok60 else
                                          f"(60判定未通过:{'+'.join(_why60)})",
                             "rule_contact": "脉动接触界线",
                             "rule_conf": "verified" if _ok60 else "conflict",
                             "expected": "60",
                             "rule_younger": "", "young_side": ""})
            continue
        # 脉动接触发现通道（2026-10-11 用户定 60 判定逻辑配套）：码义非渐变/
        # 脉动/侵入/推测的码段（比码义不比码值——泛化），两侧纯岩浆岩 +
        # 时代一致 + 岩性不一致 → 候选 60 登记（发现编图错误；与 43 发现通道
        # 按岩性同/异互斥分流）
        if not _code_sem_is(gz, "渐变", "脉动", "侵入", "推测"):
            if all(u["layer"] in ("侵入", "火山") for u in lu_units + ru_units) \
                    and lu_units and ru_units:
                _l_neq = _liths(lu_units) != _liths(ru_units)
                _e_eq = ({_era_suffix_of(u["code"]) for u in lu_units}
                         == {_era_suffix_of(u["code"]) for u in ru_units})
                if _l_neq and _e_eq:
                    verdicts.append({**base, "verdict": "分歧",
                                     "rule_pair": "(脉动判定:两侧岩浆岩+同代+异岩性)",
                                     "rule_contact": "脉动接触界线",
                                     "rule_conf": "verified", "expected": "60",
                                     "rule_younger": "", "young_side": ""})
                    continue
        if gz == "16" or _code_sem_is(gz, "推测"):  # 泛化触发（10-11）
            # 推测地质界线核定（2026-09-13 用户批准，仿推测断层标定；
            # 2026-10-11 用户裁定强化：16 不能靠兜底逻辑、要通过判定逻辑——
            # 三检是唯一语义来源，未通过段不再挂「推测地质界线」家族标签；
            # 覆盖证据缺省（无第四系且无冰雪面元）是判定的诚实"无法判定"
            # 输出而非误读矛盾——登记未覆盖）：
            # ① 覆盖度 ≥80%（松散Q剔Qp1X/冰雪）——"推测"前提；
            #    <40% 基岩出露 → 与"推测"矛盾；
            # ② 连接性：两端 ≤10m 连接同一接触类型的实测界线段（非16/81/10）——
            #    确认"覆盖区延伸段"角色；
            # ③ 三条全过=核定通过；部分覆盖/连接不足=存疑交人工
            geom = bounds.geometry.values[idx]
            frac16 = _cov_frac8(geom)
            conns = _conn_types16(idx, geom)
            same_type = len(set(conns)) == 1 and bool(conns)
            if q_u is None and ice_u is None:
                # 覆盖证据缺省：三检不可运行——判定的诚实输出是"无法判定"，
                # 登记未覆盖（原先 frac16=0 误落"矛盾"，把无数据读成基岩出露）
                v16 = "未覆盖（覆盖证据缺省）"
            elif frac16 < 0.4:
                v16 = "矛盾（推测界线）"
            elif frac16 >= 0.8 and same_type:
                v16 = "核定通过（推测界线）"
            else:
                v16 = "存疑（推测界线）"
            verdicts.append({**base, "verdict": v16,
                             "rule_pair": f"覆盖{frac16:.0%}/连接{conns or '无'}"
                                         if v16 != "未覆盖（覆盖证据缺省）"
                                         else "覆盖证据缺省（本幅无第四系/冰雪面元）",
                             "rule_contact": "推测地质界线", "rule_conf": "calibrated",
                             "expected": "16", "rule_younger": "", "young_side": ""})
            continue
        hits = []
        # 码级匹配优先（2026-09-26 修 contact/62 案：norm_name 把"克孜尔塔格组
        # 一/二/三段"全部归并到同名同键，三条段级裁定规则（一段|二段整合、一段|
        # 三段跨段仅断层、二段|三段整合）被名称匹配同时命中而制造假分歧——先按码、
        # 码无命中再回退名称）
        for lu in lu_units:
            for ru in ru_units:
                key = tuple(sorted(clean_code(x) for x in (lu["code"], ru["code"])))
                for rule in rule_code_index.get(key, []):
                    yl = None
                    yn = norm_name(rule.get("younger", "") or "")
                    if yn:
                        if yn == norm_name(lu["name"]):
                            yl = "left"
                        elif yn == norm_name(ru["name"]):
                            yl = "right"
                    hits.append((lu, ru, rule, yl))
        if not hits:
            for lu in lu_units:
                for ru in ru_units:
                    key = tuple(sorted(norm_name(x) for x in (lu["name"], ru["name"])))
                    for rule in rule_index.get(key, []):
                        yl = None
                        yn = norm_name(rule.get("younger", "") or "")
                        if yn:
                            if yn == norm_name(lu["name"]):
                                yl = "left"
                            elif yn == norm_name(ru["name"]):
                                yl = "right"
                        hits.append((lu, ru, rule, yl))
        # 段号甄别（2026-09-26 用户定）：同组同名段级单元名称回退会同时命中
        # 相邻段与跨段规则——以界线两侧单元码解析的段号对精筛命中；伪命中
        # 弃空后落下方段间通则内禀判别
        if hits and len(lu_units) == 1 and len(ru_units) == 1:
            _seg_actual = []
            for _u in (lu_units[0], ru_units[0]):
                _k = _unit_seg(_u)
                if _k is not None and _k[1] is not None and _k[1] > 0:
                    _seg_actual.append(_k[1])
            actual = tuple(sorted(_seg_actual))
            if len(actual) == 2:
                hits = [h for h in hits if _seg_hits_ok(h[2], actual)]
        if hits:
            exp_sets = {tuple(sorted(CT2GZBD.get(r["contact"], set()))) for _, _, r, _ in hits}
            multi = len(exp_sets) > 1
            lu, ru, rule, yl = hits[0]
            exp = CT2GZBD.get(rule["contact"], set())
            verdict = "多规则分歧" if multi else ("标定通过" if gz in exp else "分歧")
            verdicts.append({**base, "verdict": verdict,
                             "rule_pair": f"{rule['pair'][0]}|{rule['pair'][1]}",
                             "rule_contact": _refine_unconformity(
                                 gz, ";".join(sorted({r["contact"] for _, _, r, _ in hits}))),
                             "rule_conf": rule["confidence"],
                             "expected": "/".join(sorted(exp)) if not multi else
                                         "||".join("/".join(s) for s in sorted(exp_sets)),
                             "rule_younger": rule.get("younger", ""),
                             "young_side": yl or ""})
            continue
        # 自支持段间通则（2026-09-29 用户裁定定版）：**上段新，下段老；
        # 一段老，二段新；同一组的相邻段之间为整合接触（期望 GZBD=01）**。
        # 跨段（中间缺段）不能地层接触、仅断层接触（10，2026-09-20 补充裁定）。
        # 段号双源：代号直读（组前缀+末位段号）优先、名称段式回退
        # （路乐河组二段/X组下上段）；相对×绝对混比不可判→不冒通则。
        # 裁定条（码级/名称命中）优先于本通则；多单元侧（拼接三角点）不适用。
        if len(lu_units) == 1 and len(ru_units) == 1:
            _adj_t = _adjacent_seg_tri(_unit_seg(lu_units[0]),
                                       _unit_seg(ru_units[0]))
            if _adj_t is not None:
                exp = {"01"} if _adj_t else {"10"}
                verdicts.append({**base,
                                 "verdict": "标定通过" if gz in exp else "分歧",
                                 "rule_pair": "(段间通则-相邻段)" if _adj_t
                                             else "(段间通则-跨段仅断层)",
                                 "rule_contact": "整合接触" if _adj_t else "断层接触",
                                 "rule_conf": "self_supporting",
                                 "expected": "/".join(sorted(exp)),
                                 "rule_younger": "", "young_side": ""})
                continue
                # _adj_t is None（相对×绝对混比不可判）→ 落下方通用级联
        all_layers = {u["layer"] for u in lu_units + ru_units}
        # 第四系判定：剔除半固结成岩沉积层（Qp1X 西域组等，算基岩；
        # 2026-10-22 增名称剔除——新疆群全变体）
        # （2026-10-04 QDUECD 兜底链：г/∑ 误录前缀码的时代从剥前缀后缀/
        # 名称时代词恢复——不再静默丢证据）
        ages = [a for u in lu_units + ru_units
                if clean_code(u["code"]) not in Q_EXCLUDE
                and not any(x in (u.get("name") or "")
                            for x in Q_EXCLUDE_NAMES)
                and (a := _age_rank_of(u)) is not None]
        if ages and max(ages) >= 1300:
            exp, cname, rpair = {"02"}, "第四系界线", "(第四系通用规则)"
        elif "侵入" in all_layers:
            int_ages = [a for u in lu_units + ru_units if u["layer"] == "侵入"
                        and (a := _age_rank_of(u)) is not None]
            oth_ages = [a for u in lu_units + ru_units if u["layer"] != "侵入"
                        and (a := _age_rank_of(u)) is not None]
            cover = int_ages and oth_ages and max(oth_ages) > max(int_ages)
            exp = {"04"} if cover else {"11"}
            cname = "角度不整合" if cover else "侵入接触"
            rpair = "(侵入通用规则-覆盖)" if cover else "(侵入通用规则)"
        elif any(clean_code(u["code"]) == "Qp1X" for u in lu_units + ru_units):
            # 西域组通用规则（2026-09-13 用户裁定原则，修订版）：
            # 西域组与下伏地层接触关系【优先以志书单元对规则为准】——
            # 单元对规则在本函数前段已先行匹配（如 库车组|西域组=整合、
            # 乌苏群|西域组=不整合）；此处仅对先验未覆盖的组合兜底：
            # 西域组上覆于更老地层 → 角度不整合(04)，年轻侧=西域组。
            xy = [a for u in lu_units + ru_units if clean_code(u["code"]) == "Qp1X"
                  and (a := _age_rank_of(u)) is not None]
            oth = [a for u in lu_units + ru_units if clean_code(u["code"]) != "Qp1X"
                   and (a := _age_rank_of(u)) is not None]
            if xy and oth and max(oth) < max(xy):
                exp, cname, rpair = {"04"}, "角度不整合", "(西域组通用规则)"
            else:
                exp, cname, rpair = None, None, None
            if exp is None:
                verdicts.append({**base, "verdict": "未覆盖", "rule_pair": "",
                                 "rule_contact": "", "rule_conf": "", "expected": "",
                                 "rule_younger": "", "young_side": ""})
                continue
        elif _same_group_member(lu_units, ru_units):
            # 同组段间通用规则（2026-09-15 用户定）：
            # 同一地层组的上段、下段之间应为整合接触(01)
            # （组名相同且段名不同；断层 GZBD=10 不参与本标定）
            exp, cname, rpair = {"01"}, "整合接触", "(同组段间通用规则)"
        elif ages and ((max(ages) - min(ages)) >= 200
                       or max(a // 100.0 for a in ages)
                       - min(a // 100.0 for a in ages) >= 2
                       or _missing_stage_gap(ages)):
            # 间断通则（2026-09-26 用户指令，contact/56 案例 J3kz|C2ak 驱动；
            # 2026-10-09 用户优化：J1b↔P2a 案例——两侧单元跨系缺带（系带差
            # ≥2，如 J(900)↔P(700) 缺整个三叠系）时数值差 199<200 曾漏判
            # 落入"未覆盖"。补系带差≥2 条件：跨带必然沉积间断，至少排除
            # 整合接触关系）：
            # 两侧均为地层单元（非第四系、非侵入——已在上游分支处理）且年龄
            # 间断 ≥200（明显沉积间断）或跨系缺带 ≥2 或跨系缺失整统
            # （2026-10-14 用户裁定：D1↔C2 中间缺 C1=显著间断）→ 不整合接触
            # （04 角度不整合兜底，24 平行不整合兼容）；01 实测界线命中者
            # 登记"分歧"交裁定（发现编图错误通道）。阈值证据：04 码 25%分位
            # 101/中位 398、01 码 95%分位 101，≥200 全幅仅 8 段。
            exp, cname, rpair = {"04", "24"}, \
                _refine_unconformity(gz, "不整合接触"), "(间断通则)"
        elif "style" not in _ABLATE and                 _lt_map.get(str(_lt_by_src.get(idx, ""))):
            # 线型图形语义分支（2026-10-16 路线1）：制图样式的接触类型
            # 断言——xj115 挖掘 ≥85% 纯度注册（line_style_semantics_<key>.
            # json）；级联末位正规则（地质先验全部不命中才轮到图面样式
            # 断言）——期望码/语义双出口，核验+发现双向（gz∈exp 标定通过
            # /否则分歧登记，证据=线型注册语义）
            _lt0 = _lt_by_src.get(idx)
            _sem0 = _lt_map.get(str(_lt0))
            _CT2GZ0 = dict(CT2GZBD)
            _CT2GZ0.setdefault("岩性过渡渐变界线", {"43"})
            exp = set(_CT2GZ0.get(_sem0, set()))
            cname = _sem0
            rpair = f"(线型图形语义:{_lt0}→{'/'.join(sorted(exp))})"
        else:
            # 整合接触反向判别（2026-10-11 用户裁定·七项排除全规格）：
            # **无断层接触证据 ∧ 无推测地质界线证据 ∧ 无水体、冰雪区证据 ∧
            # 无第四系松散沉积物证据 ∧ 无年代间断 ∧ 无岩浆岩 ∧ 无不整合接触
            # 先验 → 判定整合接触**（verified 挣得，不再未覆盖兜底）。
            # 级联位置学：走到末端即「第四系规则未命中（无 Q 证据）∧间断通则
            # 未命中（无年代间断）∧单元对规则未命中（无不整合先验）」；断层/
            # 冰川水体/岩浆岩/覆盖四项显式核验。非 01 码满足全部排除 → 候选
            # 01 登记（发现编图错误通道）
            _no_fault = _pct10 is None or _pct10 < 0.9
            _no_ice = _pct81 is None or _pct81 < 0.9
            _igneous_free = ("侵入" not in all_layers and "火山" not in all_layers)
            # 无推测界线证据：16 三检同款覆盖度采样（_cov_frac8 共享）——
            # Q/冰雪覆盖 <80% 才算"无推测证据"（覆盖证据缺省视为无证据，不误读）
            _cov = _cov_frac8(bounds.geometry.values[idx])
            _no_infer = _cov is None or _cov < 0.8
            if _no_fault and _no_ice and _igneous_free and _no_infer:
                _ev_rev = ("无断层重合" if _pct10 is None
                           else f"断层重合{_pct10:.0%}<90%") \
                          + ("；无冰川水体重合" if _pct81 is None
                             else f"；冰川水体重合{_pct81:.0%}<90%") \
                          + ("；覆盖证据缺省" if _cov is None
                             else f"；覆盖{_cov:.0%}<80%") \
                          + ("；年龄秩不可测" if not ages
                             else f"；年龄差{max(ages) - min(ages):.0f}") \
                          + "；无岩浆岩；无Q；无不整合先验"
                if gz == "01":
                    verdicts.append({**base, "verdict": "标定通过",
                                     "rule_pair": f"(整合反向判别:{_ev_rev})",
                                     "rule_contact": "整合接触",
                                     # 弱置信度（用户裁定 10-11）：排除法=
                                     # 无反证之默认，非正向证据
                                     "rule_conf": "inferred", "expected": "01",
                                     "rule_younger": "", "young_side": ""})
                else:
                    verdicts.append({**base, "verdict": "分歧",
                                     "rule_pair": f"(整合反向判别:{_ev_rev})",
                                     "rule_contact": "整合接触",
                                     "rule_conf": "inferred", "expected": "01",
                                     "rule_younger": "", "young_side": ""})
                continue
            verdicts.append({**base, "verdict": "未覆盖", "rule_pair": "",
                             "rule_contact": "", "rule_conf": "", "expected": "",
                             "rule_younger": "", "young_side": ""})
            continue
        # 间断通则补填年轻侧（先验年轻侧通道）：age_rank 大者所在侧
        if rpair == "(间断通则)" and ages:
            _lmax = max((a for a in (_age_rank_of(u) for u in lu_units)
                         if a is not None), default=None)
            _rmax = max((a for a in (_age_rank_of(u) for u in ru_units)
                         if a is not None), default=None)
            if _lmax is not None and _rmax is not None and _lmax != _rmax:
                base = {**base, "rule_younger": "", "young_side": "left" if _lmax > _rmax else "right"}
        # 通用规则统一补年轻侧（2026-09-26 强化）：年龄秩大者所在侧
        # （第四系侧恒新；侵入侧恒新于被侵入围岩；覆盖式年轻地层侧恒新——年龄序
        # 统一可算；同组段间的新老由 C0 段序补位执行——「同龄不判」旧约定
        # 已于 2026-09-29 用户裁定废止）
        if not base.get("young_side") and ages and rpair in (
                "(第四系通用规则)", "(侵入通用规则)", "(侵入通用规则-覆盖)",
                "(西域组通用规则)"):
            _lmax = max((a for a in (_age_rank_of(u) for u in lu_units)
                         if a is not None), default=None)
            _rmax = max((a for a in (_age_rank_of(u) for u in ru_units)
                         if a is not None), default=None)
            if _lmax is not None and _rmax is not None and _lmax != _rmax:
                base = {**base, "rule_younger": "", "young_side": "left" if _lmax > _rmax else "right"}
        verdicts.append({**base, "verdict": "标定通过" if gz in exp else "分歧",
                         "rule_pair": rpair, "rule_contact": cname,
                         # 2026-10-11 用户裁定置信分级：不整合接触判据=强置信度
                         # （间断通则/西域组规则产出正向间断证据→verified）；
                         # 整合接触反向判别=弱置信度（排除法默认→inferred，
                         # 见级联末端分支）
                         "rule_conf": ("verified" if rpair in ("(间断通则)", "(西域组通用规则)")
                                       else "generic"),
                         "expected": "/".join(sorted(exp)),
                         "rule_younger": base.get("rule_younger", ""),
                         "young_side": base.get("young_side", "")})

    rep = pd.DataFrame(verdicts)
    rep[rep["gzbd"] != "10"].to_csv(_out("_gzbd_calibration_report.csv"),
                                    index=False, encoding="utf-8-sig")
    print("B. 先验标定完成（断层接触=重合规则级联判定，2026-10-10 起）：")
    print(rep[rep["gzbd"] != "10"]["verdict"].value_counts().to_string())

    # ---------- B2. 间断通则互证标记 + 先验缺口候选单（2026-09-26 强化） ----------
    # 互证：priors/裁定命中且间断通则同向（gap≥200 且 gz∈{04,24}）→ 证据加注，
    # 不改判定、不改置信级（佐证信息位）
    def _gap_of(row):
        codes = re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(row["left"]) + str(row["right"]))
        ranks = [a for c in codes if (a := _unit_age_rank(clean_code(c))) is not None]
        return (max(ranks) - min(ranks)) if len(ranks) >= 2 else None

    _corr = 0
    for i, r in rep.iterrows():
        if r["verdict"] == "标定通过" and "(间断通则)" not in str(r["rule_pair"]):
            g = _gap_of(r)
            if g is not None and g >= 200 and r["gzbd"] in ("04", "24"):
                rep.at[i, "rule_pair"] = str(r["rule_pair"]) + "＋间断通则互证"
                _corr += 1
    print(f"   间断通则互证标记：{_corr} 段（priors/裁定命中且同向）")

    # 缺口→裁定候选单：未覆盖段的结构化输出（contact/56 案的机制化）
    def _names_of(side):
        return re.findall(r"\(([^)]+)\)", str(side))

    _MEMOIR_CONTACTS = None


    def _memoir_contacts():
        nonlocal _MEMOIR_CONTACTS  # 函数化后模块全局→闭包（2026-09-29 修）
        if _MEMOIR_CONTACTS is None:
            rows = []
            p = str(data_path("xinjiang_stratigraphic_contacts.csv"))
            if _os.path.exists(p):
                import csv as _csv
                with open(p, encoding="utf-8-sig", newline="") as f:
                    for row in _csv.DictReader(f):
                        rows.append(row)
            _MEMOIR_CONTACTS = rows
        return _MEMOIR_CONTACTS


    def _name_variants(name):
        """别名候选生成（contact/66 案：别名缺环≠知识真空）：
        alias_map 直查 + 保守字形变体（莎↔沙）+ 群→组桥（志书"组名（群名）"括注）
        + 组→群桥（group_composition 成员隶属）。"""
        out = set()
        if name in ALIAS:
            out.add(ALIAS[name])
        for a, b in [("莎", "沙")]:
            if a in name:
                out.add(name.replace(a, b))
            if b in name:
                out.add(name.replace(b, a))
        if name.endswith("群"):
            for row in _memoir_contacts():
                unit = str(row.get("地层单元", ""))
                m = re.search(r"[（(]([^）)]+)[）)]", unit)
                if m and m.group(1) in (name, name.replace("莎", "沙"), name.replace("沙", "莎")):
                    out.add(unit.split("（")[0].split("(")[0])
        elif name.endswith("组"):
            for g in priors.get("group_composition", {}).get("groups", []):
                if any(mb.get("name") == name for mb in g.get("members", [])):
                    out.add(g["group"])
        return out


    def _alias_bridge(lname, rname):
        """两侧名称变体组合命中现有规则 → (左变体, 右变体, 规则) 或 None。"""
        for ln in [lname] + sorted(_name_variants(lname)):
            for rn in [rname] + sorted(_name_variants(rname)):
                if ln == lname and rn == rname:
                    continue
                key = tuple(sorted(norm_name(x) for x in (ln, rn)))
                for rule in rule_index.get(key, []):
                    return (ln, rn, rule)
        return None


    _gaps = []
    for _, r in rep[(rep["verdict"] == "未覆盖") & (rep["gzbd"] != "10")].iterrows():
        g = _gap_of(r)
        if g is not None and g >= 200:
            sugg = "间断通则候选（不整合接触）"
            bridge = None
        else:
            bridge = None
            for ln in _names_of(r["left"]):
                for rn in _names_of(r["right"]):
                    bridge = _alias_bridge(ln, rn)
                    if bridge:
                        break
                if bridge:
                    break
            if bridge:
                sugg = (f"别名候选：{ln}→{bridge[0]}｜{rn}→{bridge[1]}"
                        f"（命中规则 {bridge[2]['pair'][0]}|{bridge[2]['pair'][1]}"
                        f"={bridge[2]['contact']}，{bridge[2].get('confidence','')}）")
            elif "侵入" in str(r["left"]) + str(r["right"]):
                sugg = "侵入接触候选（查侵入关系）"
            else:
                sugg = "单元对规则候选（查志书补录）"
        _gaps.append({"idx": r["idx"], "gzbd": r["gzbd"], "left": r["left"],
                      "right": r["right"], "age_gap": g, "suggestion": sugg})
    gap_df = pd.DataFrame(_gaps)
    gap_df.to_csv(_out("_gzbd_gap_candidates.csv"), index=False, encoding="utf-8-sig")
    _alias_n = gap_df["suggestion"].str.startswith("别名候选").sum() if len(gap_df) else 0
    print(f"   先验缺口候选单：{len(gap_df)} 段 → _gzbd_gap_candidates.csv"
          f"（其中别名候选 {_alias_n} 段）")


    # G1 统计（2026-10-10 用户裁定版）：断层/冰雪接触均改由级联内重合规则
    # 判定（计算已前移至 B 段级联之前）——此处仅汇总
    _n10 = int((rep["gzbd"] == "10").sum())
    _c10 = [_coinc_all.get(int(r["idx"])) for _, r in rep.iterrows()
            if r["gzbd"] == "10"]
    _n10_pass = sum(1 for c in _c10 if c is not None and c >= 0.9)
    _n10_low = sum(1 for c in _c10 if c is not None and c < 0.9)
    _n10_unv = sum(1 for c in _c10 if c is None)
    _n_cand = sum(1 for _, r in rep.iterrows()
                  if r["gzbd"] not in ("10", "81")
                  and (c := _coinc_all.get(int(r["idx"]))) is not None
                  and c >= 0.9)
    _n81 = int((rep["gzbd"] == "81").sum())
    _c81 = [_coinc_ice.get(int(r["idx"])) for _, r in rep.iterrows()
            if r["gzbd"] == "81"]
    _n81_pass = sum(1 for c in _c81 if c is not None and c >= 0.9)
    _n81_low = sum(1 for c in _c81 if c is not None and c < 0.9)
    _n81_unv = sum(1 for c in _c81 if c is None)
    _n_cand81 = sum(1 for _, r in rep.iterrows()
                    if r["gzbd"] not in ("10", "81")
                    and (c := _coinc_ice.get(int(r["idx"]))) is not None
                    and c >= 0.9)
    print(f"   断层重合规则：码10 {_n10} 段（重合≥90% {_n10_pass}，"
          f"不足 {_n10_low}，无数据 {_n10_unv}）；"
          f"非10码高重合候选 {_n_cand} 段（登记分歧待裁定）")
    print(f"   冰雪重合规则：码81 {_n81} 段（重合≥90% {_n81_pass}，"
          f"不足 {_n81_low}，无数据 {_n81_unv}）；"
          f"非81码高重合候选 {_n_cand81} 段（登记分歧待裁定）")

    # G3（2026-09-29 泛化优化）：码义一致性声明——硬编码分支语义 × 幅级词表
    # 注册对照，偏移/未注册者入审计档案（分支结构不变，三审前置把关机制化）
    # 2026-10-10：10/81 路由双撤（均改重合证据级联），_BRANCH_EXPECT 同步移除
    _BRANCH_EXPECT = {"43": "igneous_phase_contact", "60": "igneous_phase_contact",
                      "16": "contact"}
    _sem_checks = []
    for _vp in (sh.root / "data" / "geosciml_vocab_mapping.json",
                sh.root / f"geosciml_vocab_mapping_{sh.key}.json"):
        if _vp.exists():
            _vz = (json.loads(_vp.read_text(encoding="utf-8"))
                   .get("gzbd_contacttype", {}))
            for _c, _exp_st in _BRANCH_EXPECT.items():
                _vr = _vz.get(_c) or {}
                _st = _vr.get("status", "absent")
                _term = _vr.get("term")
                _bad = ((_c in ("43", "60") and _st == "decided"
                         and _term not in (None, "igneous_phase_contact"))
                        or (_c == "81" and _st not in ("absent", _exp_st)))
                _sem_checks.append({
                    "code": _c, "registry": f"{_st}" + (f":{_term}" if _term else ""),
                    "branch_assumption": _exp_st,
                    "verdict": ("偏移！分支假设与幅级注册不一致（交人工核义）"
                                if _bad else "一致/未注册（分支按国家标准语义运行）")})
            break
    if _sem_checks:
        pd.DataFrame(_sem_checks).to_csv(
            _out("_gzbd_code_semantics_check.csv"), index=False,
            encoding="utf-8-sig")

    # ---------- C0. 段序新老原则执行（2026-09-29 用户裁定：上段新，下段老；
# 一段老，二/三段新）——同组段级单元对的年轻侧=段号大者侧（绝对/相对同式：
# 数值大=新）。先验 younger 明示优先，空时按段序补位；旧约定「同组段间
# 两侧同龄不判」废止（段序内禀新老，整合/断层接触两态下新老关系均成立）。 ----------
    _seg_fill = 0
    for _i, _r in rep.iterrows():
        if _r.get("young_side"):
            continue  # 先验明示优先
        _lcs = re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(_r["left"]))
        _rcs = re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(_r["right"]))
        if len(_lcs) != 1 or len(_rcs) != 1:
            continue
        _lns = re.findall(r"\(([^()]*)\)", str(_r["left"]))
        _rns = re.findall(r"\(([^()]*)\)", str(_r["right"]))
        _lu = {"code": _lcs[0], "name": (_lns[0] if len(_lns) == 1
                                         else code2name.get(_lcs[0], _lcs[0]))}
        _ru = {"code": _rcs[0], "name": (_rns[0] if len(_rns) == 1
                                         else code2name.get(_rcs[0], _rcs[0]))}
        _sl, _sr = _unit_seg(_lu), _unit_seg(_ru)
        if not (_sl and _sr and _sl[0] == _sr[0] and _sl[1] != _sr[1]):
            continue
        _a, _b = _sl[1], _sr[1]
        if not ((_a > 0 and _b > 0) or (_a < 0 and _b < 0)):
            continue  # 相对×绝对混比不可判
        rep.at[_i, "young_side"] = "left" if _a > _b else "right"
        _seg_fill += 1
    if _seg_fill:
        print(f"   段序年轻侧补位：{_seg_fill} 段（上/下、一/二/三段新老原则执行）")

# ---------- C. 语义解释 + 年轻侧对账 ----------
    interp = []
    for _, r in rep.iterrows():
        gz, idx = r["gzbd"], int(r["idx"])
        base_sem = (codes_meta.get(gz, {}).get("meaning")
                    or (gz if not gz.isdigit() else "?"))
        out = {"idx": idx, "GZBD原码": gz, "原码语义": base_sem,
               "先验年轻侧": r["young_side"], "点线裁定侧": side_ov.get(str(idx), "")}
        if r["verdict"] == "制图误差（剔除）":
            out.update(标定语义="（制图误差，不参与标定与渲染语义）", GZBD_eff=gz,
                       状态=r["verdict"], 证据=carto_err[str(idx)], 置信度="user")
        elif str(idx) in type_ov:
            new = type_ov[str(idx)]
            out.update(标定语义=codes_meta.get(new, {}).get("meaning", new),
                       GZBD_eff=new, 状态="用户裁定改码",
                       证据=f"原码 {gz}→{new}（gzbd_overrides.json）", 置信度="user")
        elif str(idx) in noise_seg:
            # 编图错误噪声段（2026-10-09 T3 裁定回路）：直接取码级裁定语义
            # （user_semantic）；2026-10-11 摒弃注册兜底——无用户裁定语义者
            # 不再回退注册表码义/码面直读，置空待裁定（语义缺席即裁定对象）
            _ns_sem = _user_bsem_early.get(gz) or ""
            out.update(标定语义=_ns_sem, GZBD_eff=gz, 状态="裁定噪声（编图错误）",
                       证据=f"编图错误噪声裁定：{noise_seg[str(idx)]}",
                       置信度="user")
        elif str(r.get("rule_pair") or "").startswith(("(断层重合规则", "(冰雪重合规则")):
            # 重合规则出站（2026-10-10 用户裁定：10/81 双路由撤销，界线与
            # 本体层（FBA003 断层线 / LDLYAAE002 冰川面轮廓）实测重合判定；
            # 核验/发现双向；10-11 提前于文本码分支——文本码「断层接触」
            # 等同样吃重合核验证据，标签保字面）
            _rc = str(r["rule_contact"])          # 断层接触（断裂界线）/ 冰雪区界线
            _exp = str(r["expected"])             # 10 / 81
            _orc = "LDZOFBA003 实测断层线" if _exp == "10" else "LDLYAAE002 冰川面元"
            # 泛化（10-11）：文本码幅 GZBD_eff 保原文（码即语义），标签取字面；
            # 数值码幅走国标码与规范标签
            _rc_eff = _rc if gz.isdigit() else gz
            _gz_eff = _exp if gz.isdigit() else gz
            if r["verdict"] == "标定通过":
                out.update(标定语义=_rc_eff, GZBD_eff=_gz_eff,
                           状态="标定通过",
                           证据=f"界线与{_orc}重合核验通过（{r['rule_pair']}）",
                           置信度="verified")
            elif r["verdict"] == "分歧":
                _cand_lbl = (f"{_rc_eff}（先验建议→{_exp}）" if gz.isdigit()
                             else f"候选{_rc}（重合实测）")
                out.update(标定语义=_cand_lbl, GZBD_eff=gz,
                           状态="分歧未裁定",
                           证据=f"界线与{_orc}高重合而图面码={gz}（非 {_exp}）——"
                                f"候选{_rc}登记（{r['rule_pair']}）",
                           置信度="conflict")
            elif r["verdict"].startswith("重合不足"):
                out.update(标定语义=f"{_rc_eff.split('（')[0]}存疑（重合不足）",
                           GZBD_eff=gz, 状态="分歧未裁定",
                           证据=f"码 {_exp} 声明{_rc}但与{_orc}重合不足"
                                f"（{r['rule_pair']}）——交裁定",
                           置信度="conflict")
            else:  # 未覆盖：本幅无本体层数据
                out.update(标定语义="", GZBD_eff=gz,
                           状态="未覆盖（先验缺口）",
                           证据=f"重合证据缺省（{r['rule_pair']}）——无语义赋值（摒弃兜底）",
                           置信度="uncovered")
        elif not gz.isdigit():
            # 文本码（2026-10-09 新疆115 C 类 K46C001004·用户裁定方案一）：
            # GZBD 字段直写中文语义——字面即语义，独立码族登记；不改码、
            # 不经 MLE/先验级联，置信按 verified×single（图面自声明单源）
            out.update(标定语义=gz, GZBD_eff=gz, 状态="字面语义（文本码）",
                       证据="GZBD 字段直写中文语义（字面即语义注册）",
                       置信度="verified")
        elif r["verdict"] == "特殊码兜底":
            # 2026-10-11 用户裁定：摒弃注册兜底——域外码不再赋「一般地质界线」
            # 默认语义，标「未解析」进 pending（语义缺席即裁定对象）
            out.update(标定语义="", GZBD_eff=gz, 状态="未解析（码域外）",
                       证据=f"码 {gz} 不在 GZBD 标定域——无语义赋值（2026-10-11 摒弃兜底后）",
                       置信度="uncovered")
        elif r["verdict"] == "核定通过（推测界线）":
            out.update(标定语义="推测地质界线（覆盖区延伸段）", GZBD_eff="16",
                       状态="标定通过", 证据=f"三检：{r['rule_pair']}",
                       置信度="calibrated")
        elif r["verdict"] == "存疑（推测界线）":
            # 2026-10-11 用户裁定：16 不能靠兜底逻辑——三检未通过段不赋
            # 推测家族标签（标签即语义断言），只记存疑事实交裁定
            out.update(标定语义="界线性质存疑（推测核定不足）",
                       GZBD_eff=gz, 状态="分歧未裁定",
                       证据=f"推测界线三检未通过（{r['rule_pair']}）——"
                            f"不赋推测语义，交裁定", 置信度="conflict")
        elif r["verdict"] == "矛盾（推测界线）":
            out.update(标定语义="非推测界线嫌疑（基岩出露与推测矛盾）",
                       GZBD_eff=gz, 状态="分歧未裁定",
                       证据=f"推测界线三检矛盾（{r['rule_pair']}）——"
                            f"不赋推测语义，交裁定", 置信度="conflict")
        elif r["verdict"] == "未覆盖（覆盖证据缺省）":
            # 覆盖证据缺省：判定不可运行——注册表定义性标签展示，
            # 缺口如实登记（不伪装判定）；摒弃兜底后无语义赋值
            out.update(标定语义="", GZBD_eff=gz,
                       状态="未覆盖（先验缺口）",
                       证据="覆盖证据缺省（本幅无第四系/冰雪面元，三检不可运行）",
                       置信度="uncovered")
        elif r["verdict"] == "标定通过":
            src = "志书单元对规则" if str(r["rule_conf"]).startswith("memoir") else "通用规则"
            # 2026-10-11 摒弃注册兜底：标定语义一律取规则出站语义
            # （rule_contact），不再回退注册表码义（原间断通则保留码表细分名
            # 的通道同时撤销——细分名属注册义）
            sem = str(r["rule_contact"] or "")
            out.update(标定语义=sem, GZBD_eff=gz,
                       状态="标定通过", 证据=f"{src}：{r['rule_pair']}",
                       置信度=str(r["rule_conf"]))
        elif r["verdict"] == "渐变判定未通过":
            # 2026-10-11 用户裁定（同 16 逻辑）：判定未通过段不赋家族标签
            out.update(标定语义="岩性渐变嫌疑未通过（两侧时代/岩性不一致或非岩浆岩）",
                       GZBD_eff=gz, 状态="分歧未裁定",
                       证据=f"43 判定逻辑未通过{r['rule_pair']}——不赋渐变语义，交裁定",
                       置信度="conflict")
        elif r["verdict"] == "脉动判定未通过":
            # 2026-10-11 用户裁定（同 16/43 逻辑）：判定未通过段不赋家族标签
            out.update(标定语义="脉动接触嫌疑未通过（时代不一致/非岩浆岩/岩性一致）",
                       GZBD_eff=gz, 状态="分歧未裁定",
                       证据=f"60 判定逻辑未通过{r['rule_pair']}——不赋脉动语义，交裁定",
                       置信度="conflict")
        elif r["verdict"] in ("分歧", "多规则分歧"):
            out.update(标定语义=f"{r['rule_contact']}（先验建议→{r['expected']}）",
                       GZBD_eff=gz, 状态="分歧未裁定",
                       证据=f"{r['rule_pair']} 期望 {r['expected']}", 置信度="conflict")
        elif str(r["verdict"]).startswith("分歧未裁定（"):
            # 岩性过渡渐变约束违反（2026-09-24 用户核定：两侧岩浆岩时代岩性须一致）；
            # 摒弃兜底后违反段不赋注册义
            out.update(标定语义="", GZBD_eff=gz, 状态="分歧未裁定",
                       证据=str(r["verdict"]), 置信度="conflict")
        else:
            # 未覆盖归因：缺口单元 vs 规则组合缺失；摒弃兜底后无语义赋值
            codes_l = re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(r["left"]))
            codes_r = re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(r["right"]))
            gap_hit = [c for c in codes_l + codes_r if c in GAPS]
            cause = f"志书缺口单元: {'/'.join(gap_hit)}" if gap_hit else "单元对组合未收录"
            out.update(标定语义="", GZBD_eff=gz, 状态="未覆盖（先验缺口）",
                       证据=cause, 置信度="uncovered")
        interp.append(out)

    # ---------- C'. 影子置信度（统一框架 S×I×F，2026-09-27 裁定参数） ----------
    # 既有「置信度」标签列原样保留；统一三列 confidence_u/conf_breakdown_u/
    # conf_band_u 附后。映射语义：标定通过=先验×图面码核验一致（两独立认识源，
    # I=multi_root）；分歧/存疑 → F=0 直落冲突册；未覆盖=无假设 → unassessed。
    from pymapgis.semantics.confidence import emit_columns, evaluate

    _GZBD_S = {"adjudicated": "adjudicated", "user": "adjudicated",
               "user_confirmed": "verified", "verified": "verified",
               "memoir": "verified", "memoir_multi": "verified",
               "calibrated": "multi", "inferred": "single", "generic": "single",
               "self_supporting": "single", "uncovered": "code_read",
               "conflict": "code_read", "": "code_read"}


    def _gzbd_shadow(row):
        st = str(row["状态"])
        conf = str(row["置信度"])
        # D4：用户裁定改码/制图误差剔除——裁定本身可信（C=1.0），
        # 剔除语义由 状态/excluded 承载（语义反转已在方案中显式登记）
        if st in ("用户裁定改码", "制图误差（剔除）"):
            return evaluate("adjudicated", adjudicated=True, reasons=(st,))
        if st == "断层标定":
            return evaluate("verified", "multi_root", 1.0,
                            reasons=("码表注册语义 × LDZOFBA003 重合≥90% 图面证据",))
        if st == "未解析（码域外）":
            return evaluate("code_read", "single", 1.0, evaluated=False,
                            reasons=("域外码未解析（2026-10-11 摒弃注册兜底"
                                     "——无语义赋值，pending 待裁定）",))
        if st == "字面语义（文本码）":
            return evaluate("verified", "single", 1.0,
                            reasons=("文本码字面即语义（2026-10-09 用户裁定"
                                     "方案一；图面自声明单源）",))
        if st == "裁定噪声（编图错误）":
            return evaluate("adjudicated", adjudicated=True,
                            reasons=("编图错误噪声裁定（T3 用户回路）",))
        if st == "特殊码（独立标定）":
            return evaluate(_GZBD_S.get(conf, "verified"), "multi_root", 1.0,
                            reasons=("码表独立标定（不参与地层接触先验）",))
        if st == "标定通过":
            tier = _GZBD_S.get(conf, "single")
            if tier == "adjudicated":
                return evaluate("adjudicated", adjudicated=True, reasons=("裁定先验",))
            # 2026-09-28 用户裁定（F1）：谱系事实同源——编图参考同一志书/区调
            # 知识源，先验×图面码一致不构成第二独立源 → I=single（从严，memoir
            # 段落落 suspect 审查队列）；推测三检（覆盖/连接/走向=自有数据同类
            # 多证）不在此裁定域 → I=intra_class。
            indep = "intra_class" if conf == "calibrated" else "single"
            return evaluate(tier, indep, 1.0,
                            reasons=(f"先验({conf}) × 图面码核验一致（F1 裁定："
                                     f"谱系同源，I=single 从严）"
                                     if indep == "single" else
                                     "推测界线三检（同类内部多证）",))
        if st == "分歧未裁定":
            return evaluate("single", fit=0.0, reasons=("分歧待裁定",))
        if st.startswith("未覆盖"):
            return evaluate("code_read", "single", 1.0, evaluated=False,
                            reasons=("先验缺口（无假设可评）",))
        return evaluate("code_read", "single", 1.0, evaluated=False,
                        reasons=(f"未识别状态 {st}",))


    for _r in interp:
        emit_columns(_r, _gzbd_shadow(_r), shadow=True)

    # ---------- D. 三层逻辑 L2/L3 后处理（2026-10-04 用户裁定：GZBD 同样
    # 需要标定——boundary_contact_priors 注入的先验知识属 L1 标定算法；
    # L2 码级语义=用户裁定级（注册表 user_confirmed/图幅 decided/映射表
    # user_semantic）> MLE 段级统计精化（主导具体标签 ≥25%）> 注册先验
    # 泛义兜底；L3 全继承：通用/存疑标签段静默继承码义（泛称式升级），
    # 具体分歧段让位+登记（矛盾保持）；「先验建议→」建议型标签为本域
    # 自有的分歧登记机制，保持原样不再重复登记；用户裁定改码/分歧未
    # 裁定/制图误差剔除行绝对不动） ----------
    from pymapgis.semantics.materialize import _SEM_NORM as _GZBD_SEM_NORM
    from ..data import data_path as _dp

    _GENERIC_LBL = {"实测地质", "地质", "", "None", "nan"}  # canon 口径兜底类
    _ROUTED_LBL = {}  # 路由码已全部撤销（2026-10-10：10 断层重合规则、81 冰雪重合规则）
    _reg_codes = {}
    try:
        _reg_codes = (json.load(open(_dp("gzbd_codes.json"), encoding="utf-8"))
                      .get("codes", {}))
    except Exception:
        pass

    _SYN_FOLD = {"推测地质界线": "推测界线",  # 同义折叠（SEM_NORM 补集）
                 # 判定未通过/存疑类标签→折叠入通用桶弃权（2026-10-11 用户裁定：
                 # 界线码义经逻辑标定挣得——判定失败标签不赋语义、不参与码级
                 # MLE 票仓竞争，仅在段级登记待裁定）
                 "界线性质存疑（推测核定不足）": "实测地质",
                 "非推测界线嫌疑（基岩出露与推测矛盾）": "实测地质",
                 "断层接触存疑（重合不足）": "实测地质",
                 "冰雪区界线存疑（重合不足）": "实测地质",
                 "岩性渐变嫌疑未通过（两侧时代/岩性不一致或非岩浆岩）": "实测地质",
                 "脉动接触嫌疑未通过（时代不一致/非岩浆岩/岩性一致）": "实测地质"}

    def _base_lbl(_raw):
        """展示级标签：去「（先验建议…）」后缀取基签，再走 SEM_NORM 归一。"""
        _t = re.sub(r"（先验建议.*?）", "", str(_raw or "")).strip()
        return _GZBD_SEM_NORM.get(_t, _t)

    def _canon(_raw):
        """比较级标签：同义折叠+可选「界线」后缀忽略——防展示变体假分歧
        （侵入接触界线≡侵入接触；推测地质界线≡推测界线）。"""
        _t = _SYN_FOLD.get(_base_lbl(_raw), _base_lbl(_raw))
        return _t[:-2] if _t.endswith("界线") and len(_t) > 2 else _t

    # 映射表用户修改装载（编辑跨轮保留；消费优先级见上）
    _bmap_p = sh.root / f"boundary_semantics_map_{sh.key}.csv"
    _user_bsem, _bmap_note = {}, {}
    if _bmap_p.exists():
        for _, _br in pd.read_csv(_bmap_p, dtype=str).iterrows():
            _c0 = str(_br.get("GZBD") or "").strip()
            _u0 = str(_br.get("user_semantic") or "").strip()
            if _c0 and _u0 and _u0 not in ("nan", "None"):
                _user_bsem[_c0] = _u0
            _n0 = str(_br.get("user_note") or "").strip()
            if _c0 and _n0 and _n0 not in ("nan", "None"):
                _bmap_note[_c0] = _n0
    if _user_bsem:
        print(f"   界线映射表用户修改载入: {len(_user_bsem)} 码")

    # 段级标签分布（比较级 canon 口径键控——变体合并；建议型标签的基签
    # 同样计入统计——全样本票仓）；同 canon 下展示级形态度数（码义须以
    # 展示形出站——渲染 STANDARD_LINE_LAYERS 以展示形键控，canon 形
    # （剥「界线」）会断渲染键）
    _lbl_dist = {}
    _disp = {}
    for _r in interp:
        _c0 = str(_r.get("GZBD_eff") or _r.get("GZBD原码") or "")
        if not _c0:
            continue
        _lbl_dist.setdefault(_c0, {})
        _b0 = _canon(_r.get("标定语义"))
        if _b0 == "岩相接触":
            continue  # 结构规则语义不进码义票仓（2026-10-15 岩相接触案：
            # 两侧同单元/同组段间的结构判定是段级挣得，非码义证据——
            # 否则 43 码义被 104 段岩相翻转、26 段岩浆岩渐变遭 L3 覆盖）
        _lbl_dist[_c0][_b0] = _lbl_dist[_c0].get(_b0, 0) + 1
        _disp.setdefault(_c0, {}).setdefault(_b0, {})
        _d0 = _base_lbl(_r.get("标定语义"))
        _disp[_c0][_b0][_d0] = _disp[_c0][_b0].get(_d0, 0) + 1

    def _disp_of(_c0, _canon_lbl):
        """canon 键 → 展示级标签（该码下同 canon 的最常见展示形）。"""
        _dd = _disp.get(_c0, {}).get(_canon_lbl, {})
        return max(_dd.items(), key=lambda kv: kv[1])[0] if _dd else _canon_lbl

    # L2 码级语义判定
    _code_sem = {}
    for _c0, _dd in _lbl_dist.items():
        _n0 = sum(_dd.values())
        _reg_e = _reg_codes.get(_c0, {})
        _reg_lbl = str(_reg_e.get("meaning") or "")
        _reg_adj = str(_reg_e.get("confidence") or "") == "user_confirmed"
        if _c0 in _ROUTED_LBL:
            _code_sem[_c0] = (_ROUTED_LBL[_c0], "路由码")
        elif _c0 in _user_bsem:
            _code_sem[_c0] = (_user_bsem[_c0], "用户修改")
        elif not _c0.isdigit():
            # 文本码族（用户裁定方案一）：码即语义，不经 MLE
            _code_sem[_c0] = (_c0, "字面语义")
        else:
            # 2026-10-11 用户裁定：界线码义经逻辑标定挣得——**MLE 段级证据
            # 优先于注册表裁定固化**（未必 16=推测界线、43=渐变界线：码义是
            # 标定输出而非注册固定项）；注册表降为 MLE 之下的次兜底（证据
            # 缺席时的定义性参照，national_label 列仍全量保留注册义）
            _spec = {k: v for k, v in _dd.items()
                     if k not in _GENERIC_LBL and "或" not in k}
            if _spec:
                _top, _nt = max(_spec.items(), key=lambda kv: kv[1])
                if _nt / _n0 >= 0.25:
                    _code_sem[_c0] = (_disp_of(_c0, _top), "MLE精化")
                    continue
            # 2026-10-11 用户裁定：界线判别**完全依赖判别逻辑，摒弃注册兜底
            # 机制**——注册表不再提供码义赋值（含裁定固化/注册先验/泛称兜底）；
            # 判定无产出者=未解析（pending），注册义仅存 national_label 参照列
            _code_sem[_c0] = ("", "未解析")

    # L3 全继承（覆盖库例外：用户裁定改码/分歧未裁定/制图误差剔除）
    _b_conflicts = []
    _n_binh = 0
    for _r in interp:
        _r["原标定语义"] = _r.get("标定语义")  # own_label 留档（L1/L2 分层可读）
        if str(_r.get("状态")) in ("用户裁定改码", "分歧未裁定", "制图误差（剔除）"):
            continue
        if _canon(str(_r.get("标定语义") or "")) == "岩相接触":
            continue  # 结构规则挣得语义豁免码义继承（2026-10-15：岩相接触
            # 是段级结构判定产物，不随码级 MLE 语义被覆盖）
        _raw0 = str(_r.get("标定语义") or "")
        if "（先验建议" in _raw0:
            continue  # 建议型标签=本域分歧登记机制，保持原样
        _c0 = str(_r.get("GZBD_eff") or _r.get("GZBD原码") or "")
        _sem0, _src0 = _code_sem.get(_c0, (None, None))
        if not _sem0:
            continue
        _b0 = _canon(_raw0)
        if _b0 == _canon(_sem0):
            continue
        if _b0 in _GENERIC_LBL or "或" in _b0:
            # 通用/存疑标签段静默继承（泛称式升级）
            _r["标定语义"] = _sem0
            _r["证据"] = str(_r.get("证据") or "") + f"；码义继承（{_sem0}）"
            _n_binh += 1
        else:
            # 具体分歧段让位+登记（矛盾保持，证据不因码义消失）
            _b_conflicts.append({
                "idx": str(_r.get("idx")), "GZBD": _c0,
                "issue": f"GZBD={_c0}（{_sem0}）码义全继承",
                "evidence": (f"段级标定 {_b0} 让位码级语义（全继承）——"
                             f"段级证据（{str(_r.get('证据'))[:80]}）"
                             f"如实保留待裁定"),
                "status": "pending_review"})
            _r["标定语义"] = _sem0
            _r["证据"] = str(_r.get("证据") or "") + f"；码义继承（{_sem0}）"
            _n_binh += 1
    if _n_binh:
        print(f"   界线码义继承: {_n_binh} 段")
    if _b_conflicts:
        _new_bc = pd.DataFrame(_b_conflicts)
        _bcp = str(_out(f"_gzbd_conflicts_{sh.key}.csv"))
        if os.path.exists(_bcp):
            # 登记册合并（与 gzeeb 同口径）：已裁定条目（adjudicated）
            # 保留在前，新计算分歧在后
            _old_bc = pd.read_csv(_bcp, dtype=str)
            _keep_bc = _old_bc[_old_bc["status"] == "adjudicated"]
            _new_bc = pd.concat([_keep_bc, _new_bc], ignore_index=True)
        _new_bc.to_csv(_bcp, index=False, encoding="utf-8-sig")
        print(f"   界线码义分歧登记: {len(_b_conflicts)} 段 → "
              f"_gzbd_conflicts_{sh.key}.csv")
    else:
        _bcp = sh.root / f"_gzbd_conflicts_{sh.key}.csv"
        if _bcp.exists():
            _old_bc = pd.read_csv(_bcp, dtype=str)
            _keep_bc = _old_bc[_old_bc["status"] == "adjudicated"]
            if len(_keep_bc):
                _keep_bc.to_csv(_bcp, index=False, encoding="utf-8-sig")
            else:
                _bcp.unlink()  # 清零清理陈旧件（防误读，与 gzeeb 兜底件同口径）

    # 界线编码-地质语义映射表出站（全码一表；user_semantic 为用户修改
    # 列——编辑跨轮保留，修改-再转化回路与 GZEEB 同构：编辑 → 重跑
    # calibrate-gzbd → pipeline --skip-convert --skip-calibrate-stages）
    _bmap_rows = []
    for _c0 in sorted(_lbl_dist):
        _dd = _lbl_dist[_c0]
        _n0 = sum(_dd.values())
        _sem0, _src0 = _code_sem[_c0]
        _reg_lbl = str(_reg_codes.get(_c0, {}).get("meaning") or "")
        _term0 = str(_reg_codes.get(_c0, {}).get("geosciml_contacttype") or "")
        _nt0 = _dd.get(_canon(_sem0), 0)
        if _src0 in ("路由码",):
            _conf0 = "路由码"
        elif _src0 == "用户裁定(注册)":
            _conf0 = "裁定固化"
        elif _src0 == "用户修改":
            _conf0 = "用户修改"
        elif _src0 == "未解析":
            _conf0 = "未解析（无判定证据）"
        else:
            _share = _nt0 / _n0 if _n0 else 0.0
            _conf0 = (f"强证({_n0}段·{_share * 100:.0f}%)"
                      if _n0 >= 20 and _share >= 0.5 else
                      f"中证({_n0}段·{_share * 100:.0f}%)"
                      if _n0 >= 10 or (_n0 >= 5 and _share >= 0.25) else
                      f"薄证({_n0}段·{_share * 100:.0f}%)")
        _bmap_rows.append({
            "GZBD": _c0, "segs": _n0,
            "semantic": _sem0, "source": _src0, "confidence": _conf0,
            "national_label": _reg_lbl, "contactType_term": _term0,
            "label_distribution": "；".join(
                f"{k}×{v}" for k, v in sorted(_dd.items(), key=lambda x: -x[1])),
            "divergent_segs": sum(1 for _r in interp
                                if str(_r.get("GZBD_eff") or _r.get("GZBD原码") or "") == _c0
                                and "（先验建议" in str(_r.get("原标定语义") or "")),
            "user_semantic": _user_bsem.get(_c0, ""),
            "user_note": _bmap_note.get(_c0, "")})
    pd.DataFrame(_bmap_rows).to_csv(_bmap_p, index=False, encoding="utf-8-sig")
    print(f"   界线编码-地质语义映射表: {len(_bmap_rows)} 码 → {_bmap_p.name}")

    out_df = pd.DataFrame(interp)
    out_df.to_csv(_out("_gzbd_semantic_interpretation.csv"), index=False, encoding="utf-8-sig")
    # 域外码未解析登记（审计存档；2026-10-11 摒弃注册兜底——原特殊码兜底
    # 档案同址，pending.py 裁定单消费）
    _fb = out_df[out_df["状态"] == "未解析（码域外）"]
    _fb.to_csv(_out("_gzbd_special_fallback.csv"), index=False,
               encoding="utf-8-sig")
    if len(_fb):
        print(f"    域外码未解析登记（审计存档）：{len(_fb)} 段 → "
              f"_gzbd_special_fallback.csv")
    print("C. 语义解释完成：")
    print(out_df["状态"].value_counts().to_string())

    # ---------- 年轻侧对账（志书 younger × 年代秩） ----------
    audit = []
    for _, r in rep.iterrows():
        if r["verdict"] not in ("标定通过", "分歧") or not r["young_side"]:
            continue
        la = [(_unit_age_rank(c) or 0) for c in re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(r["left"]))]
        ra = [(_unit_age_rank(c) or 0) for c in re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(r["right"]))]
        if not la or not ra:
            continue
        age_side = "left" if max(la) > max(ra) else ("right" if max(ra) > max(la) else "")
        audit.append({"idx": int(r["idx"]), "gzbd": r["gzbd"],
                      "先验年轻侧": r["young_side"], "年代年轻侧": age_side,
                      "一致": r["young_side"] == age_side,
                      "left": r["left"], "right": r["right"]})
    sa = pd.DataFrame(audit)
    if len(sa):
        sa["对账"] = sa.apply(
            lambda r: "年代不可判（先验补位）" if r["年代年轻侧"] == ""
            else ("一致" if r["先验年轻侧"] == r["年代年轻侧"] else "冲突"), axis=1)
        sa.to_csv(_out("_gzbd_side_audit.csv"), index=False, encoding="utf-8-sig")
        print(f"D. 年轻侧对账：{len(sa)} 段")
        print(sa["对账"].value_counts().to_string())
    print()
    print("输出: _boundary_sides.csv / _gzbd_calibration_report.csv /")
    print("      _gzbd_semantic_interpretation.csv / _gzbd_side_audit.csv")


    return {
        "sides": len(sides),
        "verdicts": rep["verdict"].value_counts().to_dict(),
        "status": out_df["状态"].value_counts().to_dict(),
        "gaps": len(gap_df),
        "out_dir": str(_outdir),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c calibrate-gzbd")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default=None, help="输出目录（缺省=图幅 root）")
    args = ap.parse_args()
    stats = calibrate_boundaries(args.sheet, out_dir=args.out)
    print("标定完成:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
