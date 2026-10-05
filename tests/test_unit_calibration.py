# -*- coding: utf-8 -*-
"""标定/渲染纯逻辑单元测试（2026-10-05 完善测试第二轮）。

CI 契约：本文件不依赖 pymapgis.semantics（PyPI 极简包缺席时同样运行）——
只测纯函数与包数据装载：一致性抽象约束 _kin_consistent、断层名性质优先
name_sem、GZELD 全局先验、43/60 时代后缀剥离与跨时代均值、侵入岩名称
直读通道、DZ/T 0179 色库装载。
"""
import json

import pytest

from geosciml4china.calibrate import gzbd
from geosciml4china.calibrate.gzeeb import _kin_consistent, name_sem, norm_sem
from geosciml4china.calibrate.registry import load_gzeld_global_priors
from geosciml4china.data import data_path
from geosciml4china.render.stylegen import Lib, _intr_name_spec


# ---------- 一致性抽象约束（2026-10-05 用户裁定：一致/不一致作为抽象约束，
# 语义层而非码层——跨幅不变） ----------

KIN_TRUE = [
    ("逆断层", "压性"), ("推覆体边界", "压性"),
    ("正断层", "张性"),
    ("左型走滑断层", "左行"), ("右型走滑断层", "右行"),
    ("走滑断层", "左行"), ("走滑断层", "右行"),      # 泛称走滑兼容双向
    ("复合断层（逆-右行）", "右行"), ("复合断层（逆-右行）", "压性"),
    ("复合断层（正-左行）", "左行"), ("复合断层（逆）", "压性"),
]
KIN_FALSE = [
    ("逆断层", "张性"), ("逆断层", "左行"), ("逆断层", "右行"),
    ("正断层", "压性"), ("正断层", "右行"),
    ("推覆体边界", "张性"), ("推覆体边界", "右行"),
    ("左型走滑断层", "右行"), ("右型走滑断层", "左行"),
    ("复合断层（逆-右行）", "张性"), ("复合断层（正-左行）", "右行"),
    ("复合断层（走滑）", "压性"),
]
KIN_NEUTRAL = [
    # 泛称兼容一切 / 推测·活动不属结构轴（正交层）
    ("断层泛称", "压性"), ("断层（泛称）", "张性"),
    ("推测断层", "左行"), ("活动断层", "右行"),
    ("", "压性"), ("断层", "张性"),
    # GZELD 运动学未记录（109/一般/不明/空）——中性
    ("逆断层", ""), ("逆断层", "109"), ("逆断层", "一般"), ("逆断层", "不明"),
    # 未声明约束的结构语义（复活/区域性等）——中性
    ("复活断层", "压性"), ("区域性大断裂", "张性"),
    # 无分量复合断层——中性
    ("复合断层", "压性"),
]


@pytest.mark.parametrize("structural,kin", KIN_TRUE)
def test_kin_consistent_true(structural, kin):
    assert _kin_consistent(structural, kin) is True


@pytest.mark.parametrize("structural,kin", KIN_FALSE)
def test_kin_consistent_false(structural, kin):
    assert _kin_consistent(structural, kin) is False


@pytest.mark.parametrize("structural,kin", KIN_NEUTRAL)
def test_kin_consistent_neutral(structural, kin):
    assert _kin_consistent(structural, kin) is None


# ---------- 断层名性质优先（2026-10-01 用户裁定：断层名具有性质优先权） ----------

def test_name_sem_keywords_and_match_order():
    assert name_sem("左行走滑断裂") == "左型走滑断层"
    assert name_sem("右行走滑断裂") == "右型走滑断层"
    assert name_sem("逆冲断裂") == "逆断层"
    assert name_sem("逆冲推覆断裂") == "推覆体边界"  # 匹配序敏感：推覆先于逆冲
    assert name_sem("正断层") == "正断层"
    assert name_sem("复活断层") == "复活断层"
    assert name_sem("活动断裂") == "活动断层"
    assert name_sem("") == ""
    assert name_sem("无名断裂") == ""


def test_norm_sem_strips_annotations():
    assert norm_sem("逆断层（推覆证据）") == "逆断层"
    assert norm_sem("压性") == "压性"


# ---------- GZELD 全局先验（2026-10-04 用户裁定：101 压性/102 张性/
# 103 右行走滑/104 左行走滑——图幅注册表裁定优先于本层） ----------

def test_gzeld_global_priors_contract():
    assert load_gzeld_global_priors() == {
        "101": "压性", "102": "张性", "103": "右行走滑", "104": "左行走滑"}


def test_gzeld_package_data_loads():
    j = json.load(open(data_path("gzeld_codes.json"), encoding="utf-8"))
    assert set(j["gzeld_semantics"]) == {"101", "102", "103", "104"}


# ---------- 43/60 时代后缀剥离（г/∑ 西里尔与数学符误录变体） ----------

