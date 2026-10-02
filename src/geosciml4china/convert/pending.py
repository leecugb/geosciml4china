"""pending_review.md generator (adjudication-friendly checklist)."""

from __future__ import annotations

import json
from pathlib import Path

from . import config, mapping

_TITLES = {
    "P-GZBD-02": "第四系界线 → contacttype",
    "P-GZBD-24": "平行不整合界线 → contacttype",
    "P-GZBD-43": "岩性过渡渐变界线 → contacttype",
    "P-GZBD-60": "脉动接触界线 → contacttype",
    "P-DYKE-AGE-δ": "δ 闪长岩岩脉 → 侵位时代",
    "P-DYKE-AGE-υ": "υ 辉长岩岩脉 → 侵位时代",
    "P-DYKE-AGE-τα": "τα 粗面安山岩 → 侵位时代",
    "P-DYKE-AGE-βμ": "βμ 辉绿岩脉 → 侵位时代",
    "P-DYKE-AGE-γρ": "γρ 花岗伟晶岩脉 → 侵位时代",
    "P-LITH-γπ": "γπT3 花岗斑岩 → simplelithology",
    "P-LITH-βμ": "βμ 辉绿岩 → simplelithology",
    "P-LITH-τα": "τα 粗面安山岩 → simplelithology",
    "P-LITH-DYKE": "岩脉形态表达（bodyMorphology）",
    "P-GNEISS": "片麻理产状（4 点，宿主 Pt1K）→ foliationtype",
    "P-AGE-QP2": "中更新统（Qp2l/Qp2W）年代 URI",
    "P-ACTIVE-37": "活动断层（37）来源核对",
    "P-CONTACTREL": "younger_side 183 条 → ContactRelation",
    "P-FOSSIL-27": "化石点 → GeologicSpecimenView",
    "P-NAMESPACE": "正式标识符命名空间",
    "P-PAIR-F085-1": "F085 测点① 注释配对二义（注释① vs 注释②）",
    "P-PAIR-F039-1": "F039 测点① 注释配对二义（注释① vs 注释②）",
    "P-PAIR-F117-1": "F117 测点① 注释配对二义（注释① vs 注释②）",
    "P-AUX-1700-1701": "1700/1701 被遗弃倾向-倾角对（L1 异常点不入产品；反置纠错 vs 弃对剔除）",
}


def _fallback_section(lines: list, fb_csv: Path) -> None:
    """兜底码提示节（2026-09-29 用户对齐裁定：兜底机制=管线流正常推进+
    待标定项档案记录）。标定运行产生的特殊码兜底档案非空时列入裁定单；
    只提示不改词表——回填 gzbd_contacttype 节（status=decided）由人工执行。"""
    if not fb_csv.exists():
        return
    import csv as _csv
    from collections import Counter as _C
    with open(fb_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(_csv.DictReader(f))
    if not rows:
        return
    counts = _C(str(r.get("GZBD原码", "")).strip() for r in rows)
    lines.append("## 特殊码兜底登记（标定域外码 → 一般地质界线兜底）")
    lines.append("")
    lines.append("以下 GZBD 码不在标定域 {01,02,04,10,11,16,24,43,60,81}，"
                 "已按「一般地质界线」兜底（管线照常推进），档案："
                 "`_gzbd_special_fallback.csv`。")
    lines.append("裁定后请回填 `data/geosciml_vocab_mapping.json` 的 "
                 "`gzbd_contacttype` 节（status=decided），本节随档案清空自动消失。")
    lines.append("")
    lines.append("| 码 | 段数 | 建议 |")
    lines.append("|---|---|---|")
    for code, n in sorted(counts.items()):
        lines.append(f"| {code} | {n} | 查图例/词典定码义；定后回填 decided |")
    lines.append("")


def write(path: Path) -> None:
    items = mapping.pending()
    lines = [
        f"# GeoSciML 待定映射裁定单（{config.SHEET_TITLE}）",
        "",
        f"生成: {__import__('datetime').date.today().isoformat()} · 用法: 每项勾一个 ☐→☑（或写“自定义: <词>”），",
        "回填后把勾选项交给机器更新 `data/geosciml_vocab_mapping.json` 的 pending 节（status=decided）。",  # noqa: E501
        "",
    ]
    machine = {}
    for item in items:
        ref = item["ref"]
        title = _TITLES.get(ref, item.get("scope", ref))
        count = item.get("count", 0)
        lines.append(f"## {ref} {title}（影响 {count} 条）")
        lines.append("")
        lines.append(f"范围: `{item.get('scope','')}`；现状: 首版 nil/省略")
        lines.append("")
        rec = item.get("recommend")
        for cand in item.get("candidates", []):
            mark = "（推荐草案）" if cand == rec else ""
            lines.append(f"- ☐ {cand}{mark}")
        lines.append("- 自定义: ______")
        lines.append("")
        machine[ref] = None
    _fallback_section(lines, config.SHEET_ROOT / "_gzbd_special_fallback.csv")
    lines.append("---")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(machine, ensure_ascii=False, indent=1))
    lines.append("```")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"pending list written: {path} ({len(items)} items)")
