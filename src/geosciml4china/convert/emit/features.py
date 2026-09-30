"""Feature-level GeoSciML emitters (one function per feature class)."""

from __future__ import annotations

from typing import Optional

from lxml import etree

from .. import config, model, vocab
from . import sequences
from .xmlcore import (
    E,
    SlotWriter,
    geom_from_geojson,
    gml_head,
    gsml_qty_range,
    nil_ref,
    quote_uri,
    swe_category,
    swe_quantity,
    xlink_ref,
)


def _category_obs(term: Optional[str], label: str) -> Optional[etree._Element]:
    if not term:
        return None
    uri, lbl = vocab.cgi_term("featureobservationmethod", term)
    scheme = "http://resource.geosciml.org/classifierscheme/cgi/2016.01/featureobservationmethod"
    return E("gsmlb:observationMethod", swe_category(uri, lbl, scheme))


def emit_geologic_event(ev: model.EventRec, gml_id: str) -> Optional[etree._Element]:
    if ev is None:
        return None
    el = E("gsmlb:GeologicEvent", **{"gml:id": gml_id})
    w = SlotWriter(el, sequences.GEOLOGIC_EVENT, repeatable={"eventProcess"})
    if ev.eventprocess_term:
        uri, lbl = vocab.cgi_term("eventprocess", ev.eventprocess_term)
        w.add("eventProcess", xlink_ref("gsmlb:eventProcess", uri, lbl))
    if ev.numeric_pair:
        lo, hi = ev.numeric_pair
        rng = E(
            "gsmlb:NumericAgeRange",
            E("gsmlb:olderBoundDate", swe_quantity(lo, "Ma")),
            E("gsmlb:youngerBoundDate", swe_quantity(hi, "Ma")),
        )
        w.add("numericAge", E("gsmlb:numericAge", rng))
    if ev.older_era:
        w.add(
            "olderNamedAge",
            xlink_ref("gsmlb:olderNamedAge", vocab.era_uri(ev.older_era), ev.older_era),
        )
    elif not ev.numeric_pair:
        # /req/gsml4-basic/geologicevent-non-null: keep an age property present
        # with the sanctioned nil URI (dyke pending ages; clause 9.2.4).
        w.add(
            "olderNamedAge",
            nil_ref("gsmlb:olderNamedAge", "pending (P-DYKE-AGE)"),
        )
    if ev.younger_era:
        w.add(
            "youngerNamedAge",
            xlink_ref("gsmlb:youngerNamedAge", vocab.era_uri(ev.younger_era), ev.younger_era),
        )
    elif not ev.numeric_pair:
        w.add(
            "youngerNamedAge",
            nil_ref("gsmlb:youngerNamedAge", "pending (P-DYKE-AGE)"),
        )
    return el


def emit_composition(comp: model.CompositionRec, owner_id: str) -> etree._Element:
    cp = E("gsmlb:CompositionPart")
    w = SlotWriter(cp, sequences.COMPOSITION_PART)
    role_uri, role_label = vocab.cgi_term("proportionterm", comp.role)
    w.add("role", xlink_ref("gsmlb:role", role_uri, role_label))
    material = E(
        "gsmlb:material",
        E(
            "gsmlb:RockMaterial",
            E("gsmlb:lithology", href_=quote_uri(comp.lithology_uri), title_=comp.lithology_label),
            **{"gml:id": f"rock.{owner_id}"},
        ),
    )
    w.add("material", material)
    return E("gsmlb:composition", cp)


def emit_geologic_unit(u: model.UnitRec) -> etree._Element:
    el = E("gsmlb:GeologicUnit", **{"gml:id": u.gml_id})
    gml_head(el, u.description, u.uri, [(u.name, "urn:cgn:stratigraphy")])
    w = SlotWriter(el, sequences.GEOLOGIC_UNIT, repeatable=sequences.REPEATABLE["GEOLOGIC_UNIT"])
    w.add("purpose", E("gsmlb:purpose", text="typicalNorm"))
    for rel in u.relations:
        # 单元对接地关系（v2.1）：inline GeologicFeatureRelation，source=本单元
        # （年轻）、target=较老单元；relationship=已定 CGI contacttype 词
        frel = E("gsmle:GeologicFeatureRelation",
                 **{"gml:id": f"rel.{model._safe_ncname(u.norm)}.{model._safe_ncname(rel['target_norm'])}"})
        gml_head(frel, rel["note"], None, [])
        wf = SlotWriter(frel, sequences.FEATURE_RELATION)
        target_uri = quote_uri(f"{config.BASE_URI}geologicunit/{rel['target_norm']}")
        wf.add("relatedFeature", E("gsmlb:relatedFeature",
                                   href_=target_uri, title_=rel["target_norm"]))
        r_uri, r_lbl = vocab.cgi_term("contacttype", rel["term"])
        wf.add("relationship", xlink_ref("gsmle:relationship", r_uri, r_lbl))
        w.add("relatedFeature", E("gsmlb:relatedFeature", frel))
    w.add(
        "geologicHistory",
        E("gsmlb:geologicHistory", emit_geologic_event(u.event, f"ge.{model._safe_ncname(u.norm)}")),
    )

    uri, lbl = vocab.cgi_term("geologicunittype", u.unittype_term)
    w.add("geologicUnitType", xlink_ref("gsmlb:geologicUnitType", uri, lbl))
    if u.rank_term and u.rank_term != "rank_not_specified":
        ruri, rlbl = vocab.cgi_term("stratigraphicrank", u.rank_term)
        w.add("rank", xlink_ref("gsmlb:rank", ruri, rlbl))
    for comp in u.compositions:
        w.add("composition", emit_composition(comp, u.norm))
    return el