def test_era_suffix_of_strips_non_ascii():
    assert gzbd._era_suffix_of("→C↓2-P↓1→t") == "C2-P1t"
    assert gzbd._era_suffix_of("гC-P") == "C-P"
    assert gzbd._era_suffix_of("∑O-D↓2") == "O-D2"
    assert gzbd._era_suffix_of("γδT↓1") == "T1"
    assert gzbd._era_suffix_of("J3kz") == "J3kz"


def test_age_rank_fallback_chain(monkeypatch):
    """时代级别兜底链：码解析 → 剥非 ASCII 前缀再解析（跨时代取均值，
    2026-09-15 跨亚统均值裁定同构）→ 名称字段时代词。_unit_age_rank
    monkeypatch 桩替——不依赖 pymapgis（CI 可跑）。"""
    ranks = {"C": 600.0, "C1": 600.0, "P": 700.0, "O": 500.0, "D2": 550.0,
             "T1": 800.0}
    monkeypatch.setattr(gzbd, "_unit_age_rank",
                        lambda code: ranks.get(str(code)))
    monkeypatch.setattr(gzbd, "_era_from_name", lambda name: 999.0)
    assert gzbd._age_rank_of({"code": "гC-P", "name": ""}) == 650.0
    assert gzbd._age_rank_of({"code": "∑O-D2", "name": ""}) == 525.0
    assert gzbd._age_rank_of({"code": "γδT1", "name": ""}) == 800.0
    assert gzbd._age_rank_of({"code": "C1", "name": ""}) == 600.0  # 直读优先
    assert gzbd._age_rank_of({"code": "→xx", "name": "白垩系地层"}) == 999.0


# ---------- 侵入岩名称直读通道（2026-10-05 用户裁定：优先读取岩浆岩自身
# 属性字段；长词优先防「花岗岩」截断「二长花岗岩」） ----------

def test_intr_name_channel_long_word_priority():
    lib = Lib()
    spec = _intr_name_spec("灰白色二长花岗岩", "ηγC-γC", lib)
    assert spec.cls == "intrusive"
    assert spec.pattern_ref == {"family": "t15_intrusive", "code": "etagJ1"}
    spec2 = _intr_name_spec("中粒二长花岗岩", "ηγT2", lib)
    assert spec2.pattern_ref == {"family": "t15_intrusive", "code": "etagJ1"}


def test_intr_name_dike_guard_no_pattern():
    """脉岩守卫：名称含岩脉/脉岩不赋侵入体花纹；时代不明落表 14。"""
    lib = Lib()
    spec = _intr_name_spec("闪长岩岩脉", "δ", lib)
    assert spec.cls == "intrusive"
    assert spec.pattern_ref is None
    assert "表14" in spec.src


def test_intr_name_no_keyword_returns_none():
    assert _intr_name_spec("玄武岩", "β", Lib()) is None


# ---------- DZ/T 0179 色库装载（包数据单源） ----------

def test_color_lib_loads_package_data():
    lib = Lib()
    assert lib.sys_base
    assert lib.t6_ep
    assert lib.t14


# ---------- 比例尺锚定画布（2026-10-05 用户裁定「样式尺寸保持固定」） ----------

def test_scale_anchored_figsize_constant_mpp():
    """画布随 bbox 等比伸缩：每像素地面米恒定=1:25 万图面（250000×0.0254/dpi）
    ——小图幅（td 41×42 km）不再被固定画布放大致样式相对变细。"""
    from geosciml4china.render.map_builder import (_MAP_SCALE_DENOM,
                                                   _scale_anchored_figsize)
    dpi = 200
    # td 级小图幅 vs y1 级大图幅：figsize 与范围（米）成正比，mpp 相同
    bbox_td = (73.6, 39.7, 74.1, 40.1)   # ~41×44 km
    bbox_y1 = (74.6, 39.7, 76.2, 40.8)   # ~137×122 km
    fw_td, fh_td = _scale_anchored_figsize(bbox_td, dpi)
    fw_y1, fh_y1 = _scale_anchored_figsize(bbox_y1, dpi)
    import math
    lat0_td = (bbox_td[1] + bbox_td[3]) / 2
    lat0_y1 = (bbox_y1[1] + bbox_y1[3]) / 2
    mpp = _MAP_SCALE_DENOM * 0.0254 / dpi
    # mpp 恒定：宽度米 ÷ (fig_in × dpi) 恰为标准 mpp
    w_m_td = (bbox_td[2] - bbox_td[0]) * 111320 * math.cos(math.radians(lat0_td))
    w_m_y1 = (bbox_y1[2] - bbox_y1[0]) * 111320 * math.cos(math.radians(lat0_y1))
    assert w_m_td / (fw_td * dpi) == pytest.approx(mpp, rel=1e-9)
    assert w_m_y1 / (fw_y1 * dpi) == pytest.approx(mpp, rel=1e-9)
    # 物理图面尺寸与 dpi 无关（dpi 只决定像素数）
    fw_td_300, _ = _scale_anchored_figsize(bbox_td, 300)
    assert fw_td_300 == pytest.approx(fw_td, rel=1e-12)
