"""Core XML building blocks for GeoSciML emission.

Design rules (from geosciml_4.1_encoding_guide.md, all validated):
- Property order is enforced here by ``SlotWriter`` (build-time), with the
  full-document XSD validation as the independent second gate.
- Axis flip lon/lat (input CRS84) -> lat/lon (GML EPSG:4326) happens ONLY in
  the ``geom_*`` builders. Lite/GeoJSON output never touches these.
- Empty properties are omitted, never written as empty elements.
- Vocabulary references are empty elements with xlink:href + xlink:title.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from lxml import etree

from .. import config

NS = {
    "gsmlb": "http://www.opengis.net/gsml/4.1/GeoSciML-Basic",
    "gsmle": "http://www.opengis.net/gsml/4.1/GeoSciML-Extension",
    "gml": "http://www.opengis.net/gml/3.2",
    "swe": "http://www.opengis.net/swe/2.0",
    "xlink": "http://www.w3.org/1999/xlink",
}
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    "http://www.opengis.net/gsml/4.1/GeoSciML-Basic "
    "http://schemas.opengis.net/gsml/4.1/geoSciMLBasic.xsd "
    "http://www.opengis.net/gsml/4.1/GeoSciML-Extension "
    "http://schemas.opengis.net/gsml/4.1/geoSciMLExtension.xsd"
)


def qname(prefixed: str) -> str:
    prefix, local = prefixed.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def E(tag: str, *children: etree._Element, text: Any = None, **attrs: Any) -> etree._Element:
    """Create an element; ``None`` children are dropped; attribute values of
    None are dropped. ``href_``/``title_`` kwargs map to xlink attributes."""
    el = etree.Element(qname(tag))
    if text is not None:
        el.text = str(text)
    for key, value in attrs.items():
        if value is None:
            continue
        if key in ("href_", "title_"):
            el.set(qname(f"xlink:{key[:-1]}"), str(value))
        elif ":" in key:
            el.set(qname(key), str(value))
        elif key == "codeSpace":
            el.set("codeSpace", str(value))
        else:
            el.set(key, str(value))
    for child in children:
        if child is not None:
            el.append(child)
    return el


def quote_uri(text: str) -> str:
    """Percent-encode non-ASCII characters (Greek unit codes) for URIs."""
    from urllib.parse import quote

    # 2026-09-29 修：safe 移除 '+'——'+' 系合法 URI 子定界符但与单元标识
    # 裸 quote() 路径的 %2B 编码不一致（巴什库尔干 Qp3eld+Qheol 关系 href
    # 裸 '+' vs 标识 %2B → A13 未解析）。百分编码全链一致纪律。
    return quote(text, safe="/:#?&=%")


class SlotWriter:
    """Append elements to a parent in XSD sequence order.

    Raises AssertionError on any out-of-order or duplicate-non-repeatable
    slot. ``None`` elements passed to :meth:`add` are skipped (the empty
    property rule).
    """

    def __init__(
        self, parent: etree._Element, order: Sequence[str], repeatable: Iterable[str] = ()
    ) -> None:
        self._parent = parent
        self._order = list(order)
        self._repeatable = set(repeatable)
        self._last = -1

    def add(self, slot: str, element: Optional[etree._Element]) -> Optional[etree._Element]:
        if element is None:
            return None
        if slot not in self._order:
            raise AssertionError(f"unknown slot {slot!r} for {etree.QName(self._parent).localname}")
        idx = self._order.index(slot)
        if idx < self._last:
            raise AssertionError(
                f"slot order violation: {slot!r} after {self._order[self._last]!r} "
                f"in {etree.QName(self._parent).localname}"
            )
        if idx == self._last and slot not in self._repeatable:
            raise AssertionError(
                f"slot {slot!r} is not repeatable in {etree.QName(self._parent).localname}"
            )
        self._parent.append(element)
        self._last = idx
        return element


# ---------------------------------------------------------------------------
# GML head and vocabulary references
# ---------------------------------------------------------------------------


def gml_head(
    parent: etree._Element,
    description: Optional[str],
    identifier_uri: Optional[str],
    names: Sequence[Any],
) -> None:
    """Write gml:description?, gml:identifier?, gml:name* in fixed order."""
    if description:
        parent.append(E("gml:description", text=description))
    if identifier_uri:
        parent.append(
            E("gml:identifier", text=quote_uri(identifier_uri), codeSpace=config.CODE_SPACE)
        )
    for name in names:
        if isinstance(name, tuple):
            text, code_space = name
        else:
            text, code_space = name, None
        el = E("gml:name", text=text)
        if code_space:
            el.set("codeSpace", code_space)
        parent.append(el)


def xlink_ref(tag: str, uri: str, title: Optional[str] = None) -> etree._Element:
    """Empty vocabulary reference element with xlink:href + xlink:title."""
    return E(tag, href_=quote_uri(uri), title_=title or uri.rstrip("/").split("/")[-1])


def nil_ref(tag: str, reason: str) -> etree._Element:
    """Vocabulary reference to the OGC nil/unknown URI (for pending terms)."""
    return E(tag, href_=config.NIL_URI, title_=f"unknown ({reason})")


def swe_category(term_uri: str, label: str, scheme_uri: str) -> etree._Element:
    """swe:Category with identifier/label/codeSpace (§1.3 of the guide)."""
    return E(
        "swe:Category",
        E("swe:identifier", text=quote_uri(term_uri)),
        E("swe:label", text=label),
        E("swe:codeSpace", href_=quote_uri(scheme_uri)),
        **{"definition": scheme_uri},
    )


def swe_quantity(value: Any, uom: str = "deg") -> etree._Element:
    """swe:Quantity with uom; bare ``code`` attribute matches the officially
    validated numericAge instance (no xlink:href on swe:uom)."""
    return E(
        "swe:Quantity",
        E("swe:uom", code=uom),
        E("swe:value", text=fmt(value)),
    )


def gsml_qty_range(value: Any, uom: str = "deg") -> etree._Element:
    """Single-valued GSML_QuantityRange: lower=upper, swe:value written twice."""
    text = fmt(value)
    return E(
        "gsmlb:GSML_QuantityRange",
        E("swe:uom", code=uom),
        E("swe:value", text=f"{text} {text}"),
        E("gsmlb:lowerValue", text=text),
        E("gsmlb:upperValue", text=text),
    )


def gsml_qty_range_pair(lo: Any, hi: Any, uom: str = "Ma") -> etree._Element:
    """Ranged GSML_QuantityRange (lower <= upper)."""
    return E(
        "gsmlb:GSML_QuantityRange",
        E("swe:uom", href_=f"http://www.opengis.net/def/uom/OGC/1.0/{uom}", code=uom),
        E("swe:value", text=f"{fmt(lo)} {fmt(hi)}"),
        E("gsmlb:lowerValue", text=fmt(lo)),
        E("gsmlb:upperValue", text=fmt(hi)),
    )


# ---------------------------------------------------------------------------
# Geometry (axis flip happens HERE and only here)
# ---------------------------------------------------------------------------


def fmt(value: Any) -> str:
    """Shortest round-trip repr for floats (lossless); str() otherwise."""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _flip(coords: Iterable[Sequence[float]]) -> List[Tuple[Any, Any]]:
    """lon,lat -> lat,lon for GML EPSG:4326."""
    return [(y, x) for x, y, *rest in coords]


def _pos_list(coords: Iterable[Sequence[float]]) -> str:
    flipped = _flip(coords)
    return " ".join(f"{fmt(a)} {fmt(b)}" for a, b in flipped)


def geom_point(coords: Sequence[float], gml_id: str) -> etree._Element:
    """GeoJSON Point [lon, lat] -> gml:Point (lat lon)."""
    lon, lat = coords[0], coords[1]
    return E(
        "gml:Point",
        E("gml:pos", text=f"{fmt(lat)} {fmt(lon)}"),
        **{"gml:id": gml_id, "srsName": "urn:ogc:def:crs:EPSG::4326", "srsDimension": "2"},
    )


def geom_linestring(coords: Sequence[Sequence[float]], gml_id: str) -> etree._Element:
    """GeoJSON LineString -> gml:LineString with gml:posList."""
    return E(
        "gml:LineString",
        E("gml:posList", text=_pos_list(coords), srsDimension="2"),
        **{"gml:id": gml_id, "srsName": "urn:ogc:def:crs:EPSG::4326"},
    )


def _linear_ring(coords: Sequence[Sequence[float]]) -> etree._Element:
    return E(
        "gml:LinearRing",
        E("gml:posList", text=_pos_list(coords), srsDimension="2"),
    )


def geom_polygon(rings: Sequence[Sequence[Sequence[float]]], gml_id: str) -> etree._Element:
    """GeoJSON Polygon coordinate array ([[exterior], [hole1], ...])."""
    polygon = E(
        "gml:Polygon",
        E("gml:exterior", _linear_ring(rings[0])),
        **{"gml:id": gml_id, "srsName": "urn:ogc:def:crs:EPSG::4326", "srsDimension": "2"},
    )
    for hole in rings[1:]:
        polygon.append(E("gml:interior", _linear_ring(hole)))
    return polygon


def geom_from_geojson(geometry: Dict[str, Any], gml_id: str) -> etree._Element:
    """Dispatch on GeoJSON geometry type; MultiPolygon -> gml:MultiSurface."""
    gtype = geometry["type"]
    coords = geometry["coordinates"]
    if gtype == "Point":
        return geom_point(coords, gml_id)
    if gtype == "LineString":
        return geom_linestring(coords, gml_id)
    if gtype == "Polygon":
        return geom_polygon(coords, gml_id)
    if gtype == "MultiPolygon":
        ms = E(
            "gml:MultiSurface",
            **{"gml:id": gml_id, "srsName": "urn:ogc:def:crs:EPSG::4326", "srsDimension": "2"},
        )
        for i, polygon in enumerate(coords):
            ms.append(E("gml:surfaceMember", geom_polygon(polygon, f"{gml_id}.{i + 1}")))
        return ms
    raise ValueError(f"unsupported geometry type {gtype}")


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------


def new_document() -> etree._Element:
    """Create the gsmlb:GSML root element with full namespace declarations."""
    nsmap = {
        "gsmlb": NS["gsmlb"],
        "gsmle": NS["gsmle"],
        "gml": NS["gml"],
        "swe": NS["swe"],
        "xlink": NS["xlink"],
        "xsi": XSI,
    }
    root = etree.Element(qname("gsmlb:GSML"), nsmap=nsmap)
    root.set(qname("gml:id"), f"kurgan.{config.SHEET}")
    root.set(f"{{{XSI}}}schemaLocation", SCHEMA_LOCATION)
    return root


def member(feature: etree._Element) -> etree._Element:
    return E("gsmlb:member", feature)
