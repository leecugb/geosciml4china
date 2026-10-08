# -*- coding: utf-8 -*-
"""E3 hyperparameter sensitivity: ±25% perturbations of the dominance
threshold, reactivation ratio, reactivation counts, and minimum-vote floor.
Deterministic shadow replays; canonical artifacts untouched.
"""
import csv
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\geosciml4china")
OUT = ROOT / "docs" / "publication" / "figures" / "e2_results"  # shared results dir
SHEETS = ["jwsss", "jwss"]

PERTURB = [
    ("th_dom", "G4C_TH_DOM", ["0.1875", "0.3125"]),
    ("react_ratio", "G4C_TH_REACT", ["0.375", "0.625"]),
    ("react_n", "G4C_TH_REACT_N", ["2", "4"]),
    ("min_votes", "G4C_TH_MINV", ["1.5", "2.5"]),
]


def read_map(root_dir: Path, key: str) -> dict:
    p = root_dir / f"code_semantics_map_{key}.csv"
    if not p.exists():
        return {}
    return {r["GZEEB"]: r["semantic"]
            for r in csv.DictReader(open(p, encoding="utf-8-sig"))}


results = {}
for sheet in SHEETS:
    base = read_map(Path(rf"D:\{sheet}"), sheet)
    row = {}
    for tag, var, vals in PERTURB:
        for v in vals:
            shadow = OUT / f"sens_{sheet}_{tag}_{v.replace('.', 'p')}"
            shadow.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ)
            env[var] = v
            try:
                subprocess.run(
                    [sys.executable, "-m", "geosciml4china.cli",
                     "calibrate-gzeeb", "--sheet", sheet, "--out", str(shadow)],
                    env=env, cwd=str(ROOT),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=True)
            except subprocess.CalledProcessError as e:
                row[f"{tag}={v}"] = {"error": str(e)}
                continue
            m = read_map(shadow, sheet)
            flips = {c: (base.get(c), m.get(c)) for c in set(base) | set(m)
                     if base.get(c) != m.get(c)}
            row[f"{tag}={v}"] = {"codes_flipped": sorted(flips),
                                 "details": flips}
            print(f"{sheet} {tag}={v}: {sorted(flips)}", flush=True)
    results[sheet] = row

import json
with open(OUT / "e3_sensitivity_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
print("done →", OUT / "e3_sensitivity_results.json")
