# jws L0 GeoJSON — Kurgan sheet (J43C001002) full-pipeline test case

This directory holds the **L0-level GeoJSON** of the *jws* test sheet — a
working copy of the Kurgan sheet (J43C001002) used for full-pipeline testing —
i.e. the conversion products of the **11-file completeness contract**
(preflight CORE + CONDITIONAL) that the geosciml4china parsing chain consumes.

## Position in the pipeline

```
MapGIS 6.x vectors (.WL/.WT/.WP)
  → convert (MapGIS → L0 GeoJSON, EPSG:4326)
  → self-supporting geological-semantics calibration (six domains)
  → L1 semantic GeoJSON
  → GeoSciML (GML + Lite views)
  → semantic rendering
```

This directory is the output of the first step above (L0).

## File catalogue (11-file contract)

| File | Feature class | Contract |
|---|---|---|
| `LDLYAAE001.WL.geojson` | Water system (lines) | CONDITIONAL 1143 |
| `LDLYAAE002.WP.geojson` | Water system (polygons) | CONDITIONAL 128 |
| `LDZOFBA002.WL.geojson` | Geological boundaries | CORE 2222 |
| `LDZOFBA003.WL.geojson` | Fault lines | CORE 310 |
| `LDZOFBA005.WL.geojson` | Fold lines | CONDITIONAL 4 |
| `LDZOFBA016.WT.geojson` | Attitude symbols | CORE 305 |
| `LDZOFBB001.WP.geojson` | Strata (sedimentary) | CORE 608 |
| `LDZOFBB002.WP.geojson` | Volcanic rocks | CONDITIONAL 10 |
| `LDZOFBB003.WP.geojson` | Intrusive rocks | CONDITIONAL 46 |
| `LDZOFBB004.WP.geojson` | Metamorphic rocks | CONDITIONAL 49 |
| `LDZOFBB099.WT.geojson` | Annotations (incl. fault aux points) | CORE 2024 |

## Notes

- Coordinate system: **EPSG:4326** (WGS84 geographic);
- Source: a working copy of the Kurgan sheet (J43C001002) 1:250 000
  construction-geology MapGIS project, published by the data owner for
  reproducible full-pipeline testing;
- Generation tooling: `pymapgis` Reader, driven by the geosciml4china
  `preflight → convert` chain;
- The L1 semantic layer and GeoSciML products are **not** in this directory
  (parsing outputs live in the respective sheet project root).

## Reproducing the pipeline

See the repository [README](../../README.md#test-case-jws-kurgan-sheet-j43c001002-published-l0-dataset)
for sheet registration (TOML) and the `g4c check` / `g4c pipeline` commands.
