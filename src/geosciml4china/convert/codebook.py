# -*- coding: utf-8 -*-
"""convert 消费侧 codebook 装载（2026-10-06 用户裁定：后续转换 GeoSciML
建立在 codebook JSON 上）。

build.py 三通道以 codebook 为语义基础（codebook 在场时）：
  · faultType：GZEEB 码 → codebook 语义（注册表/用户编辑覆盖段级标定，
    矛盾保留段维持 L1 段级语义）
  · contactType：GZBD 码 → codebook 语义（分歧未裁定段维持 L1 段级语义）
  · movementSense：GZELD 码 → codebook 语义（钩线旋向仍居先）
codebook 缺席（PyPI 极简/未跑校准环境）→ 返回 None，build 回退现行
L1 通道（向后兼容，字节稳定）。
"""
from __future__ import annotations

from pathlib import Path

from ..calibrate import codebook as _cb_mod
from . import config

_cache: dict = {}


def load():
    """当前图幅的 codebook（config.init_sheet 之后调用）；缺席→None。

    mtime 感知缓存（2026-10-06 td e2e 教训：用户编辑 codebook 后同进程
    重跑 build 必须读到新文件——旧缓存会让编辑静默失效）。
    """
    key = getattr(config, "SHEET_KEY", None)
    if not key:
        return None
    p = _cb_mod.codebook_path(Path(config.SHEET_ROOT), key)
    mt = p.stat().st_mtime if p.exists() else None
    hit = _cache.get(key)
    if hit and hit[0] == mt:
        return hit[1]
    cb = _cb_mod.load_codebook(Path(config.SHEET_ROOT), key)
    _cache[key] = (mt, cb)
    return cb


def sem_of(cb, family: str, code) -> str:
    """codebook 语义解析（注册表 > 用户编辑 > 校准推导）；缺席→''。"""
    return _cb_mod.semantic_of(cb, family, code)
