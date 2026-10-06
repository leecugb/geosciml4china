"""g4c 统一命令行入口。

零注入接入三步（新图幅最快路径）：

    g4c probe --root D:/my-sheet --key mykey --register   # 普查+注册（零外部信息）
    g4c check --sheet mykey                               # 11 文件预检
    g4c pipeline --sheet mykey --accept-portrait          # 全链（首跑落盘画像）

子命令（转发现有一切 main()，参数面零变化）：

- ``g4c probe --root P --key K [--register]``   零注入普查；--register 运行时注册
- ``g4c sheets``                                列出已注册图幅（root 解析后）
- ``g4c check --sheet K``                       图幅预检（11 文件完整性，处理前必过）
- ``g4c data``                                  列出包数据路径与存在性
- ``g4c pipeline --sheet K``                    全链：MapGIS 文件夹→标定→转换→渲染
                                                （--skip-convert/--skip-calibrate-stages/
                                                --skip-render/--check-only/--accept-portrait/
                                                --no-pattern/--dpi N）
- 标定域（可按域单独执行）：
    calibrate-gzbd / entities / auxchain / calibrate-gzeeb /
    calibrate-fault-contact-activity / calibrate-attitudes /
    calibrate-fossils / calibrate-folds / calibrate-inferred-faults
    （均 ``--sheet K``；另 report-gaps 输出缺口报告+单要素配图）
- 转换与渲染：
    ``g4c stylegen --sheet K``     面元样式生成（render.stylegen）
    ``g4c stylegen-fault --sheet K``  断层样式生成（render.stylegen_fault）
    ``g4c build --sheet K``        L1 → GeoSciML GML+Lite（convert.build）
    ``g4c verify --sheet K``       XSD+29 业务断言（convert.verify；
                                   --write-portrait/--accept-portrait）
    ``g4c render --sheet K``       渲染 + C1-C7 镜像核验（--no-overlay/
                                   --check-only/--full-extent/--no-pattern）

管线序：**stylegen → build → verify**（render 前 F3 样式重生自动兜底）。
"""
from __future__ import annotations

import sys


def _delegate(fn, prog: str, argv: list[str]) -> int:
    old = sys.argv
    sys.argv = [prog, *argv]
    try:
        r = fn()
        return int(r or 0)
    finally:
        sys.argv = old


def _sheets() -> int:
    from .sheets import list_sheets
    for sh in list_sheets():
        ok = "OK" if sh.root.exists() else "!! root 不存在"
        print(f"{sh.key:12s} {sh.code}  root={sh.root}  {ok}")
        print(f"             {sh.title}")
    return 0


def _data() -> int:
    from . import data as d
    for name in ("DZT0179_COLOR_LIBRARY", "DZT0179_PATTERN_REGISTRY",
                 "CGI_TERMS", "CGI_VOCABS_DIR", "ICS_ERAS"):
        p = getattr(d, name)
        print(f"{name:28s} {'OK' if p.exists() else '!!'}  {p}")
    try:
        p = d.xsd_root()
        n = sum(1 for _ in p.rglob("*.xsd"))
        print(f"{'XSD_ROOT':28s} OK  {p}  ({n} 个 .xsd)")
    except FileNotFoundError as e:
        print(f"{'XSD_ROOT':28s} !!  {e}")
        return 1
    return 0


_DELEGATES = {
    "pipeline": ("geosciml4china.pipeline", "main"),
    "calibrate-gzbd": ("geosciml4china.calibrate.gzbd", "main"),
    "entities": ("geosciml4china.calibrate.entities", "main"),
    "auxchain": ("geosciml4china.calibrate.auxchain", "main"),
    "calibrate-gzeeb": ("geosciml4china.calibrate.gzeeb", "main"),
    "calibrate-attitudes": ("geosciml4china.calibrate.attitudes", "main"),
    "calibrate-fossils": ("geosciml4china.calibrate.fossils", "main"),
    "calibrate-folds": ("geosciml4china.calibrate.folds", "main"),
    "report-gaps": ("geosciml4china.render.gap_report", "main"),
    "calibrate-inferred-faults":
        ("geosciml4china.calibrate.inferred_faults", "main"),
    "calibrate-fault-contact-activity":
        ("geosciml4china.calibrate.fault_contact_activity", "main"),
    "stylegen": ("geosciml4china.render.stylegen", "main"),
    "stylegen-fault": ("geosciml4china.render.stylegen_fault", "main"),
    "build": ("geosciml4china.convert.build", "main"),
    "verify": ("geosciml4china.convert.verify", "main"),
    "render": ("geosciml4china.render.render", "main"),
    "probe": ("geosciml4china.probe", "main"),
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "sheets":
        return _sheets()
    if cmd == "data":
        return _data()
    if cmd == "check":
        from . import preflight
        return _delegate(preflight.main, "g4c check", rest)
    ent = _DELEGATES.get(cmd)
    if ent is None:
        print(f"未知子命令 {cmd!r}（可选：sheets/data/{'/'.join(_DELEGATES)}）",
              file=sys.stderr)
        return 2
    import importlib
    fn = getattr(importlib.import_module(ent[0]), ent[1])
    return _delegate(fn, f"g4c {cmd}", rest)


if __name__ == "__main__":
    sys.exit(main())
