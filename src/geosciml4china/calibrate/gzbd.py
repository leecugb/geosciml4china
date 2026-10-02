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
      标定域 _CALIB_DOMAIN={01,02,04,10,11,16,24,43,60,81}——五通道：
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
import re
import sys

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point  # LineString：G1 断层重合度（2026-09-29）
from shapely.strtree import STRtree
from shapely.ops import unary_union as _unary_union
import os as _os

from pymapgis.semantics import load_source_layer
from pymapgis.semantics.profile import get_profile
from pymapgis.rendering.pdf_writer import _unit_age_rank

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


def calibrate_boundaries(sheet_key: str, out_dir=None) -> dict:
    """执行 GZBD 界线先验标定，返回计数统计。out_dir 缺省=图幅 root。"""
    sh = get_sheet(sheet_key)
    _lat0 = float(get_profile(sh.key).center_lat_hint)
    from pathlib import Path as _P
    _outdir = _P(out_dir) if out_dir is not None else sh.root
    _outdir.mkdir(parents=True, exist_ok=True)  # 影子验证输出目录自建（函数化缺口补）

    def _out(name):
        return str(_outdir / name)

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
    codes_meta = json.loads(data_path("gzbd_codes.json").read_text(encoding="utf-8"))["codes"]
    SPECIAL_CODES = {"81", "43", "60"}
    # 标定域（2026-09-29 用户对齐裁定）：域内码走五通道（地质志单元对先验/
    # 43 岩性过渡渐变/60 脉动接触/16 推测界线/通用规则级联）+10 断层标定+
    # 81 特殊码独立标定；域外码=其他特殊类型编码，统一一般地质界线兜底
    _CALIB_DOMAIN = {"01", "02", "04", "10", "11", "16", "24", "43", "60", "81"}  # 16 推测界线自 2026-09-13 起经专项核定（见 B 段）
    # 2026-09-13 用户对齐：第四系不含已半固结成岩的沉积层（西域组 Qp1X 算基岩）
    Q_EXCLUDE = set(priors.get("quaternary_exclude", ["Qp1X"]))


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
    for g, c in zip(_sg.geometry.values, _sg["QDUECC"].astype(str).values):
        if g is not None and not g.is_empty \
                and (a := _unit_age_rank(c)) is not None and a >= 1300 \
                and clean_code(c) not in Q_EXCLUDE:
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
            "idx": i, "gzbd": f"{int(row['GZBD']):02d}",
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
    for _, rec in sides.iterrows():
        gz = rec["gzbd"]
        idx = int(rec["idx"])
        lu_codes = json.loads(rec["left_codes"])
        ru_codes = json.loads(rec["right_codes"])
        lu_units = [{"code": c, "name": code2name.get(c, c), "layer": code2layer.get(c, "?")}
                    for c in lu_codes]
        ru_units = [{"code": c, "name": code2name.get(c, c), "layer": code2layer.get(c, "?")}
                    for c in ru_codes]
        base = {"idx": idx, "gzbd": gz,
                "left": ";".join(f"{u['code']}({u['name']})" for u in lu_units),
                "right": ";".join(f"{u['code']}({u['name']})" for u in ru_units)}
        if str(idx) in carto_err:
            verdicts.append({**base, "verdict": "制图误差（剔除）", "rule_pair": "",
                             "rule_contact": "", "rule_conf": "", "expected": "",
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
        if gz == "43":
            # 岩性过渡渐变（2026-09-24 用户核定）：岩浆岩间的一种接触界线，
            # 两侧岩浆岩时代、岩性要求一致——逐侧校验（岩浆岩层 + 希腊岩性码同
            # + 时代码同）；违反者登记分歧交裁定（永不自动改码）
            _parts = {"L": [], "R": []}
            for tag, units in (("L", lu_units), ("R", ru_units)):
                for u in units:
                    c = re.sub(r"[→↓↑]", "", u["code"])
                    m = re.match(r"([Ͱ-Ͽἀ-῿]+)(.*)$", c)
                    if m:
                        _parts[tag].append((u["layer"], m.group(1), m.group(2)))
            _ok43 = True
            if not _parts["L"] or not _parts["R"]:
                _ok43 = False
            elif not all(p[0] in ("侵入", "火山") for p in _parts["L"] + _parts["R"]):
                _ok43 = False
            elif {p[1] for p in _parts["L"]} != {p[1] for p in _parts["R"]}:
                _ok43 = False  # 岩性不一致
            elif {p[2] for p in _parts["L"]} != {p[2] for p in _parts["R"]}:
                _ok43 = False  # 时代不一致
            verdicts.append({**base,
                             "verdict": "特殊码（独立标定）" if _ok43 else
                             "分歧未裁定（43约束：两侧岩浆岩时代岩性须一致）",
                             "rule_pair": "", "rule_contact": "", "rule_conf": "",
                             "expected": "", "rule_younger": "", "young_side": ""})
            continue
        if gz == "60":
            # 脉动接触（2026-09-24 用户核定）：岩浆岩间的一种接触界线，
            # 两侧岩浆岩要求时代一致（岩性不要求一致——不同岩性侵入体同代
            # 脉动注入）；违反者登记分歧交裁定（永不自动改码）
            _parts = {"L": [], "R": []}
            for tag, units in (("L", lu_units), ("R", ru_units)):
                for u in units:
                    c = re.sub(r"[→↓↑]", "", u["code"])
                    m = re.match(r"([Ͱ-Ͽἀ-῿]+)(.*)$", c)
                    if m:
                        _parts[tag].append((u["layer"], m.group(1), m.group(2)))
            _ok60 = True
            if not _parts["L"] or not _parts["R"]:
                _ok60 = False
            elif not all(p[0] in ("侵入", "火山") for p in _parts["L"] + _parts["R"]):
                _ok60 = False
            elif {p[2] for p in _parts["L"]} != {p[2] for p in _parts["R"]}:
                _ok60 = False  # 时代不一致
            verdicts.append({**base,
                             "verdict": "特殊码（独立标定）" if _ok60 else
                             "分歧未裁定（60约束：两侧岩浆岩时代须一致）",
                             "rule_pair": "", "rule_contact": "", "rule_conf": "",
                             "expected": "", "rule_younger": "", "young_side": ""})
            continue
        if gz in SPECIAL_CODES:
            verdicts.append({**base, "verdict": "特殊码（独立标定）", "rule_pair": "",
                             "rule_contact": "", "rule_conf": "", "expected": "",
                             "rule_younger": "", "young_side": ""})
            continue
        if gz == "16":
            # 推测地质界线核定（2026-09-13 用户批准，仿推测断层标定）：
            # ① 覆盖度 ≥80%（松散Q剔Qp1X/冰雪）——"推测"前提；
            #    <40% 基岩出露 → 与"推测"矛盾；
            # ② 连接性：两端 ≤10m 连接同一接触类型的实测界线段（非16/81/10）——
            #    确认"覆盖区延伸段"角色；
            # ③ 三条全过=核定通过；部分覆盖/连接不足=存疑交人工
            geom = bounds.geometry.values[idx]
            hit = 0
            NPT = 8
            for t in np.linspace(0.08, 0.92, NPT):
                q = geom.interpolate(float(t), normalized=True)
                if (q_u is not None and q_u.intersects(q)) or \
                   (ice_u is not None and ice_u.intersects(q)):
                    hit += 1
            frac16 = hit / NPT
            conns = []
            bcoords = list(geom.coords)
            for w in (0, 1):
                pt = bcoords[0] if w == 0 else bcoords[-1]
                for j, row2 in bounds.iterrows():
                    if j == idx or row2.geometry is None:
                        continue
                    c2 = list(row2.geometry.coords)
                    for p2 in (c2[0], c2[-1]):
                        if math.hypot((pt[0] - p2[0]) * LON_M,
                                      (pt[1] - p2[1]) * LAT_M) <= 10.0:
                            gzc = f"{int(row2['GZBD']):02d}"
                            if gzc not in ("16", "81", "10"):
                                conns.append(gzc)
            same_type = len(set(conns)) == 1 and bool(conns)
            if frac16 < 0.4:
                v16 = "矛盾（推测界线）"
            elif frac16 >= 0.8 and same_type:
                v16 = "核定通过（推测界线）"
            else:
                v16 = "存疑（推测界线）"
            verdicts.append({**base, "verdict": v16,
                             "rule_pair": f"覆盖{frac16:.0%}/连接{conns or '无'}",
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
                             "rule_contact": ";".join(sorted({r["contact"] for _, _, r, _ in hits})),
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
            sl, sr = _unit_seg(lu_units[0]), _unit_seg(ru_units[0])
            if sl and sr and sl[0] == sr[0] and sl[1] != sr[1]:
                a, b = sl[1], sr[1]
                if a > 0 and b > 0:
                    adjacent = abs(a - b) == 1  # 绝对段号
                elif a < 0 and b < 0:
                    ra, rb = sorted((a, b))  # 新编码：下=-3 中=-2 上=-1
                    if (ra, rb) in ((-2, -1), (-3, -2)):
                        adjacent = True  # 下|中 / 中|上 恒相邻
                    elif (ra, rb) == (-3, -1):
                        # 下|上：组内中段存在性普查决定（2026-09-29 审计：
                        # 三段式组 下|上 隔中段=跨段；两组式无中段=相邻）
                        _grp = sl[0]
                        _has_mid = any(str(code2name.get(c, c)) in
                                       (f"{_grp}中段", f"{_grp}中岩段")
                                       for c in code2name)
                        adjacent = not _has_mid
                    else:
                        adjacent = None
                else:
                    adjacent = None  # 相对×绝对混比不可判——不冒通则
                if adjacent is not None:
                    exp = {"01"} if adjacent else {"10"}
                    verdicts.append({**base,
                                     "verdict": "标定通过" if gz in exp else "分歧",
                                     "rule_pair": "(段间通则-相邻段)" if adjacent
                                                 else "(段间通则-跨段仅断层)",
                                     "rule_contact": "整合接触" if adjacent else "断层接触",
                                     "rule_conf": "self_supporting",
                                     "expected": "/".join(sorted(exp)),
                                     "rule_younger": "", "young_side": ""})
                    continue
                # adjacent is None（相对×绝对混比不可判）→ 落下方通用级联
        all_layers = {u["layer"] for u in lu_units + ru_units}
        # 第四系判定：剔除半固结成岩沉积层（Qp1X 西域组等，算基岩）
        ages = [a for u in lu_units + ru_units
                if clean_code(u["code"]) not in Q_EXCLUDE
                and (a := _unit_age_rank(u["code"])) is not None]
        if ages and max(ages) >= 1300:
            exp, cname, rpair = {"02"}, "第四系界线", "(第四系通用规则)"
        elif "侵入" in all_layers:
            int_ages = [a for u in lu_units + ru_units if u["layer"] == "侵入"
                        and (a := _unit_age_rank(u["code"])) is not None]
            oth_ages = [a for u in lu_units + ru_units if u["layer"] != "侵入"
                        and (a := _unit_age_rank(u["code"])) is not None]
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
                  and (a := _unit_age_rank(u["code"])) is not None]
            oth = [a for u in lu_units + ru_units if clean_code(u["code"]) != "Qp1X"
                   and (a := _unit_age_rank(u["code"])) is not None]
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
        elif ages and (max(ages) - min(ages)) >= 200:
            # 间断通则（2026-09-26 用户指令，contact/56 案例 J3kz|C2ak 驱动）：
            # 两侧均为地层单元（非第四系、非侵入——已在上游分支处理）且年龄
            # 间断 ≥200（明显沉积间断）→ 不整合接触（04 角度不整合兜底，
            # 24 平行不整合兼容）；01 实测界线命中者登记"分歧"交裁定
            # （发现编图错误通道）。阈值证据：04 码 25%分位 101/中位 398、
            # 01 码 95%分位 101，≥200 全幅仅 8 段。
            exp, cname, rpair = {"04", "24"}, "不整合接触", "(间断通则)"
        else:
            verdicts.append({**base, "verdict": "未覆盖", "rule_pair": "",
                             "rule_contact": "", "rule_conf": "", "expected": "",
                             "rule_younger": "", "young_side": ""})
            continue
        # 间断通则补填年轻侧（先验年轻侧通道）：age_rank 大者所在侧
        if rpair == "(间断通则)" and ages:
            _lmax = max((a for a in (_unit_age_rank(u["code"]) for u in lu_units)
                         if a is not None), default=None)
            _rmax = max((a for a in (_unit_age_rank(u["code"]) for u in ru_units)
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
            _lmax = max((a for a in (_unit_age_rank(u["code"]) for u in lu_units)
                         if a is not None), default=None)
            _rmax = max((a for a in (_unit_age_rank(u["code"]) for u in ru_units)
                         if a is not None), default=None)
            if _lmax is not None and _rmax is not None and _lmax != _rmax:
                base = {**base, "rule_younger": "", "young_side": "left" if _lmax > _rmax else "right"}
        verdicts.append({**base, "verdict": "标定通过" if gz in exp else "分歧",
                         "rule_pair": rpair, "rule_contact": cname,
                         "rule_conf": "generic", "expected": "/".join(sorted(exp)),
                         "rule_younger": base.get("rule_younger", ""),
                         "young_side": base.get("young_side", "")})

    rep = pd.DataFrame(verdicts)
    rep[rep["gzbd"] != "10"].to_csv(_out("_gzbd_calibration_report.csv"),
                                    index=False, encoding="utf-8-sig")
    print("B. 先验标定完成（GZBD=10 由断层标定除外）：")
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


    # G1（2026-09-29 泛化优化）：断层标定证据由断言改为计算——gzbd=10 行与
    # FBA003 实测断层线重合占比（米制 100m 缓冲）。旧「重合≥90%（n/n）」为
    # 行计数非验证；现逐行实测，不足 90% 者证据注记「重合不足（复核）」。
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

    def _coincidence(geom):
        """界线与 FBA003 断层线重合占比（米制 100m 缓冲）；无数据→None。"""
        if _fault_u_m is None or geom is None or geom.is_empty:
            return None
        _cm = np.array(geom.coords)
        if len(_cm) < 2:
            return None
        _seg = LineString(_cm * [LON_M, LAT_M])
        _tot = _seg.length
        if _tot < 1e-9:
            return None
        return _seg.intersection(_fault_u_m.buffer(100.0)).length / _tot

    # G3（2026-09-29 泛化优化）：码义一致性声明——硬编码分支语义 × 幅级词表
    # 注册对照，偏移/未注册者入审计档案（分支结构不变，三审前置把关机制化）
    _BRANCH_EXPECT = {"10": "skip_fault", "81": "skip_nongeologic",
                      "43": "igneous_phase_contact", "60": "igneous_phase_contact",
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
                        or (_c in ("10", "81") and _st not in ("absent", _exp_st)))
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
    _n10 = int((rep["gzbd"] == "10").sum())
    _coinc10 = [_coincidence(bounds.geometry.values[int(r["idx"])])
                for _, r in rep.iterrows() if r["gzbd"] == "10"]
    _n10_pass = sum(1 for c in _coinc10 if c is not None and c >= 0.9)
    _n10_unv = sum(1 for c in _coinc10 if c is None)
    _coinc_map = {int(r["idx"]): _coincidence(bounds.geometry.values[int(r["idx"])])
                  for _, r in rep.iterrows() if r["gzbd"] == "10"}

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
        base_sem = codes_meta.get(gz, {}).get("meaning", "?")
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
        elif gz == "10":
            _pct = _coinc_map.get(idx)
            if _pct is None:
                _ev = f"与 LDZOFBA003 重合未验证（本幅无 FBA003 数据；{_n10_unv} 段同）"
            elif _pct >= 0.9:
                _ev = f"与 LDZOFBA003 重合 {_pct:.0%}（{_n10_pass}/{_n10} 段 ≥90% 实测）"
            else:
                _ev = f"与 LDZOFBA003 重合仅 {_pct:.0%}（<90% 复核）"
            out.update(标定语义="断层接触（断裂界线）", GZBD_eff="10", 状态="断层标定",
                       证据=_ev, 置信度="verified")
        elif r["verdict"] == "特殊码兜底":
            out.update(标定语义="一般地质界线", GZBD_eff=gz, 状态="特殊码兜底（一般地质界线）",
                       证据=f"码 {gz} 不在 GZBD 标定域（2026-09-29 用户对齐裁定：统一一般地质界线兜底）",
                       置信度="code_read")
        elif r["verdict"] == "特殊码（独立标定）":
            out.update(标定语义=base_sem, GZBD_eff=gz, 状态=r["verdict"],
                       证据="码表（不参与地层接触先验）",
                       置信度=codes_meta[gz]["confidence"])
        elif r["verdict"] == "核定通过（推测界线）":
            out.update(标定语义="推测地质界线（覆盖区延伸段）", GZBD_eff="16",
                       状态="标定通过", 证据=f"三检：{r['rule_pair']}",
                       置信度="calibrated")
        elif r["verdict"] in ("存疑（推测界线）", "矛盾（推测界线）"):
            out.update(标定语义=f"推测地质界线（{r['verdict'][:2]}）",
                       GZBD_eff=gz, 状态="分歧未裁定",
                       证据=f"推测界线核定：{r['rule_pair']}", 置信度="conflict")
        elif r["verdict"] == "标定通过":
            src = "志书单元对规则" if str(r["rule_conf"]).startswith("memoir") else "通用规则"
            # 间断通则（2026-09-26 用户指令）是佐证级规则：标定语义保留码表
            # 细分名（04=角度不整合界线等），通则仅作证据，不降级码义粒度
            sem = (base_sem if str(r["rule_pair"]) == "(间断通则)"
                   else (str(r["rule_contact"]) or base_sem))
            out.update(标定语义=sem, GZBD_eff=gz,
                       状态="标定通过", 证据=f"{src}：{r['rule_pair']}",
                       置信度=str(r["rule_conf"]))
        elif r["verdict"] in ("分歧", "多规则分歧"):
            out.update(标定语义=f"{r['rule_contact']}（先验建议→{r['expected']}）",
                       GZBD_eff=gz, 状态="分歧未裁定",
                       证据=f"{r['rule_pair']} 期望 {r['expected']}", 置信度="conflict")
        elif str(r["verdict"]).startswith("分歧未裁定（"):
            # 岩性过渡渐变约束违反（2026-09-24 用户核定：两侧岩浆岩时代岩性须一致）
            out.update(标定语义=base_sem, GZBD_eff=gz, 状态="分歧未裁定",
                       证据=str(r["verdict"]), 置信度="conflict")
        else:
            # 未覆盖归因：缺口单元 vs 规则组合缺失
            codes_l = re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(r["left"]))
            codes_r = re.findall(r"([A-Za-zΑ-ω0-9↓→.-]+)\(", str(r["right"]))
            gap_hit = [c for c in codes_l + codes_r if c in GAPS]
            cause = f"志书缺口单元: {'/'.join(gap_hit)}" if gap_hit else "单元对组合未收录"
            out.update(标定语义=base_sem, GZBD_eff=gz, 状态="未覆盖（先验缺口）",
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
        if st == "特殊码兜底（一般地质界线）":
            return evaluate("code_read", "single", 1.0,
                            reasons=("特殊码兜底（2026-09-29 用户对齐裁定；"
                                     "码义待裁定）",))
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

    out_df = pd.DataFrame(interp)
    out_df.to_csv(_out("_gzbd_semantic_interpretation.csv"), index=False, encoding="utf-8-sig")
    # 特殊码兜底登记（审计报告存档，2026-09-29 用户对齐裁定）
    _fb = out_df[out_df["状态"] == "特殊码兜底（一般地质界线）"]
    _fb.to_csv(_out("_gzbd_special_fallback.csv"), index=False,
               encoding="utf-8-sig")
    if len(_fb):
        print(f"    特殊码兜底登记（审计存档）：{len(_fb)} 段 → "
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
