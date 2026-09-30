"""Document assembly for the full GML output."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from lxml import etree

from .xmlcore import member, new_document


def assemble(features: Iterable[etree._Element]) -> etree._Element:
    root = new_document()
    for feature in features:
        root.append(member(feature))
    return root


def write(root: etree._Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tree = etree.ElementTree(root)
    tree.write(
        str(path),
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    )
