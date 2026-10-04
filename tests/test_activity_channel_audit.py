# -*- coding: utf-8 -*-
"""活动断层判别通道审计（2026-10-02 活动断层标定逻辑审计 A10 落地）：
面元拓扑通道（gzeeb 内）+ 断裂接触审计层（第七域）的不变量与消费链。

方法=不变量断言：生产 CSV（四幅+jws）+ 合成登记册（双册消费链）+
纯函数分类 + 源码 lint（硬编码漂移闸）。登记册断言对 A7 前陈旧件
显式跳过（reason 注明），正典重跑后自动激活。
"""
import re
from pathlib import Path

import pandas as pd
import pytest

from pymapgis.rendering.pdf_writer import _unit_age_rank

SRC = Path(r"D:\geosciml4china\src\geosciml4china")

# 2026-10-04 用户裁定：审计测试以 jwss/jwsss 为测试项目；import 期
# skipif 标记——无数据机器（CI runner）优雅跳过
SHEETS = [
    pytest.param("jwsss", r"D:\jwsss",
                 marks=pytest.mark.skipif(not Path(r"D:\jwsss").is_dir(),
                                          reason="jwsss 数据不在场")),
    pytest.param("jwss", r"D:\jwss",
                 marks=pytest.mark.skipif(not Path(r"D:\jwss").is_dir(),
                                          reason="jwss 数据不在场")),
]


# ---------- 纯函数分类 ----------

def _is_q(c, excl=("Qp1X",), qmin=1300.0):
    """独立重算 Q 侧判定（与 fault_contact_activity._is_q 同约）。"""
    nc = re.sub(r"[→↓↑.-]", "", str(c)).strip()
    return ((_unit_age_rank(c) or 0) >= qmin
            and not any(x in nc for x in excl))


def test_q_side_classification_markers():
    """码面标记归一：→Qh↑al 等 Q 码入 Q 侧；半胶结 Qp1X 剔除；无时代
    侵入岩（→δ）与非 Q 地层入地层侧。"""
    assert _is_q("→Qh↑al") and _is_q("→Qh↑pal") and _is_q("→Qp↓3↑pal")
    assert _is_q("→Qp↓2↑W") and _is_q("→Qp↓3↑gl")
    assert not _is_q("→Qp↓1→X")            # 半胶结西域组剔除
    assert not _is_q("→N↓1→k") and not _is_q("→D↓2→t")
    assert not _is_q("→EK") and not _is_q("→S↓3-4→t")
    assert not _is_q("→δ")                  # 侵入岩无时代后缀 → 非 Q


def test_activity_check_strings_classified_acont():
    """ACONT 根类覆盖（A4 修复回归闸）：面元拓扑通道证据串必须归入
    活动证据根类（check_classes 前缀匹配）。"""
    from pymapgis.semantics.confidence import check_classes
    ac = ("第四系界线重合", "活动性佐证", "Q-地层边界重合",
          "实体 Q-地层边界重合")
    for s in ("Q-地层边界重合 8944m",
              "实体 Q-地层边界重合×2段（活动候选）",
              "活动性佐证（Q-地层边界重合×3段）"):
        assert "ACONT" in check_classes(s, {"ACONT": ac}), s