def emit_mapped_feature(mf: model.MappedFeatureRec) -> etree._Element:
    el = E("gsmlb:MappedFeature", **{"gml:id": mf.gml_id})
    gml_head(el, mf.description, mf.uri, [])
    w = SlotWriter(el, sequences.MAPPED_FEATURE, repeatable={"observationMethod"})
    w.add("observationMethod", _category_obs(mf.observation_term, mf.observation_label))
    w.add(
        "resolutionRepresentativeFraction",
        E("gsmlb:resolutionRepresentativeFraction", text=config.SCALE_DENOMINATOR),
    )
    w.add(
        "mappingFrame",
        xlink_ref("gsmlb:mappingFrame", config.MAPPING_FRAME_URI, config.MAPPING_FRAME_TERM),
    )
    w.add(
        "specification",
        E(
            "gsmlb:specification",
            href_=quote_uri(mf.specification_uri),
            title_=mf.specification_title,
        ),
    )
    w.add("shape", E("gsmlb:shape", geom_from_geojson(mf.geometry, f"{mf.gml_id}.geom")))
    return el


def emit_contact(c: model.ContactRec) -> etree._Element:
    el = E("gsmlb:Contact", **{"gml:id": c.gml_id})
    desc = f"{c.sem_label}（{c.verdict}）"
    if c.younger_side:
        desc += f"（年轻侧 {c.younger_side}）"
    if c.pending_ref:
        desc += f"（contactType 待定 {c.pending_ref}）"
    gml_head(el, desc, c.uri, [])
    w = SlotWriter(el, sequences.CONTACT, repeatable=sequences.REPEATABLE["GEOLOGIC_FEATURE"])
    w.add("observationMethod", _category_obs(c.observation_term, c.observation_label))
    w.add("purpose", E("gsmlb:purpose", text="instance"))
    if c.decided and c.contacttype_term:
        uri, lbl = vocab.cgi_term("contacttype", c.contacttype_term)
        w.add("contactType", xlink_ref("gsmlb:contactType", uri, lbl))
    else:
        w.add("contactType", nil_ref("gsmlb:contactType", c.pending_ref or "pending"))
    return el


def emit_sds(f: model.FaultRec) -> etree._Element:
    el = E("gsmlb:ShearDisplacementStructure", **{"gml:id": f.gml_id})
    # GML/lite 描述对称（2026-09-28）：description_append（28/31/37/41 活动/
    # 复活等结构层描述）此前仅 lite 出站——补齐 GML 通道
    desc = "；".join(x for x in (f.gzehg, f.description_append, f.attitude_note)
                    if x)
    gml_head(el, desc or None, f.uri, [f.fault_name or f.fault_id])
    w = SlotWriter(el, sequences.SDS, repeatable=sequences.REPEATABLE["SDS"])
    w.add("observationMethod", _category_obs(f.observation_term, f.observation_label))
    w.add("purpose", E("gsmlb:purpose", text="instance"))
    if f.faulttype_term:
        uri, lbl = vocab.cgi_term("faulttype", f.faulttype_term)
        w.add("faultType", xlink_ref("gsmlb:faultType", uri, lbl))
    else:
        w.add("faultType", nil_ref("gsmlb:faultType", "pending"))
    if f.planes:
        for plane in f.planes:
            desc_el = E("gsmle:ShearDisplacementStructureDescription")
            wd = SlotWriter(desc_el, sequences.SDS_DESCRIPTION)
            po = E("gsmlb:GSML_PlanarOrientation")
            wp = SlotWriter(po, sequences.PLANAR_ORIENTATION)
            conv_uri, conv_lbl = vocab.cgi_term("conventioncode", "dip_dip_direction")
            wp.add("convention", xlink_ref("gsmlb:convention", conv_uri, conv_lbl))
            wp.add("azimuth", E("gsmlb:azimuth", gsml_qty_range(plane.azimuth, "deg")))
            if plane.dip is not None:
                wp.add("dip", E("gsmlb:dip", gsml_qty_range(plane.dip, "deg")))
            wd.add("planeOrientation", E("gsmle:planeOrientation", po))
            w.add("stStructureDescription", E("gsmlb:stStructureDescription", desc_el))
            # DisplacementValue 块（辅助点非实体原则 2026-09-26）：
            # hangingWallDirection=dip_az（悬挂盘恒在倾向侧，与 a 无关）；
            # movementSense=a 的判别折叠（normal/reverse/no_movement_sense）
            dv = E("gsmle:DisplacementValue")
            wv = SlotWriter(dv, sequences.DISPLACEMENT_VALUE)
            lo = E("gsmlb:GSML_LinearOrientation")
            wl = SlotWriter(lo, sequences.LINEAR_ORIENTATION)
            wl.add("trend", E("gsmlb:trend", gsml_qty_range(plane.azimuth, "deg")))
            wv.add("hangingWallDirection", E("gsmle:hangingWallDirection", lo))
            if plane.movement_sense:
                ms_uri, ms_lbl = vocab.cgi_term("faultmovementsense",
                                                plane.movement_sense)
                wv.add("movementSense", xlink_ref("gsmle:movementSense",
                                                  ms_uri, ms_lbl))
            w.add("stStructureDescription", E("gsmlb:stStructureDescription", dv))
    # 走滑钩段：旋向折叠（238=dextral / 239=sinistral，与 faultType 互证）
    if f.slip_sense:
        dv = E("gsmle:DisplacementValue")
        wv = SlotWriter(dv, sequences.DISPLACEMENT_VALUE)
        ms_uri, ms_lbl = vocab.cgi_term("faultmovementsense", f.slip_sense)
        wv.add("movementSense", xlink_ref("gsmle:movementSense", ms_uri, ms_lbl))
        w.add("stStructureDescription", E("gsmlb:stStructureDescription", dv))
    return el


