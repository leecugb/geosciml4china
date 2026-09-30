"""Load geosciml_vocab_mapping.json and validate all decided terms at load time."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from . import config, vocab

_cache: Optional[dict] = None


def load() -> dict:
    global _cache
    if _cache is None:
        with open(config.VOCAB_MAPPING, encoding="utf-8") as f:
            _cache = json.load(f)
        _validate(_cache)
    return _cache


def _validate(m: dict) -> None:
    """Every decided vocabulary term must exist in its vocabulary — die here,
    not at XSD time."""
    for code, row in m["gzbd_contacttype"].items():
        if row.get("status") == "decided" and row.get("term"):
            vocab.cgi_term("contacttype", row["term"])
        if row.get("obs"):
            vocab.cgi_term("featureobservationmethod", row["obs"])
    for code, row in m["gzeeb_faulttype"].items():
        if row.get("status") == "decided" and row.get("term"):
            vocab.cgi_term("faulttype", row["term"])
    for label, term in m["evidence_observation"].items():
        vocab.cgi_term("featureobservationmethod", term)
    for code, row in m["gzbbga_foliation"].items():
        if row.get("status") == "decided" and row.get("term"):
            vocab.foliation_uri(row["term"])
    for term in m["eventprocess"].values():
        vocab.cgi_term("eventprocess", term)
    for term in m["unit_type"].values():
        vocab.cgi_term("geologicunittype", term)


def gzbd_row(code: str) -> Dict[str, Any]:
    return load()["gzbd_contacttype"].get(code, {"term": None, "status": "pending"})


def gzeeb_row(code: str) -> Dict[str, Any]:
    return load()["gzeeb_faulttype"].get(code, {"term": "fault", "status": "decided"})


def evidence_observation(evidence_class: str) -> Optional[str]:
    return load()["evidence_observation"].get(evidence_class)


def foliation_row(key: str) -> Dict[str, Any]:
    return load()["gzbbga_foliation"].get(key, {"term": None, "status": "pending"})


def fold_profile(code: str) -> Optional[str]:
    row = load()["gzce_foldprofile"].get(code)
    if row and row.get("term"):
        return load()["gzce_foldprofile"]["_uri_base"] + row["term"]
    return None


def eventprocess(layer_role: str) -> str:
    return load()["eventprocess"].get(layer_role, "deposition")


def unit_type(layer_role: str) -> str:
    return load()["unit_type"].get(layer_role, "lithostratigraphic_unit")


def pending() -> list:
    return load()["pending"]
