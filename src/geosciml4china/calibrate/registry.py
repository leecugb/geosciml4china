# -*- coding: utf-8 -*-
"""图幅码义注册表共享装载（2026-10-01 泛化优化：gzeeb/auxchain 双域复用）。

注册表链（图幅文件优先、无叠加合并——勿跨幅套码义教训在案）：
  1. <root>/fault_semantics_<key>.json
  2. <root>/data/gzeeb_codes.json
  3. 包数据 gzeeb_codes.json（国家通用核心码基座）
"""
from __future__ import annotations

import json
from pathlib import Path


def load_gzeeb_semantics(sheet_root, sheet_key: str):
    """装载图幅 GZEEB/GZELD 码义注册表。

    返回 (gsem: dict, gzeld_sem: dict)——gsem 键=两位码，值=dict 含
    semantic/meaning 字段（或直接字符串）；gzeld_sem 键=GZELD 码值。
    """
    from ..data import data_path  # 包数据路径助手

    _cands = [
        Path(sheet_root) / f"fault_semantics_{sheet_key}.json",
        Path(sheet_root) / "data" / "gzeeb_codes.json",
    ]
    sem_p = None
    for _c in _cands:
        if _c.exists():
            sem_p = str(_c)
            break
    if sem_p is None:
        sem_p = str(data_path("gzeeb_codes.json"))
    sem_j = json.load(open(sem_p, encoding="utf-8"))
    gsem = dict(sem_j.get("gzeeb_semantics") or sem_j.get("codes") or {})
    gzeld_sem = dict(sem_j.get("gzeld_semantics", {}))
    return gsem, gzeld_sem


def reverse_codes(gsem: dict, norm_sem) -> set:
    """逆断层期望码集（aux 互验基准，注册表驱动）：语义 ∈ {逆断层,
    推覆体边界} 的码——推覆=逆冲分量，aux 组期望逆判。
    """
    out = set()
    for code, entry in gsem.items():
        if not isinstance(entry, dict):
            continue
        sem = norm_sem(entry.get("semantic", entry.get("meaning", "")))
        if sem in ("逆断层", "推覆体边界"):
            out.add(str(code))
    return out


def activity_codes(gsem: dict, norm_sem) -> set:
    """活动断层码集（活动性层，注册表驱动）：语义=活动断层的码。"""
    out = set()
    for code, entry in gsem.items():
        if not isinstance(entry, dict):
            continue
        sem = norm_sem(entry.get("semantic", entry.get("meaning", "")))
        if sem == "活动断层":
            out.add(str(code))
    return out
