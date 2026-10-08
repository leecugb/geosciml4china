# -*- coding: utf-8 -*-
"""E4 entity-cluster weighting + E6 confidence calibration — post-hoc
computations from existing artifacts (no replays)."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(r"D:\geosciml4china\docs\publication\figures\e2_results")
res = {}

for sheet in ("jwsss", "jwss"):
    root = Path(rf"D:\{sheet}")
    cal = list(csv.DictReader(open(root / f"_gzeeb_calibration_{sheet}.csv",
                                   encoding="utf-8-sig")))
    # ---- E4: entity-cluster weighting ----
    # L2 distribution with segment votes vs entity-weighted votes (1/m_f)
    seg_dist = defaultdict(lambda: defaultdict(int))
    ent_dist = defaultdict(lambda: defaultdict(float))
    m_f = Counter(r["fault_id"] for r in cal if r["fault_id"])
    for r in cal:
        c = r["GZEEB"]
        st = r["own_structural_type"]  # own = segment-level (pre-inheritance)
        seg_dist[c][st] += 1
        ent_dist[c][st] += 1.0 / m_f[r["fault_id"]]
    def dom(dist):
        out = {}
        for c, dd in dist.items():
            tot = sum(dd.values())
            spec = {k: v for k, v in dd.items()
                    if k not in ("断层泛称", "推测断层")}
            if spec and max(spec.values()) / tot >= 0.25:
                out[c] = max(spec.items(), key=lambda kv: kv[1])[0]
            else:
                out[c] = "断层泛称"
        return out
    d_seg, d_ent = dom(seg_dist), dom(ent_dist)
    flips = {c: (d_seg[c], d_ent[c]) for c in d_seg if d_seg[c] != d_ent[c]}
    res.setdefault(sheet, {})["e4_entity_weight"] = {
        "segment_based": d_seg, "entity_weighted": d_ent,
        "codes_flipped": flips}

    # ---- E6: confidence calibration ----
    # verdict/confidence vs adjudication status
    band = Counter(r["verdict"] for r in cal)
    conf_u = [r.get("confidence_u") for r in cal if r.get("confidence_u")]
    try:
        conf_vals = [float(x) for x in conf_u if x not in ("", None, "nan")]
    except (TypeError, ValueError):
        conf_vals = []
    adjudicated = [r for r in cal
                   if str(r["verdict"]).startswith("裁定") or "裁定" in str(r["verdict"])]
    res.setdefault(sheet, {})["e6_confidence"] = {
        "verdict_distribution": dict(band),
        "adjudicated_rows": len(adjudicated),
        "adjudicated_confidence": [r.get("confidence_u") for r in adjudicated],
        "n_confidence_values": len(conf_vals),
        "confidence_min_max": (min(conf_vals), max(conf_vals)) if conf_vals else None,
    }
    print(sheet, "E4 flips:", flips, "| E6 verdicts:", dict(band), flush=True)

with open(OUT / "e4_e6_results.json", "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print("done →", OUT / "e4_e6_results.json")