def emit_foliation(a: model.AttitudeRec) -> etree._Element:
    el = E("gsmlb:Foliation", **{"gml:id": a.gml_id})
    desc = (f"{a.sem_type}（{a.azimuth:g}°∠{a.dip:g}°）" if a.dip is not None
            else f"{a.sem_type}（{a.azimuth:g}°∠—倾角缺省）")
    if a.note:
        desc += f"；{a.note}"
    gml_head(el, desc, a.uri, [])
    w = SlotWriter(el, sequences.FOLIATION, repeatable=sequences.REPEATABLE["GEOLOGIC_FEATURE"])
    w.add("purpose", E("gsmlb:purpose", text="instance"))
    if a.host_norm:
        w.add(
            "relatedFeature",
            E(
                "gsmlb:relatedFeature",
                href_=quote_uri(f"{config.BASE_URI}geologicunit/{a.host_norm}"),
                title_=a.host_name or a.host_norm,
            ),
        )
    if a.foliation_term:
        uri, lbl = vocab.foliation_uri(a.foliation_term)
        w.add("foliationType", xlink_ref("gsmlb:foliationType", uri, lbl))
    else:
        w.add("foliationType", nil_ref("gsmlb:foliationType", "pending (P-GNEISS)"))
    # Extension: FoliationDescription.orientation
    desc_el = E("gsmle:FoliationDescription")
    wd = SlotWriter(desc_el, sequences.FOLIATION_DESCRIPTION)
    po = E("gsmlb:GSML_PlanarOrientation")
    wp = SlotWriter(po, sequences.PLANAR_ORIENTATION)
    conv_uri, conv_lbl = vocab.cgi_term("conventioncode", "dip_dip_direction")
    wp.add("convention", xlink_ref("gsmlb:convention", conv_uri, conv_lbl))
    wp.add("azimuth", E("gsmlb:azimuth", gsml_qty_range(a.azimuth, "deg")))
    if a.dip is not None:
        wp.add("dip", E("gsmlb:dip", gsml_qty_range(a.dip, "deg")))
    if a.overturned:
        pol_uri, pol_lbl = vocab.cgi_term("planarpolaritycode", "overturned")
        wp.add("polarity", xlink_ref("gsmlb:polarity", pol_uri, pol_lbl))
    wd.add("orientation", E("gsmle:orientation", po))
    w.add("stFoliationDescription", E("gsmlb:stFoliationDescription", desc_el))
    return el


def emit_fold(f: model.FoldRec, profile_uri: str) -> etree._Element:
    el = E("gsmlb:Fold", **{"gml:id": f.gml_id})
    gml_head(el, None, f.uri, [f.name])
    w = SlotWriter(el, sequences.FOLD, repeatable=sequences.REPEATABLE["GEOLOGIC_FEATURE"])
    w.add("purpose", E("gsmlb:purpose", text="instance"))
    if profile_uri:
        w.add("profileType", xlink_ref("gsmlb:profileType", profile_uri, f.profile_term))
    else:
        w.add("profileType", nil_ref("gsmlb:profileType", "pending"))
    return el