def test_read_fault_conflict_entities_dual_register(tmp_path):
    """登记册消费链（合成，2026-10-02 裁定后单册）：产品横幅只读 gzeeb
    册；断裂接触册为审查档案不入横幅集合。adjudicated 与空 fault_id
    行过滤保持。"""
    from geosciml4china.convert import sources, config
    a = tmp_path / "a.csv"
    pd.DataFrame([
        {"fault_id": "F001", "segs": "[187, 192]", "issue": "活动断层候选",
         "evidence": "段187: 7840m（90%段长）", "status": "pending_review"},
        {"fault_id": "F002", "segs": "[5]", "issue": "活动断层候选",
         "evidence": "已裁定", "status": "adjudicated"},
        {"fault_id": "", "segs": "99", "issue": "活动断层候选",
         "evidence": "无归因", "status": "pending_review"},
    ]).to_csv(a, index=False, encoding="utf-8-sig")
    b = tmp_path / "b.csv"
    pd.DataFrame([
        {"fault_id": "F047", "segs": "41", "issue": "断裂接触活动候选",
         "evidence": "归因 F047 段41", "status": "pending_review"},
    ]).to_csv(b, index=False, encoding="utf-8-sig")
    _oa, _ob = config.CONFLICTS_CSV, config.CONTACT_CONFLICTS_CSV
    try:
        config.CONFLICTS_CSV = a
        config.CONTACT_CONFLICTS_CSV = b
        out = sources.read_fault_conflict_entities()
    finally:
        config.CONFLICTS_CSV = _oa
        config.CONTACT_CONFLICTS_CSV = _ob
    assert out == {("F001", 187), ("F001", 192)}


# ---------- 生产数据不变量 ----------

@pytest.mark.parametrize("key,root", SHEETS)
def test_activity_candidates_never_carto_error(key, root):
    """制图误差剔除与活动通道正交（seg217 案护栏）：候选行不得为制图
    误差；制图误差行活动性必为未评。"""
    p = Path(root) / f"_gzeeb_calibration_{key}.csv"
    if not p.exists():
        pytest.skip(f"{key} 无 gzeeb 标定表")
    gz = pd.read_csv(p, dtype=str)
    act = gz[gz["activity"].astype(str).str.contains("候选", na=False)]
    assert not act["verdict"].astype(str).str.contains("制图误差").any(), \
        f"{key} 活动候选行携带制图误差"
    carto = gz[gz["verdict"].astype(str).str.contains("制图误差", na=False)]
    assert (carto["activity"].astype(str) == "未评").all(), \
        f"{key} 制图误差行活动性非未评"


@pytest.mark.parametrize("key,root", SHEETS)
def test_activity_candidate_checks_carry_acon_evidence(key, root):
    """候选行证据串完整（A4/A5 修复回归闸）：活动候选行的 checks 必须
    携带 Q-地层边界重合/活动性佐证证据串。"""
    p = Path(root) / f"_gzeeb_calibration_{key}.csv"
    if not p.exists():
        pytest.skip(f"{key} 无 gzeeb 标定表")
    gz = pd.read_csv(p, dtype=str)
    act = gz[gz["activity"].astype(str).str.contains("候选", na=False)]
    if not len(act):
        pytest.skip(f"{key} 无活动候选行（正典重跑前）")
    _ch = act["checks"].astype(str)
    if _ch.str.contains("切割第四系", na=False).any() \
            and not _ch.str.contains("Q-地层边界重合", na=False).any():
        pytest.skip(f"{key} 标定表为切割通道旧件，待重跑")
    _pfx = ("Q-地层边界重合", "实体 Q-地层边界重合", "活动性佐证",
            "第四系界线重合")
    for _, r in act.iterrows():
        toks = [t for t in str(r["checks"]).split("；") if t.strip()]
        assert any(t.startswith(_pfx) for t in toks), \
            f"{key} seg{int(r['idx'])} 候选行缺活动证据串"


