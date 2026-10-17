# -*- coding: utf-8 -*-
"""断层辅助点旋转约定解析与变体码自动挣得（2026-10-12 用户裁定链产品化）。

glyph0（初始样式）×旋转约定 = **图幅级变量**，权威源 = 该幅 MapGIS 图形库
Subgraph.lib（新疆115 仅 1/115 幅随附，pymapgis 无 SLIB 读取器）。本模块为
**通道 B**：多约定扫描 + 几何一致性推断，对池中未解析符号码自动挣得
tick（双短线变体）/ arrow（倾向箭头变体）身份——**inferred 级**，机挣册
登记；verified 仍须用户图面核验/裁定（准确性优先总纲）。

**红线（裁定在案）**：
  · 约定解析**永不跨幅继承**——每（幅,码）独立挣得；
  · **正典码在场禁变体化**：池中有 1281 则不挣 tick、有 1894/b 码则不挣
    arrow（1283/1281 案——变体化不得旁路角色歧义闸）；
  · 唯一干净约定才转正；多约定同洁/全不洁/角色证据打平 → **存疑留池**
    （五类合法集闸登记交裁定）——宁疑勿冒进。

挣得闸口（保守，经 43+7 幅实测校准）：n≥2；⊥偏差中位 ≤10° 且 ≥80% 点
≤15°；距离中位 ∈ [50,500]m（辅助点测量带域）；角色区分证据——tick=
同断层同侧同角（Δφ≤5°）成对率 ≥50%；arrow=倾角注记 300m 邻近率 ≥50%
且箭头侧=点侧一致率 ≥80%。双向着火时比较角色证据强度，打平存疑。

几何公式与全舰队实测脚本同源（_1519_fleet_conv.py / _1894_fleet_perp.py）：
走向=链垂足 ±200m 窗口向量方位（atan2(dx,dy)，mod 180）；⊥偏差=
|(θ−strike) mod 180 − 90|；侧一致=窗口向量×(垂足→点) 与 窗口向量×箭头向量
两叉积同号。

产物：`data/fault_aux_code_earned_<key>.json`（机挣册，与用户裁定册
`fault_aux_code_semantics_<key>.json` 分立；每 run 重挣重写、幂等；
用户册在场的码跳过不挣）。
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from shapely.ops import substring

# 8 约定空间：sense × base（glyph0 0° 方位）。绘制方位角 θ =
# (base − φ) % 360（逆时针 CCW）或 (base + φ) % 360（顺时针 CW）。
# 线状符号 mod 180 坍缩为 4 等价类（N-CCW≡S-CCW、E-CCW≡W-CCW、
# N-CW≡S-CW、E-CW≡W-CW）——tick 用代表集，arrow 方向敏感用全集。
CONVENTIONS = {
    "N-CCW": ("CCW", 0.0), "E-CCW": ("CCW", 90.0),
    "S-CCW": ("CCW", 180.0), "W-CCW": ("CCW", 270.0),
    "N-CW": ("CW", 0.0), "E-CW": ("CW", 90.0),
    "S-CW": ("CW", 180.0), "W-CW": ("CW", 270.0),
}
_LINE_CONV = ("N-CCW", "N-CW", "E-CCW", "E-CW")

PERP_MED_TOL = 10.0     # ⊥偏差中位容差（1894 舰队实测 1.7–7.0°）
PERP_PT_TOL = 15.0      # 逐点 ⊥容差
PERP_PT_FRAC = 0.8      # ≥80% 点须在逐点容差内
DIST_BAND = (50.0, 500.0)   # 距离中位测量带域（钩线带 [50,500] 同源）
OFFLINE_M = 1000.0      # 超此距不参与统计（脱线疑点另走距离闸）
PAIR_DPHI = 5.0         # tick 同角对判定（双短线同角实测 0.1–1.7°）
PAIR_MIN_FRAC = 0.5     # tick 成对率下限
ANN_NEAR_M = 300.0      # arrow 倾角注记邻近半径
ANN_MIN_FRAC = 0.5      # arrow 注记邻近率下限
SIDE_MIN_FRAC = 0.8     # arrow 侧一致率下限（1894 舰队实测 85–100%）


def drawn_az(conv: str, phi: float) -> float:
    """约定码 → 绘制方位角（顺时针从北，度）。"""
    sense, base = CONVENTIONS[conv]
    return (base - phi) % 360.0 if sense == "CCW" else (base + phi) % 360.0


def _med(v):
    v = sorted(v)
    n = len(v)
    return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2) if v else None


def _strike_side(chain_m, pt_m, win=200.0):
    """链垂足 ±win 窗走向（方位 mod180）+点侧别+窗口向量+垂足。

    返回 dict(strike, side, wvec, foot)；退化返回 None。
    实体链可能为 MultiLineString（同实体多段不连续）——取最近部件。"""
    if chain_m.geom_type == "MultiLineString":
        chain_m = min(chain_m.geoms, key=lambda g: g.distance(pt_m))
    s = chain_m.project(pt_m)
    sub = substring(chain_m, max(0.0, s - win), min(chain_m.length, s + win))
    cc = list(sub.coords)
    if len(cc) < 2:
        cc = list(chain_m.coords)
    dx, dy = cc[-1][0] - cc[0][0], cc[-1][1] - cc[0][1]
    if dx == 0 and dy == 0:
        return None
    fp = chain_m.interpolate(s)
    return {
        "strike": math.degrees(math.atan2(dx, dy)) % 180.0,
        "side": math.copysign(
            1, dx * (pt_m.y - fp.y) - dy * (pt_m.x - fp.x) + 1e-12),
        "wvec": (dx, dy), "foot": fp,
    }


def _perp_dev(theta, strike):
    """绘制方位与走向的垂直偏差（0=严格垂直）。"""
    return abs(((theta - strike) % 180.0) - 90.0)


def _arrow_side_match(row, theta):
    """箭头指向侧 = 点所在侧：窗口向量×箭头向量 与 窗口向量×(垂足→点) 同号。"""
    dx, dy = row["wvec"]
    ax_, ay_ = math.sin(math.radians(theta)), math.cos(math.radians(theta))
    side_arrow = math.copysign(1, dx * ay_ - dy * ax_ + 1e-12)
    return bool(side_arrow == row["side"])


def earn_aux_codes(sh, aux_cat, chains_m, pm, user_reg, prof, log=print):
    """约定扫描挣得主入口。

    返回 (tick_set, arrow_map, conv_map)：
      tick_set  {code_str}         —— 双短线变体（归一 1281）
      arrow_map {code_str: conv}   —— 倾向箭头变体（归一 1894）
      conv_map  {code_str: (sense, base)} —— 供 dip_az 按码换算
    机挣册同步重写（data/fault_aux_code_earned_<key>.json）。
    """
    tick_out, arrow_out, conv_out = set(), {}, {}
    if not len(aux_cat) or not chains_m:
        return tick_out, arrow_out, conv_out

    pool_codes = {int(x) for x in aux_cat["symbol_no"]}
    canon_tick = 1281 in pool_codes
    canon_arrow = (1894 in pool_codes) or (int(prof.b_symbol_raw) in pool_codes)
    # 倾角注记池（symbol_no=0 文本点）——arrow 角色证据
    ann_pts = [pm(r.geometry) for _, r in aux_cat.iterrows()
               if int(r["symbol_no"]) == 0 and r.geometry is not None]

    user_codes = {int(c) for c in user_reg if str(c).lstrip("-").isdigit()}
    cand = sorted(pool_codes - {0, 1281, 1894, int(prof.b_symbol_raw)}
                  - user_codes)
    entries = {}
    for code in cand:
        rows = []
        for _, r in aux_cat.iterrows():
            if int(r["symbol_no"]) != code or r.geometry is None:
                continue
            try:
                phi = float(r["angle"])
            except (TypeError, ValueError):
                continue
            pt_m = pm(r.geometry)
            d_best, fid_best = None, None
            for fid, ch in chains_m.items():
                d = ch.distance(pt_m)
                if d_best is None or d < d_best:
                    d_best, fid_best = d, fid
            if d_best is None or d_best > OFFLINE_M:
                continue
            ss = _strike_side(chains_m[fid_best], pt_m)
            if ss is None:
                continue
            rows.append({"phi": phi, "dist": d_best, "fid": fid_best,
                         "pt": pt_m, **ss})
        n = len(rows)
        if n < 2:
            continue  # 单点不立约定——存疑留池
        d_med = _med([r["dist"] for r in rows])
        if not (DIST_BAND[0] <= d_med <= DIST_BAND[1]):
            continue  # 距离中位出测量带域——非辅助点身份，存疑留池

        # 角色证据：tick 成对率 / arrow 注记邻近率
        n_pair = 0
        for r in rows:
            for q in rows:
                if q is r or q["fid"] != r["fid"] or q["side"] != r["side"]:
                    continue
                dphi = abs(r["phi"] - q["phi"]) % 360.0
                if min(dphi, 360.0 - dphi) <= PAIR_DPHI:
                    n_pair += 1
                    break
        pair_rate = n_pair / n
        ann_rate = (sum(1 for r in rows
                        if any(r["pt"].distance(a) <= ANN_NEAR_M
                               for a in ann_pts)) / n) if ann_pts else 0.0

        # 约定扫描：tick 线状 4 等价类；arrow 方向敏感 8 全集
        line_clean = []
        for cv in _LINE_CONV:
            devs = [_perp_dev(drawn_az(cv, r["phi"]), r["strike"])
                    for r in rows]
            if (_med(devs) <= PERP_MED_TOL
                    and sum(1 for d in devs if d <= PERP_PT_TOL) / n
                    >= PERP_PT_FRAC):
                line_clean.append((cv, devs))
        arrow_clean = []
        for cv in CONVENTIONS:
            devs = [_perp_dev(drawn_az(cv, r["phi"]), r["strike"])
                    for r in rows]
            if not (_med(devs) <= PERP_MED_TOL
                    and sum(1 for d in devs if d <= PERP_PT_TOL) / n
                    >= PERP_PT_FRAC):
                continue
            sm = sum(1 for r in rows
                     if _arrow_side_match(r, drawn_az(cv, r["phi"])))
            if sm / n >= SIDE_MIN_FRAC:
                arrow_clean.append((cv, devs))

        tick_fire = (not canon_tick) and len(line_clean) == 1 \
            and pair_rate >= PAIR_MIN_FRAC
        arrow_fire = (not canon_arrow) and len(arrow_clean) == 1 \
            and ann_rate >= ANN_MIN_FRAC
        if tick_fire and arrow_fire:
            # 双向着火：角色证据强者胜；打平 → 存疑（宁疑勿冒进）
            if pair_rate > ann_rate:
                arrow_fire = False
            elif ann_rate > pair_rate:
                tick_fire = False
            else:
                continue
        if tick_fire:
            cv, devs = line_clean[0]
            tick_out.add(str(code))
            entries[str(code)] = _entry(
                "tick_variant", "1281", cv, n, devs, d_med,
                pair_rate=pair_rate)
            log(f"   变体挣得：{code} → 双短线变体（{cv}，n={n}，"
                f"⊥中位 {_med(devs):.1f}°，成对率 {pair_rate:.0%}，"
                f"距中位 {d_med:.0f}m）inferred")
        elif arrow_fire:
            cv, devs = arrow_clean[0]
            arrow_out[str(code)] = cv
            conv_out[str(code)] = CONVENTIONS[cv]
            entries[str(code)] = _entry(
                "arrow_variant", "1894", cv, n, devs, d_med,
                ann_rate=ann_rate)
            log(f"   变体挣得：{code} → 倾向箭头变体（{cv}，n={n}，"
                f"⊥中位 {_med(devs):.1f}°，注记邻近率 {ann_rate:.0%}，"
                f"距中位 {d_med:.0f}m）inferred")
        # 其余：存疑留池，五类合法集闸照常登记

    _write_earned(sh, entries, log)
    return tick_out, arrow_out, conv_out


def _entry(role, family, conv, n, devs, d_med, pair_rate=None,
           ann_rate=None):
    ev = {"n": n, "dev_perp_median_deg": round(_med(devs), 2),
          "dev_le15_frac": round(
              sum(1 for d in devs if d <= PERP_PT_TOL) / len(devs), 3),
          "dist_median_m": round(d_med, 1)}
    if pair_rate is not None:
        ev["pair_rate"] = round(pair_rate, 3)
    if ann_rate is not None:
        ev["annotation_rate"] = round(ann_rate, 3)
    return {
        "role": role, "family": family, "rotation_convention": conv,
        "grade": "inferred",
        "adjudicator": "几何判定链（约定扫描自动挣得）",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "reason": "变体码自动挣得（通道 B）：唯一干净约定 + ⊥清洁 + 距离带域"
                  "+角色证据达标；红线：正典码在场禁变体化、约定不跨幅继承、"
                  "升 verified 须用户图面核验/裁定",
        "evidence": ev,
    }


def _write_earned(sh, entries, log):
    """机挣册写出（与用户裁定册分立；零条目删陈旧防误读）。"""
    d = Path(sh.root) / "data"
    fp = d / f"fault_aux_code_earned_{sh.key}.json"
    if not entries:
        if fp.exists():
            fp.unlink()
            log(f"   机挣册清零（删陈旧）: {fp.name}")
        return
    d.mkdir(exist_ok=True)
    doc = {"registry": "geosciml4china/fault-aux-code-earned/v1",
           "sheet": sh.key,
           "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "codes": entries}
    fp.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                  encoding="utf-8")
    log(f"   机挣册 → data/{fp.name}（{len(entries)} 码 inferred 级）")
