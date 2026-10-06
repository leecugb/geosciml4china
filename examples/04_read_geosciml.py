# -*- coding: utf-8 -*-
"""04 — GeoSciML 读取：成员计数、断层类型分布、XSD 校验（只读，PyPI 环境可跑）。

    python 04_read_geosciml.py --gml D:/my-sheet/output/geosciml/<key>_geosciml_full.gml
       [--xsd]

示例：
    python 04_read_geosciml.py --key mykey --xsd   # 经注册表解析 GML 路径
"""
import argparse
from pathlib import Path

from lxml import etree

NS = {"gsmlb": "http://www.opengis.net/gsml/4.1/GeoSciML-Basic"}
GML_ID = "{http://www.opengis.net/gml/3.2}id"


def main() -> int:
    ap = argparse.ArgumentParser(description="GeoSciML GML 只读检查")
    ap.add_argument("--gml", default=None, help="GML 路径（缺省经 --key 注册表解析）")
    ap.add_argument("--key", default=None, help="已注册图幅键")
    ap.add_argument("--xsd", action="store_true", help="附加官方 XSD 全文档校验")
    args = ap.parse_args()

    if not args.gml:
        if not args.key:
            print("!! 需要 --gml 或 --key")
            return 2
        from geosciml4china.sheets import get_sheet
        args.gml = str(Path(get_sheet(args.key).root) / "output" / "geosciml"
                       / f"{args.key}_geosciml_full.gml")
    gml = Path(args.gml)
    if not gml.exists():
        print(f"!! GML 缺席: {gml}")
        return 1

    doc = etree.parse(str(gml))
    from collections import Counter
    kinds = Counter()
    sds_types = Counter()
    for m in doc.findall(".//gsmlb:MappedFeature", NS):
        kinds["MappedFeature"] += 1
    for u in doc.findall(".//gsmlb:GeologicUnit", NS):
        kinds["GeologicUnit"] += 1
    for c in doc.findall(".//gsmlb:Contact", NS):
        kinds["Contact"] += 1
    for s in doc.findall(".//gsmlb:ShearDisplacementStructure", NS):
        kinds["ShearDisplacementStructure"] += 1
        ft = s.find("gsmlb:faultType", NS)
        sds_types[ft.get("{http://www.w3.org/1999/xlink}href", "?") if ft is not None
                   else "nil"] += 1
    for f in doc.findall(".//gsmlb:Foliation", NS):
        kinds["Foliation"] += 1
    for fo in doc.findall(".//gsmlb:Fold", NS):
        kinds["Fold"] += 1
    print(f"== {gml.name} ==")
    print(f"成员: {sum(kinds.values())}  "
          + " ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    print("断层类型 (faultType):")
    for ft, n in sds_types.most_common():
        print(f"  {ft}: {n}")

    if args.xsd:
        from geosciml4china.convert.validate import schema
        xsd = schema()   # geoSciMLExtension.xsd + LocalResolver（XSD 树内相对引用）
        ok = xsd.validate(doc)
        print(f"XSD 校验: {'通过（0 错误）' if ok else '失败: ' + str(xsd.error_log)[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
