# -*- coding: utf-8 -*-
"""运动学一致性抽象约束审计（2026-10-05 用户裁定「一致与不一致作为抽象
约束，更有利于泛化」+ 契约审计 P1-1/P1-7 修复的回归闸）。

覆盖：①相容关系纯函数钉板；②GZELD 全局先验装载；③三幅生产数据不变量
（不一致段必须已登记矛盾保留）；④movementSense 回退通道端到端（钩优先
+GZELD 兜底——L1 gzeld_sem×hooks 独立重算对账 GML）。
"""
import glob
import json
from pathlib import Path

import pandas as pd
import pytest

from geosciml4china.calibrate.gzeeb import _KIN_CONSISTENT, _kin_consistent
from geosciml4china.calibrate.registry import load_gzeld_global_priors

SHEETS = [("jwss", r"D:\jwss"), ("jwsss", r"D:\jwsss"),
          ("aoyiyayilake", None)]  # aoy root 含中文，glob 解析


def _root(key):
    """图幅根目录；数据缺席（CI runner）→ None（调用方 skip）。"""
    if key == "aoyiyayilake":
        hits = glob.glob(r"D:\J45C004001*\J45C004001\MAPGIS\JWD")
        return hits[0] if hits else None
    return dict((k, r) for k, r in SHEETS if r)[key]


# ---------- ① 相容关系钉板 ----------

def test_kin_consistent_relation_truth_table():
    # 受约束族
    assert _kin_consistent("逆断层", "压性") is True
    assert _kin_consistent("逆断层", "张性") is False
    assert _kin_consistent("推覆体边界", "压性") is True
    assert _kin_consistent("正断层", "张性") is True
    assert _kin_consistent("正断层", "压性") is False
    assert _kin_consistent("右型走滑断层", "右行走滑") is True   # 全局先验词形
    assert _kin_consistent("右型走滑断层", "左行") is False
    assert _kin_consistent("左型走滑断层", "左行（2026-09-25 用户裁定）") is True
    # 泛称走滑兼容双向
    assert _kin_consistent("走滑断层", "左行") is True
    assert _kin_consistent("走滑断层", "右行") is True
    assert _kin_consistent("走滑断层", "压性") is False
    # 复合断层：任一分量相容即一致
    assert _kin_consistent("复合断层（逆-右行）", "压性") is True
    assert _kin_consistent("复合断层（逆-右行）", "右行走滑") is True
    assert _kin_consistent("复合断层（逆-右行）", "张性") is False
    # 中性：泛称/推测/活动/未记录/不明/未注册码值
    assert _kin_consistent("断层泛称", "张性") is None
    assert _kin_consistent("推测断层", "压性") is None
    assert _kin_consistent("活动断层", "左行") is None
    assert _kin_consistent("逆断层", "109") is None
    assert _kin_consistent("逆断层", "一般") is None
    assert _kin_consistent("逆断层", "运动性质不明") is None
    assert _kin_consistent("逆断层", "") is None
    # 未声明约束的结构语义——中性（区域性大断裂/复活断层等）
    assert _kin_consistent("区域性大断裂", "压性") is None
    assert _kin_consistent("复活断层", "张性") is None
    # 约束表完备性：四关键词均被使用
    used = set().union(*[set(v) for v in _KIN_CONSISTENT.values()])
    assert used == {"压性", "张性", "左行", "右行"}


# ---------- ② GZELD 全局先验装载 ----------

def test_gzeld_global_priors_load():
    pri = load_gzeld_global_priors()
    assert pri == {"101": "压性", "102": "张性",
                   "103": "右行走滑", "104": "左行走滑"}


# ---------- ③ 生产数据不变量（三幅） ----------

@pytest.mark.parametrize("key,_r", SHEETS)
def test_consistency_production_invariant(key, _r):
    """不一致段必须已登记（矛盾保持）：_kin_consistent=False 的行 verdict
    必为标定（矛盾保留）。"""
    root = _root(key)
    if root is None:
        pytest.skip(f"{key} 数据缺席（CI runner）")
    p = Path(root) / f"_gzeeb_calibration_{key}.csv"
    if not p.exists():
        pytest.skip(f"{key} 无 gzeeb 标定表")
    cal = pd.read_csv(p, dtype=str)
    viol = 0
    for _, r in cal.iterrows():
        res = _kin_consistent(str(r.get("structural_type") or ""),
                              str(r.get("gzeld_sem") or ""))
        if res is False:
            viol += 1
            assert "矛盾" in str(r["verdict"]) or "违反" in str(r["verdict"]), \
                f"{key} idx{r['idx']}: {r['structural_type']}×" \
                f"{r['gzeld_sem']} 不一致但未登记"


# ---------- ④ movementSense 回退通道端到端 ----------

