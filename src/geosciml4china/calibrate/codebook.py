# -*- coding: utf-8 -*-
"""图幅 codebook（编码-地质语义映射表，2026-10-06 用户裁定）：

    「geosciml4china 完成编码-地质语义解析后，应以 json 格式输出映射表，
     并允许用户修改 json，后续转换 geosciml 应建立在这个 json 基础上。
     这个 json 文件就是 codebook」

**codebook_<key>.json 就是 codebook**——L2 码级语义的单一权威工件：
  · 生产：校准域产物（code_semantics_map/boundary_semantics_map/
    gzeld_semantics_map 三 CSV）+ 图幅注册表 + 包数据全局先验合并生成；
  · 用户修改：直接编辑 JSON（user_semantic/user_note 字段跨轮保留）；
  · 消费：convert.build 以 codebook 为唯一语义基础（注册表 > 用户编辑
    > 全局先验 > 校准推导 > 泛称兜底）；codebook 缺席时回退现行 L1 通道
    （向后兼容，PyPI/CI 极简环境不受影响）。

管线钩子：② 校准阶段末尾（终态物化后）重新生成并保留用户编辑。
CLI: g4c codebook --sheet K（重新生成 + 摘要）。
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

import pandas as pd

from ..data import data_path
from ..sheets import get_sheet

CODEBOOK_SCHEMA = "geosciml4china/codebook/v1"

# 族 → (CSV 映射表名, 码列名)
_FAMILIES = {
    "GZEEB": ("code_semantics_map_{key}.csv", "GZEEB"),
    "GZBD": ("boundary_semantics_map_{key}.csv", "GZBD"),
    "GZELD": ("gzeld_semantics_map_{key}.csv", "GZELD"),
}


def codebook_path(root: Path, key: str) -> Path:
    return Path(root) / f"codebook_{key}.json"


def _norm_code(c) -> str:
    return str(c).strip().zfill(2)


def _load_csv_entries(root: Path, key: str) -> dict:
    """三 CSV 映射表 → {family: {code: entry}}（校准推导层）。"""
    out = {}
    for fam, (tmpl, code_col) in _FAMILIES.items():
        p = root / tmpl.format(key=key)
        if not p.exists():
            continue
        df = pd.read_csv(p, dtype=str)
        fam_d = {}
        for _, r in df.iterrows():
            code = _norm_code(r.get(code_col) or "")
            if not code.strip("0"):
                continue
            fam_d[code] = {
                "semantic": str(r.get("semantic") or "").strip(),
                "source": str(r.get("source") or "校准推导").strip(),
                "segs": int(float(r.get("segs") or 0)),
                "confidence": str(r.get("confidence") or "").strip(),
                "user_semantic": str(r.get("user_semantic") or "").strip(),
                "user_note": str(r.get("user_note") or "").strip(),
            }
        out[fam] = fam_d
    return out


def _load_registry(root: Path, key: str) -> dict:
    """图幅注册表（fault_semantics_<key>.json）→ {family: {code: entry}}。

    注册表居最高权威（2026-10-04 裁定链：图幅注册表 > 用户编辑 > 全局
    先验 > 统计推导）；条目 source=registry。
    """
    p = root / f"fault_semantics_{key}.json"
    if not p.exists():
        return {}
    j = json.load(open(p, encoding="utf-8"))
    out = {}
    for fam, jkey in (("GZEEB", "gzeeb_semantics"),
                      ("GZELD", "gzeld_semantics")):
        fam_d = {}
        for code, ent in (j.get(jkey) or {}).items():
            sem = ent.get("semantic", ent) if isinstance(ent, dict) else str(ent)
            note = ent.get("verdict", "") if isinstance(ent, dict) else ""
            fam_d[_norm_code(code)] = {
                "semantic": str(sem).strip(), "source": "registry",
                "segs": 0, "confidence": "adjudicated",
                "user_semantic": "", "user_note": str(note)[:200],
            }
        if fam_d:
            out[fam] = fam_d
    return out


def _load_global_priors() -> dict:
    """包数据全局先验（GZELD 101-104；2026-10-04 裁定）。"""
    try:
        j = json.load(open(data_path("gzeld_codes.json"), encoding="utf-8"))
    except Exception:
        return {}
    fam_d = {}
    for code, ent in (j.get("gzeld_semantics") or {}).items():
        sem = ent.get("semantic", ent) if isinstance(ent, dict) else str(ent)
        fam_d[_norm_code(code)] = {
            "semantic": str(sem).strip(), "source": "global_prior",
            "segs": 0, "confidence": "", "user_semantic": "", "user_note": "",
        }
    return {"GZELD": fam_d} if fam_d else {}


def load_codebook(root: Path, key: str) -> dict | None:
    p = codebook_path(root, key)
    if not p.exists():
        return None
    return json.load(open(p, encoding="utf-8"))


def build_codebook(sheet_key: str, out_dir=None) -> dict:
    """合并生成 codebook_<key>.json（用户编辑跨轮保留）。

    合并权威序（低→高覆盖）：校准推导（CSV）→ 全局先验（补缺）→
    图幅注册表（覆盖 semantic）→ 既有 codebook 的 user_* 字段（保留）。
    """
    sh = get_sheet(sheet_key)
    root = Path(out_dir) if out_dir else Path(sh.root)
    root.mkdir(parents=True, exist_ok=True)

    codes = _load_csv_entries(root, sheet_key)
    # 全局先验补缺（不覆盖校准推导）
    for fam, fam_d in _load_global_priors().items():
        dst = codes.setdefault(fam, {})
        for code, ent in fam_d.items():
            dst.setdefault(code, ent)
    # 图幅注册表覆盖（最高权威）
    for fam, fam_d in _load_registry(root, sheet_key).items():
        dst = codes.setdefault(fam, {})
        dst.update(fam_d)
    # 既有 codebook 的用户编辑跨轮保留（注册表条目豁免——注册表权威更高）
    old = load_codebook(root, sheet_key)
    if old:
        for fam, fam_d in (old.get("codes") or {}).items():
            dst = codes.get(fam)
            if dst is None:
                continue
            for code, ent in fam_d.items():
                if code not in dst:
                    continue
                if dst[code]["source"] == "registry":
                    continue
                u = str(ent.get("user_semantic") or "").strip()
                n = str(ent.get("user_note") or "").strip()
                if u and u not in ("nan", "None"):
                    dst[code]["user_semantic"] = u
                if n and n not in ("nan", "None"):
                    dst[code]["user_note"] = n

    cb = {
        "codebook": CODEBOOK_SCHEMA,
        "sheet": sheet_key,
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "authority": "registry > user_semantic > global_prior > calibration "
                     "> generic fallback",
        "codes": codes,
    }
    p = codebook_path(root, sheet_key)
    p.write_text(json.dumps(cb, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return cb


def semantic_of(cb: dict | None, family: str, code) -> str:
    """codebook 语义解析（消费侧唯一入口）：registry > user > 校准推导。"""
    if not cb:
        return ""
    ent = ((cb.get("codes") or {}).get(family) or {}).get(_norm_code(code))
    if not ent:
        return ""
    if ent.get("source") == "registry":
        return str(ent.get("semantic") or "").strip()
    u = str(ent.get("user_semantic") or "").strip()
    if u and u not in ("nan", "None"):
        return u
    return str(ent.get("semantic") or "").strip()


def summary(cb: dict) -> str:
    lines = [f"codebook {cb['sheet']}（{cb['codebook']}，生成 {cb['generated']}）"]
    for fam, fam_d in cb["codes"].items():
        n_user = sum(1 for e in fam_d.values()
                     if str(e.get("user_semantic") or "").strip())
        n_reg = sum(1 for e in fam_d.values() if e.get("source") == "registry")
        lines.append(f"  {fam}: {len(fam_d)} 码"
                     f"（注册表 {n_reg} / 用户编辑 {n_user}）")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(prog="g4c codebook",
                                 description="生成图幅 codebook（编码-地质"
                                             "语义映射表 JSON，用户可改，"
                                             "转换唯一语义基础）")
    ap.add_argument("--sheet", required=True)
    args = ap.parse_args()
    cb = build_codebook(args.sheet)
    print(summary(cb))
    print(f"已写出: {codebook_path(Path(get_sheet(args.sheet).root), args.sheet)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
