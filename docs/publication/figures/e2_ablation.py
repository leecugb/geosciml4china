# -*- coding: utf-8 -*-
"""E2 channel ablation: rerun calibration with each evidence channel disabled
(G4C_ABLATE hook), compare codebook semantics and segment-level flips against
the full-channel baseline. Shadow output dirs keep canonical artifacts intact.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

CHANNELS = ["prior", "name", "sig", "kin", "dip", "aux", "cover", "coinc",
            "nappe", "hook"]
SHEETS = ["jwsss", "jwss"]
ROOT = Path(r"D:\geosciml4china")
OUT = ROOT / "docs" / "publication" / "figures" / "e2_results"
OUT.mkdir(parents=True, exist_ok=True)

import csv


def read_map(root_dir: Path, key: str) -> dict:
    p = root_dir / f"code_semantics_map_{key}.csv"
    if not p.exists():
        return {}
    return {r["GZEEB"]: r["semantic"]
            for r in csv.DictReader(open(p, encoding="utf-8-sig"))}


def read_structural(root_dir: Path, key: str) -> dict:
    p = root_dir / f"_gzeeb_calibration_{key}.csv"
    if not p.exists():
        return {}
    return {r["idx"]: r["structural_type"]
            for r in csv.DictReader(open(p, encoding="utf-8-sig"))}


def run(sheet, ablate, shadow: Path) -> None:
    env = dict(os.environ)
    if ablate:
        env["G4C_ABLATE"] = ablate
    subprocess.run(
        [sys.executable, "-m", "geosciml4china.cli", "calibrate-gzeeb",
         "--sheet", sheet, "--out", str(shadow)],
        env=env, cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True)


results = {}
for sheet in SHEETS:
    base_dir = ROOT / ".." / sheet if sheet == "jwsss" else ROOT / ".." / sheet
    # canonical baseline lives in the sheet root
    base = Path(rf"D:\{sheet}")
    base_map = read_map(base, sheet)
    base_struct = read_structural(base, sheet)
    row = {"baseline_codes": base_map}
    for ch in CHANNELS:
        shadow = OUT / f"ablate_{sheet}_{ch}"
        shadow.mkdir(parents=True, exist_ok=True)
        try:
            run(sheet, ch, shadow)
        except subprocess.CalledProcessError as e:
            row[ch] = {"error": str(e)}
            continue
        m = read_map(shadow, sheet)
        st = read_structural(shadow, sheet)
        flipped_codes = {c for c in base_map if m.get(c) != base_map[c]}
        flipped_segs = sum(1 for i in base_struct
                           if st.get(i) != base_struct[i])
        row[ch] = {"codes_flipped": sorted(flipped_codes),
                   "code_details": {c: (base_map.get(c), m.get(c))
                                    for c in flipped_codes},
                   "segs_flipped": flipped_segs,
                   "n_segs_total": len(base_struct)}
        print(f"{sheet} -{ch}: codes {sorted(flipped_codes)} segs {flipped_segs}",
              flush=True)
    results[sheet] = row

with open(OUT / "e2_ablation_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
print("done →", OUT / "e2_ablation_results.json")