def test_movement_sense_fallback_end_to_end_aoy():
    """钩对优先 + GZELD 兜底：GML movementSense 计数 ==
    |{钩右行段} ∪ {gzeld_sem 右行 且无钩段}|（sinistral 同构）。"""
    root = _root("aoyiyayilake")
    if root is None:
        pytest.skip("aoy 数据缺席（CI runner）")
    gmls = glob.glob(str(Path(root) / "output/geosciml/*_geosciml_full.gml"))
    lp = Path(root) / "geojson/L1/faults.geojson"
    if not gmls or not lp.exists():
        pytest.skip("aoy GML/L1 缺席")
    feats = json.load(open(lp, encoding="utf-8"))["features"]
    gzsem = {int(f["properties"]["_src_id"]):
             str(f["properties"].get("gzeld_sem") or "")
             for f in feats}
    hooked = {}
    hp = Path(root) / "_fault_hooks_aoyiyayilake.csv"
    if hp.exists():
        for _, hr in pd.read_csv(hp, dtype=str).iterrows():
            for sg in str(hr.get("segs") or "").split(","):
                if sg.strip():
                    hooked[int(sg)] = str(hr["sense"])
    exp_dex = ({s for s in hooked if hooked[s] == "右行"} |
               {s for s, g in gzsem.items()
                if g.startswith("右行") and s not in hooked})
    exp_sin = ({s for s in hooked if hooked[s] == "左行"} |
               {s for s, g in gzsem.items()
                if g.startswith("左行") and s not in hooked})
    gml = open(gmls[0], encoding="utf-8").read()
    n_dex = gml.count("faultmovementsense/dextral")
    n_sin = gml.count("faultmovementsense/sinistral")
    assert n_dex == len(exp_dex), \
        f"dextral: GML={n_dex} 期望={len(exp_dex)}"
    assert n_sin == len(exp_sin), \
        f"sinistral: GML={n_sin} 期望={len(exp_sin)}"
    # 回退实证：16 码未挂钩段必须 dextral 出站（F037/F035/F137 案）
    aoy16 = [s for s, g in gzsem.items()
             if g.startswith("右行") and s not in hooked]
    assert len(aoy16) == 4, f"16 码回退段数 {len(aoy16)}≠4"


def test_movement_sense_hook_priority_jwss():
    """钩优先于 GZELD 全局先验：jwss（英吉沙副本，103 全局=右行）的 3 个
    钩段为左行——GML 中其 slip=sinistral，dextral=0。"""
    root = _root("jwss")
    if root is None:
        pytest.skip("jwss 数据缺席（CI runner）")
    gmls = glob.glob(str(Path(root) / "output/geosciml/*_geosciml_full.gml"))
    if not gmls:
        pytest.skip("jwss GML 缺席")
    gml = open(gmls[0], encoding="utf-8").read()
    n_dex = gml.count("faultmovementsense/dextral")
    n_sin = gml.count("faultmovementsense/sinistral")
    assert n_dex == 0 and n_sin == 3, \
        f"jwss 钩优先失守: dextral={n_dex} sinistral={n_sin}"


# ---------- ⑤ 源码漂移闸（2026-10-05 裁定链守卫） ----------

_SRC = Path(__file__).resolve().parents[1] / "src" / "geosciml4china"


def test_drift_gzeld_user_edit_priority():
    """GZELD 三线优先级=注册表>用户编辑>全局先验>推导（P1-7 修复闸）。"""
    src = (_SRC / "calibrate" / "gzeeb.py").read_text(encoding="utf-8")
    i = src.index("gzeld_sem_now =")
    win = src[i:i + 300]
    assert win.index("gzeld_sem.get(gzeld)") < win.index("_user_kin.get(gzeld)") \
        < win.index("_gzeld_prior.get(gzeld)")


def test_drift_movement_sense_fallback():
    """movementSense 回退分支存在（P1-1 修复闸）：钩优先、GZELD 兜底、
    未记录不伪出站。"""
    src = (_SRC / "convert" / "build.py").read_text(encoding="utf-8")
    assert '_slip = slip_by_seg.get' in src and 'gzeld_sem' in src
    i = src.index('_gzsem = str(row.get("gzeld_sem")')
    win = src[i:i + 400]
    assert "右行" in win and '"dextral"' in win
    assert "左行" in win and '"sinistral"' in win


def test_drift_water_not_cover():
    """水系不算覆盖原则（2026-10-04 用户重申）——cover_u 不得含水系线。"""
    src = (_SRC / "calibrate" / "gzeeb.py").read_text(encoding="utf-8")
    i = src.index("cover_u =")
    win = src[i:i + 140]
    assert "ice_u" in win and "quat_u" in win and "water_u" not in win


def test_drift_stylegen_name_first():
    """stylegen 岩性直读优先（2026-10-05 裁定）——名称通道先行、前缀兜底。"""
    src = (_SRC / "render" / "stylegen.py").read_text(encoding="utf-8")
    assert "_INTR_NAME" in src
    i = src.index("intr = _intr_name_spec")
    win = src[i:i + 180]
    assert "_intr_name_spec(u.name, nm, lib)" in win
    assert "_intr_spec(nm, lib)" in win
