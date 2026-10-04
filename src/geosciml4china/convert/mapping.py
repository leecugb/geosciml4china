"""Load geosciml_vocab_mapping.json and validate all decided terms at load time."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from . import config, vocab

# 段级标定语义 → CGI faulttype 词（词表语义恒定，图幅无关——CGI 词表
# 标准映射；2026-10-04 用户裁定「类别编码值拥有最高优先级」全继承后
# structural_type≡码义——faultType 规范性槽直接消费段级标定语义，
# 码查表路径仅保留给图幅级映射文件（ Kurgan/英吉沙正典的 pending/decided
# 裁定）；CGI faulttype 无活动/边界/泛称/复活专词——归 fault，语义
# 由 structural_type 槽与 description 承载）
_SEMANTIC_FAULTTYPE = {
    "断层": "fault", "断层泛称": "fault", "推测断层": "fault",
    "活动断层": "fault", "复活断层": "fault",
    "区域性大断裂": "fault", "边界断裂": "fault",
    "逆断层": "reverse_fault", "推覆体边界": "thrust_fault",
    "正断层": "normal_fault",
    "右型走滑断层": "dextral_strike_slip_fault",
    "左型走滑断层": "sinistral_strike_slip_fault",
    "走滑断层": "strike_slip_fault",
    "复合断层": "oblique_slip_fault",  # 双分量倾滑×走滑（gzeeb EXPECT 预注）
}


def faulttype_by_semantics(structural_type: str) -> str:
    """段级标定语义 → CGI faulttype term（未覆盖语义兜底 fault）。"""
    base = re.sub(r"[（(].*?[)）]", "", str(structural_type or "")).strip()
    return _SEMANTIC_FAULTTYPE.get(base, "fault")


def sheet_mapping_exists() -> bool:
    """图幅级词表映射文件在场判定——在场时码查表（含 pending→nil 裁定）
    优先于语义驱动默认（正典双幅回归契约）。"""
    return bool(config.VOCAB_MAPPING and config.VOCAB_MAPPING.exists())


# 段级界线终态语义 → CGI contacttype 词（2026-10-04 用户裁定：GZBD 同样
# 需要标定——三层逻辑跨域兑现；contactType 规范性槽消费段级终态语义
# sem_label（三层 L3 出站），码查表仅作图幅级裁定通道与未覆盖标签兜底；
# 「先验建议→」建议型标签剥后缀取基签映射）
_SEMANTIC_CONTACTTYPE = {
    "整合接触": "conformable_contact",
    "实测地质界线": "depositional_contact",
    "第四系界线": "depositional_contact",
    "角度不整合": "angular_unconformable_contact",
    "角度不整合界线": "angular_unconformable_contact",
    "平行不整合": "disconformable_contact",
    "平行不整合界线": "disconformable_contact",
    "不整合接触": "unconformable_contact",
    "不整合或平行不整合": "unconformable_contact",
    "岩性过渡渐变界线": "igneous_phase_contact",
    "脉动接触界线": "igneous_phase_contact",
}


def contacttype_by_semantics(sem_label: str) -> Optional[str]:
    """段级界线终态语义 → CGI contacttype term（未覆盖标签→None，回退
    码查表）。"""
    base = re.sub(r"（先验建议.*?）", "", str(sem_label or "")).strip()
    return _SEMANTIC_CONTACTTYPE.get(base)

_cache: Optional[dict] = None
_cache_key: str = ""


def load() -> dict:
    global _cache, _cache_key
    # 图幅切换缓存键（2026-10-03 修复：原 _cache 全局不复位——褶皱标定域
    # 首呼 load() 时 config 仍为模块默认 kurgan，缓存锁定库尔干词表，
    # jwss build 误用他幅码义（A07/A08/A25 三联失败根因）；现在按
    # VOCAB_MAPPING 路径键控，init_sheet 切换即重载
    key = str(config.VOCAB_MAPPING)
    if _cache is None or _cache_key != key:
        if config.VOCAB_MAPPING.exists():
            with open(config.VOCAB_MAPPING, encoding="utf-8") as f:
                _cache = json.load(f)
        else:
            # 泛化回退（2026-10-02 jwss 泛化测试）：独立项目无图幅级映射
            # 文件——包注册表（库尔干定稿码义）派生默认映射；未注册码
            # 走 pending/兜底默认（管线畅通+待裁定闭环）
            _cache = _derived_mapping()
        _validate(_cache)
        _cache_key = key
    return _cache


def _derived_mapping() -> dict:
    """gzbd_codes/gzeeb_codes 注册表 → 默认词表映射（图幅无关定稿码义）。"""
    from ..data import data_path as _dp

    def _ld(name):
        with open(_dp(name), encoding="utf-8") as f:
            return json.load(f)

    gzbd = _ld("gzbd_codes.json").get("codes", {})
    gzbd_ct = {code: {"term": e["geosciml_contacttype"],
                      "obs": "outcrop_observation", "status": "decided"}
               for code, e in gzbd.items() if e.get("geosciml_contacttype")}
    # 通用跳过语义：断层接触（10）与非地质界线（81）不发射接触要素
    gzbd_ct["10"] = {"term": None, "status": "skip_fault"}
    gzbd_ct["81"] = {"term": None, "status": "skip_nongeologic"}

    # 语义 → faulttype 词（词表语义恒定，图幅无关——CGI 词表标准映射）
    _MEANING_TERM = {"断层": "fault", "推测断层": "fault", "逆断层": "reverse_fault",
                     "推覆体边界": "thrust_fault", "正断层": "normal_fault",
                     "右型走滑断层": "dextral_strike_slip_fault",
                     "左型走滑断层": "sinistral_strike_slip_fault",
                     "区域性大断裂": "fault", "复活断层": "fault",
                     "边界断裂": "fault"}
    # 2026-10-02 用户对齐裁定：码→义映射依赖本幅数据模式——消费本幅
    # 码义注册表（fault_semantics_<key>.json）；未注册码走 pending
    gzeeb_ft = {}
    try:
        from ..calibrate.registry import load_gzeeb_semantics as _lgs
        from ..sheets import get_sheet as _gs
        import re as _re

        def _nrm(x):
            return _re.sub(r"[（(].*?[)）]", "", str(x)).strip()
        _gsem, _ = _lgs(_gs(config.SHEET_KEY).root, config.SHEET_KEY)
        for _code, _ent in _gsem.items():
            _meaning = _nrm(_ent.get("semantic", _ent.get("meaning", ""))
                          if isinstance(_ent, dict) else _ent)
            _term = _MEANING_TERM.get(_meaning)
            if _term:
                gzeeb_ft[_code] = {"term": _term, "status": "decided"}
    except Exception:
        pass

    return {
        "_meta": {"sheet": config.SHEET,
                  "derived": "包注册表派生默认映射（无图幅级映射文件，2026-10-02 泛化回退）",
                  "note": "图幅特有裁定请建图幅级 geosciml_vocab_mapping_<key>.json"},
        "identifier": {},
        "gzbd_contacttype": gzbd_ct,
        "gzeeb_faulttype": gzeeb_ft,
        "evidence_observation": {"实测": "outcrop_observation",
                                 "部分覆盖": "indirect_method",
                                 "推测": "indirect_method",
                                 "解译": "remotely_sensed_data"},
        "gzbbga_foliation": {
            "202001": {"term": "bedding_fabric", "status": "decided"},
            "202005": {"term": "schistosity", "status": "decided"},
            "202011": {"term": "foliation", "status": "decided"},
            "202004": {"term": "bedding_fabric", "polarity": "overturned",
                       "status": "decided"},
            "202007": {"term": "foliation", "status": "decided"},
            "面理产状": {"term": "foliation", "status": "decided"},
            "片麻理产状": {"term": "gneissic_layering", "status": "decided"}},
        "gzce_foldprofile": {
            "_uri_base": "http://inspire.ec.europa.eu/codelist/FoldProfileTypeValue/",
            "02": {"term": "anticline", "status": "decided"},
            "04": {"term": "anticline", "status": "decided"},
            "03": {"term": "syncline", "status": "decided"},
            "01": {"term": "syncline", "status": "decided"}},
        "eventprocess": {"侵入岩": "intrusion", "沉积地层": "deposition",
                         "沉积岩建造": "deposition", "火山岩性岩相": "deposition",
                         "变质岩": "metamorphic_process",
                         "变质岩建造": "metamorphic_process"},
        "unit_type": {"侵入岩": "lithodemic_unit",
                      "沉积地层": "lithostratigraphic_unit",
                      "沉积岩建造": "lithostratigraphic_unit",
                      "火山岩性岩相": "lithostratigraphic_unit",
                      "变质岩": "lithodemic_unit",
                      "变质岩建造": "lithodemic_unit"},
        "unit_extras": {},
        "pending": [],
    }


def _validate(m: dict) -> None:
    """Every decided vocabulary term must exist in its vocabulary — die here,
    not at XSD time."""
    for code, row in m["gzbd_contacttype"].items():
        if row.get("status") == "decided" and row.get("term"):
            vocab.cgi_term("contacttype", row["term"])
        if row.get("obs"):
            vocab.cgi_term("featureobservationmethod", row["obs"])
    for code, row in m["gzeeb_faulttype"].items():
        if row.get("status") == "decided" and row.get("term"):
            vocab.cgi_term("faulttype", row["term"])
    for label, term in m["evidence_observation"].items():
        vocab.cgi_term("featureobservationmethod", term)
    for code, row in m["gzbbga_foliation"].items():
        if row.get("status") == "decided" and row.get("term"):
            vocab.foliation_uri(row["term"])
    for term in m["eventprocess"].values():
        vocab.cgi_term("eventprocess", term)
    for term in m["unit_type"].values():
        vocab.cgi_term("geologicunittype", term)


def gzbd_row(code: str) -> Dict[str, Any]:
    return load()["gzbd_contacttype"].get(code, {"term": None, "status": "pending"})


def gzeeb_row(code: str) -> Dict[str, Any]:
    return load()["gzeeb_faulttype"].get(code, {"term": "fault", "status": "decided"})


def evidence_observation(evidence_class: str) -> Optional[str]:
    return load()["evidence_observation"].get(evidence_class)


def foliation_row(key: str) -> Dict[str, Any]:
    return load()["gzbbga_foliation"].get(key, {"term": None, "status": "pending"})


def fold_profile(code: str) -> Optional[str]:
    row = load()["gzce_foldprofile"].get(code)
    if row and row.get("term"):
        return load()["gzce_foldprofile"]["_uri_base"] + row["term"]
    return None


def eventprocess(layer_role: str) -> str:
    return load()["eventprocess"].get(layer_role, "deposition")


def unit_type(layer_role: str) -> str:
    return load()["unit_type"].get(layer_role, "lithostratigraphic_unit")


def pending() -> list:
    return load()["pending"]
