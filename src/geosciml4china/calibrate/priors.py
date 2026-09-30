"""先验知识装载（geosciml4china.calibrate）。

权威架构（2026-09-20 用户定，入包 2026-09-29）：
- **主本** = 包数据 `boundary_contact_priors.json`（新疆区域界线接触关系先验库，
  双料最高知识源：接触关系+新老关系；adjudicated 用户核验居首 > memoir 志书 >
  inferred > generic_rules > GZBD 兜底）；
- **图幅扩展册** = `<sheet_root>/data/boundary_contact_priors_<key>.json`
  （单元对区域扩展/本幅裁定追加；合并规则：sheet 条目追加到 unit_pair_rules，
  同（码对归一化）键裁定层覆盖区域层）；
- 修改纪律：只经裁定流程编辑主本；`_check_knowledge_sync` 一致性校验（色库镜像
  stratigraphic_contacts/group_composition 与本库同步）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..data import data_path
from ..sheets import get_sheet


def _norm_code(c: str) -> str:
    return re.sub(r"[→↓↑.]", "", str(c)).strip()


def load_priors(sheet_key: str | None = None) -> dict:
    """区域主本 + （可选）图幅扩展册合并。无扩展册→主本原样。"""
    base = json.loads(data_path("boundary_contact_priors.json")
                      .read_text(encoding="utf-8"))
    if not sheet_key:
        return base
    sh = get_sheet(sheet_key)
    ext = sh.root / "data" / f"boundary_contact_priors_{sh.key}.json"
    if not ext.exists():
        return base
    overlay = json.loads(ext.read_text(encoding="utf-8"))
    out = dict(base)
    base_keys = {tuple(sorted(_norm_code(c) for c in (r.get("codes") or [])))
                 for r in base.get("unit_pair_rules", []) if r.get("codes")}
    for r in overlay.get("unit_pair_rules", []):
        k = tuple(sorted(_norm_code(c) for c in (r.get("codes") or [])))
        if r.get("codes") and k in base_keys:
            # 同键裁定层覆盖：替换区域层条目
            out["unit_pair_rules"] = [
                (r if tuple(sorted(_norm_code(c) for c in (x.get("codes") or []))) == k
                 else x)
                for x in out["unit_pair_rules"]]
        else:
            out.setdefault("unit_pair_rules", []).append(r)
    for sect in ("generic_rules", "age_order_priors", "gaps_pending"):
        if overlay.get(sect):
            out.setdefault(sect, [])
            out[sect] = out[sect] + overlay[sect] \
                if isinstance(out[sect], list) else {**out[sect], **overlay[sect]}
    if overlay.get("alias_map"):
        out.setdefault("alias_map", {}).update(overlay["alias_map"])
    out["_meta"] = dict(base.get("_meta", {}),
                        sheet_overlay=str(ext), sheet=sh.key)
    return out