@pytest.mark.parametrize("key,root", [s for s in SHEETS if s[0] == "kurgan"])
def test_fault_contact_candidate_side_evidence(key, root):
    """断裂接触候选两侧证据独立核验：Q 侧码均 age_rank≥门槛且不含
    半胶结剔除码；地层侧码均 <门槛（或属剔除码）。"""
    from geosciml4china.calibrate.priors import load_priors
    p = Path(root) / f"_fault_contact_activity_{key}.csv"
    if not p.exists():
        pytest.skip(f"{key} 无断裂接触审计表")
    pri = load_priors(key) or {}
    excl = set(pri.get("quaternary_exclude", ["Qp1X"]))
    qmin = float(pri.get("quaternary_rank_min", 1300.0))
    fc = pd.read_csv(p, dtype=str)
    cand = fc[fc["候选"].notna() & (fc["候选"].astype(str) != "")]
    assert len(cand) > 0, f"{key} 断裂接触候选 0 条"
    for _, r in cand.iterrows():
        q_units = [u for u in str(r["第四系_unit"]).split("/")
                   if u and u != "nan"]
        s_units = [u for u in str(r["地层_unit"]).split("/")
                   if u and u != "nan"]
        assert q_units and s_units, f"段{int(r['idx'])} 候选缺 Q/地层侧证据"
        for u in q_units:
            assert (_unit_age_rank(u) or 0) >= qmin, f"段{int(r['idx'])} Q 侧混入 {u}"
            assert not any(x in re.sub(r"[→↓↑.-]", "", str(u)).strip()
                           for x in excl), f"段{int(r['idx'])} Q 侧混入剔除码 {u}"
        for u in s_units:
            rk = _unit_age_rank(u) or 0
            ex = any(x in re.sub(r"[→↓↑.-]", "", str(u)).strip()
                     for x in excl)
            assert rk < qmin or ex, f"段{int(r['idx'])} 地层侧混入 Q 码 {u}"


@pytest.mark.parametrize("key,root", SHEETS)
def test_fault_contact_register_attributed(key, root):
    """A7 归因不变量：登记册行 fault_id 非空、segs 可解析为断层段
    索引。A7 前陈旧件（fault_id 全空）显式跳过，正典重跑后激活。"""
    p = Path(root) / f"_fault_contact_activity_conflicts_{key}.csv"
    if not p.exists():
        pytest.skip(f"{key} 无断裂接触登记册")
    reg = pd.read_csv(p, dtype=str)
    fids = [f for f in reg["fault_id"].astype(str) if f not in ("", "nan")]
    if not fids:
        pytest.skip(f"{key} 登记册为 A7 前陈旧件（fault_id 空），待正典重跑")
    assert len(fids) == len(reg), f"{key} 归因不完整：部分行 fault_id 为空"
    for s in reg["segs"].astype(str):
        int(float(s))


# ---------- 源码 lint（硬编码漂移闸） ----------

def test_gzeeb_nq_side_uses_q_rank_param():
    """A1 漂移闸：非 Q 侧过滤必须与 Q 侧同参数（_q_rank），不得回退
    硬编码 1300。"""
    src = (SRC / "calibrate" / "gzeeb.py").read_text(encoding="utf-8")
    i = src.index("_nq_geoms")
    win = src[i:i + 300]
    assert "_q_rank" in win and "< 1300" not in win


def test_gzeeb_q_union_covers_four_wp_layers():
    """A2 漂移闸：Q 面元并集必须覆盖四个 WP 地层图层。"""
    src = (SRC / "calibrate" / "gzeeb.py").read_text(encoding="utf-8")
    seg = src[src.index("q_geoms = []"):src.index("quat_u =")]
    for fn in ("LDZOFBB001", "LDZOFBB002", "LDZOFBB003", "LDZOFBB004"):
        assert f'"{fn}.WP"' in seg, fn


def test_build_activity_evidence_token_outbound():
    """A5 漂移闸：GML 出站 token 必须含 Q-地层边界重合证据串。"""
    src = (SRC / "convert" / "build.py").read_text(encoding="utf-8")
    assert '"Q-地层边界重合" in _tok' in src


def test_fault_contact_probe_steps_and_attribution():
    """A7/A8 漂移闸：自适应探针步长与断层归因必须保留。"""
    src = (SRC / "calibrate" / "fault_contact_activity.py") \
        .read_text(encoding="utf-8")
    assert "PROBE_STEPS_M" in src
    assert "ATTRIB_MAX_M" in src and "距断层线" in src
    assert "fault_entities" in src          # seg2fid 归组源
