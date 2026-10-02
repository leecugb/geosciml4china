# jws L1 GeoJSON — semantic calibration layer (Kurgan sheet J43C001002 copy)

This directory holds the **L1 semantic layer** of the *jws* test sheet — the
output of the self-supporting geological-semantics calibration, the input to
the GeoSciML conversion.

## Position in the pipeline

```
MapGIS vectors → L0 GeoJSON (data/jws_l0_geojson)
  → six calibration domains (gzbd / entities / auxchain / gzeeb /
    attitudes / fossils / inferred_faults)
  → L1 semantic GeoJSON (this directory)
  → GeoSciML GML + Lite views (data/jws_geosciml)
```

## Contents

| File | Feature class | Count |
|---|---|---|
| `polygons.geojson` | Geologic units (4 WP layers merged, semantics + colors) | 713 |
| `boundaries.geojson` | Geological boundaries (GZBD calibrated, sem_label, younger_side) | 2222 |
| `faults.geojson` | Fault segments (gzeeb semantics, activity, verdict, checks) | 310 |
| `fault_aux.geojson` | Fault attitude measurement points (b-family entities only) | 93 |
| `attitude.geojson` | Foliations (sem_type, host unit) | 305 |
| `fold.geojson` | Folds | 4 |
| `fossil.geojson` / `mudvolcano.geojson` | Specimens (host unit, sem_type) | 27 / 21 |
| `waterline.geojson` / `waterpoly.geojson` | Water system | 1143 / 128 |

- Coordinate system: **EPSG:4326**;
- All layers carry `semantics_version` and per-row confidence columns
  (S×I×F shadow framework);
- The L1 layer preserves `_src_id`/`aux_idx` for provenance — the GeoSciML
  product itself uses semantic identifiers only (see the package README).
