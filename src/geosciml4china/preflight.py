"""图幅预检（2026-09-29 用户裁定）：处理一个 MapGIS 图幅前，先检查 11 文件完整性。

- 完整性=存在 + 可读（pymapgis Reader 实际打开读要素数）；
- CORE 缺失 → 失败中止（fail-stop）；CONDITIONAL 缺失 → 声明登记继续；
- 返回 (ok, rows)；`g4c check --sheet K` 为其 CLI 面。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .scope import (CONDITIONAL_FILES, CORE_FILES, OFFICIAL_LAYER_NAMES,
                    SCOPE_FILES)
from .sheets import get_sheet


@dataclass
class FileCheck:
    fname: str
    layer_name: str
    tier: str            # "CORE" | "CONDITIONAL"
    present: bool
    n_features: int | None  # 可读时为要素数
    note: str = ""


def check_scope_files(sheet_key: str, *, read: bool = True) -> tuple[bool, list[FileCheck]]:
    """11 文件完整性检查。read=True 时实际打开文件读要素数（完整性实证）。"""
    sh = get_sheet(sheet_key)
    rows: list[FileCheck] = []
    for fname in sorted(SCOPE_FILES):
        tier = "CORE" if fname in CORE_FILES else "CONDITIONAL"
        p = sh.root / fname
        if not p.exists():
            rows.append(FileCheck(fname, OFFICIAL_LAYER_NAMES[fname], tier,
                                  False, None,
                                  "缺失——" + ("中止" if tier == "CORE"
                                              else "声明登记，继续")))
            continue
        n = None
        note = ""
        if read:
            try:
                import os
                from pymapgis import Reader
                cwd = os.getcwd()
                os.chdir(sh.root)
                try:
                    with Reader(fname) as r:
                        n = len(r.geodataframe)
                finally:
                    os.chdir(cwd)
            except Exception as e:  # 存在但不可读=不完整
                note = f"读取失败: {type(e).__name__}"
                rows.append(FileCheck(fname, OFFICIAL_LAYER_NAMES[fname], tier,
                                      False, None, note))
                continue
        rows.append(FileCheck(fname, OFFICIAL_LAYER_NAMES[fname], tier,
                              True, n, note))
    ok = all(r.present for r in rows if r.tier == "CORE")
    return ok, rows


def format_report(sheet_key: str, rows: list[FileCheck]) -> str:
    sh = get_sheet(sheet_key)
    lines = [f"图幅预检（11 文件完整性）：{sh.title}（{sh.root}）", ""]
    for r in rows:
        mark = "OK" if r.present else ("!!" if r.tier == "CORE" else "--")
        cnt = f"{r.n_features} 要素" if r.n_features is not None else ""
        lines.append(f"  [{mark}] {r.fname:16s} {r.layer_name:14s} "
                     f"{r.tier:11s} {cnt} {r.note}")
    n_ok = sum(1 for r in rows if r.present)
    lines.append("")
    lines.append(f"在位 {n_ok}/11（CORE 缺 "
                 f"{sum(1 for r in rows if r.tier == 'CORE' and not r.present)}，"
                 f"CONDITIONAL 缺 "
                 f"{sum(1 for r in rows if r.tier == 'CONDITIONAL' and not r.present)}）")
    return "\n".join(lines)


def main() -> int:
    import argparse
    from .sheets import list_sheets
    ap = argparse.ArgumentParser(prog="g4c check")
    ap.add_argument("--sheet", choices=[s.key for s in list_sheets()],
                    required=True)
    ap.add_argument("--no-read", action="store_true", help="只查存在性不读文件")
    args = ap.parse_args()
    ok, rows = check_scope_files(args.sheet, read=not args.no_read)
    print(format_report(args.sheet, rows))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
