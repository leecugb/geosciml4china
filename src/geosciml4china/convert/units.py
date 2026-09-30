"""Assemble the 57 GeologicUnit master records (four-way join).

Join chain (hard-wired, asserted): color-units (raw mathtext key) ->
norm -> unit_to_ics_candidate -> eventprocess/unit_type rules ->
UnitRec. Any drift between the three sources dies here at load time.
"""

from __future__ import annotations

from typing import Dict, List

from . import config, mapping, model, sources, vocab

# Greek-prefix lithology for intrusive units (decided only; pending stays empty)
_LITHOLOGY_BY_NORM = {
    "ηγT2": "monzogranite",
    "ηγP": "monzogranite",
    "γδT1": "granodiorite",
    "γοC2": "tonalite",
    "δοC2": "quartz_diorite",
    "δοP": "quartz_diorite",
    "δT1": "diorite",
    "δ": "diorite",
    "οφD1": "hornblendite",
    "νD": "gabbro",
    "υ": "gabbro",
    "γρ": "pegmatite",
}

_RANK_BY_SUFFIX = {"组": "formation", "群": "group", "段": "member", "岩群": "suite"}
_INTRUSIVE_RANK = "lithodeme"

# Regional (non-ICS) age fallback from the age table CSV (dual track)
_REGIONAL_AGE_UNITS = {"ChA", "ChSt", "Pt1K"}


def _rank_for(name: str, layer_role: str) -> str:
    if layer_role in ("侵入岩",):
        return _INTRUSIVE_RANK
    if layer_role in ("变质岩", "变质岩建造"):  # 官方名对齐（旧名兼容期）
        return "suite"
    if name.endswith("段"):
        return "member"
    if name.endswith("组"):
        return "formation"
    if name.endswith("群"):
        return "group"
    # Quaternary genetic units (冲积层/冰碛层/西域组/乌苏群 etc.)
    if name.endswith("组"):
        return "formation"
    if name.endswith("群"):
        return "group"
    return "rank_not_specified"


def build_units() -> Dict[str, model.UnitRec]:
    color_units = sources.read_color_units()
    ics_rows = sources.read_unit_to_ics()
    age_table = sources.read_age_table()

    color_norms = {u["norm"] for u in color_units.values()}
    ics_norms = set(ics_rows.keys())
    if ics_rows:  # 有 ICS 映射才强制键集相等（英吉沙未建 → 全 nil+pending）
        assert color_norms == ics_norms, (
            f"unit key mismatch color({len(color_norms)}) vs ics({len(ics_norms)}): "
            f"color-only={sorted(color_norms - ics_norms)}, ics-only={sorted(ics_norms - color_norms)}"
        )

    units: Dict[str, model.UnitRec] = {}
    for raw, cu in color_units.items():
        norm = cu["norm"]
        role = cu["layer_role"]
        ics = ics_rows.get(norm) or {}

        older = ics.get("older") if "待" not in str(ics.get("older_uri", "")) else None
        younger = ics.get("younger") if "待" not in str(ics.get("younger_uri", "")) else None
        # Qp2l/Qp2W auto-fix: MiddlePleistocene (confirmed present in ICS table)
        if older is None and norm in ("Qp2l", "Qp2W"):
            older = younger = "MiddlePleistocene"

        era_older = vocab.era(older) if older else None
        era_younger = vocab.era(younger) if younger else None

        event = model.EventRec(
            eventprocess_term=mapping.eventprocess(role),
            eventprocess_label=mapping.eventprocess(role).replace("_", " "),
            older_era=older,
            younger_era=younger,
            older_ma=era_older["older_Ma"] if era_older else None,
            younger_ma=era_younger["younger_Ma"] if era_younger else None,
        )
        if norm in _REGIONAL_AGE_UNITS:
            extras = mapping.load().get("unit_extras", {}).get(norm, {})
            pair = extras.get("numericAge")
            if pair and pair[0] > pair[1]:
                event.numeric_pair = (float(pair[0]), float(pair[1]))
            else:
                at = age_table.get(norm) or {}
                if at.get("older_Ma") and at.get("younger_Ma"):
                    event.numeric_pair = (at["older_Ma"], at["younger_Ma"])

        compositions: List[model.CompositionRec] = []
        term = _LITHOLOGY_BY_NORM.get(norm)
        if term:
            uri, label = vocab.lithology_uri(term)
            compositions.append(
                model.CompositionRec(
                    lithology_term=term, lithology_label=label, lithology_uri=uri
                )
            )

        units[norm] = model.UnitRec(
            norm=norm,
            name=cu["name"],
            layer_role=role,
            unittype_term=mapping.unit_type(role),
            rank_term=_rank_for(cu["name"], role),
            description=f"{cu['name']}（{role}，{norm}）" + (f" [{ics['note']}]" if ics.get("note") else ""),  # noqa: E501
            event=event,
            compositions=compositions,
            rgb=cu["rgb"],
        )
    if config.EXPECTED_UNITS is not None:
        assert len(units) == config.EXPECTED_UNITS, \
            f"expected {config.EXPECTED_UNITS} units, got {len(units)}"
    return units


def raw_to_norm_map() -> Dict[str, str]:
    """raw mathtext code (as in L1 QDUECC_eff / units keys) -> norm."""
    return {raw: cu["norm"] for raw, cu in sources.read_color_units().items()}
