"""XSD validation with a local resolver (all http schemaLocations -> local tree)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

from lxml import etree

from . import config


def xsd_root() -> Path:
    for cand in config.XSD_CANDIDATES:
        if cand is not None and cand.exists():
            return cand
    raise FileNotFoundError("GeoSciML XSD tree not found (run build step P1 copy)")


class LocalResolver(etree.Resolver):
    MAP = {
        "schemas.opengis.net/gml/": "gml/",
        "schemas.opengis.net/sampling/": "sampling/",
        "schemas.opengis.net/sweCommon/": "sweCommon/",
        "schemas.opengis.net/samplingSpatial/": "samplingSpatial/",
        "schemas.opengis.net/om/": "om/",
        "schemas.opengis.net/sams/": "sams/",
        "schemas.opengis.net/iso/19139/20070417/": "iso/19139/20070417/",
        "schemas.opengis.net/gsml/4.1/": "gsml/4.1/",
        "schemas.opengis.net/xlink/": "xlink/",
        "www.w3.org/1999/": "w3/1999/",
        "www.w3.org/2001/": "w3/2001/",
    }

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def resolve(self, url, pubid, context):
        if url.startswith("file:"):
            local = os.path.realpath(url[5:].lstrip("/"))
            if os.path.exists(local):
                return self.resolve_filename(local, context)
            return self.resolve_string(
                "<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>", context
            )
        if url.startswith("http"):
            for pre, rep in self.MAP.items():
                if pre in url:
                    local = os.path.realpath(self.root / (rep + url.split(pre, 1)[1]))
                    if os.path.exists(local):
                        return self.resolve_filename(local, context)
            return self.resolve_string(
                "<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>", context
            )
        local = os.path.realpath(self.root / url)
        if os.path.exists(local):
            return self.resolve_filename(local, context)
        return self.resolve_string(
            "<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>", context
        )


_schema_cache: Dict[str, etree.XMLSchema] = {}


def schema(name: str = "geoSciMLExtension.xsd") -> etree.XMLSchema:
    if name not in _schema_cache:
        parser = etree.XMLParser()
        parser.resolvers.add(LocalResolver(xsd_root()))
        doc = etree.parse(str(xsd_root() / "gsml" / "4.1" / name), parser)
        _schema_cache[name] = etree.XMLSchema(doc)
    return _schema_cache[name]


def validate(path, schema_name: str = "geoSciMLExtension.xsd") -> tuple:
    parser = etree.XMLParser()
    parser.resolvers.add(LocalResolver(xsd_root()))
    doc = etree.parse(str(path), parser)
    sch = schema(schema_name)
    ok = sch.validate(doc)
    return ok, sch.error_log
