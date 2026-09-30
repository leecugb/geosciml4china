"""Vocabulary lookup — data-driven only, no hand-built URI paths."""

from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

from . import config

_cache: Dict[str, dict] = {}


def _load(name: str, path) -> dict:
    if name not in _cache:
        with open(path, encoding="utf-8") as f:
            _cache[name] = json.load(f)
    return _cache[name]


def cgi_term(vocab: str, term: str) -> Tuple[str, str]:
    """Return (uri, label_en) for a CGI vocabulary term. Raises KeyError if
    the term is unknown — wrong terms must die at load time."""
    data = _load("cgi_terms", config.CGI_TERMS)["vocabularies"]
    if vocab not in data:
        raise KeyError(f"unknown CGI vocabulary {vocab!r}")
    for t, label in data[vocab]:
        if t == term:
            return f"{config.CGI_CLASSIFIER}/{vocab}/{term}", label
    raise KeyError(f"unknown term {term!r} in cgi/{vocab}")


def lithology_uri(term: str) -> Tuple[str, str]:
    """Return (uri, label) from simplelithology.json (keyed by term id)."""
    data = _load("lithology", config.SIMPLE_LITHOLOGY)
    if term not in data:
        raise KeyError(f"unknown lithology term {term!r}")
    entry = data[term]
    return entry["uri"], entry["label"]


def foliation_uri(term: str) -> Tuple[str, str]:
    """Return (uri, label) from foliationtype.json (keyed by term id)."""
    data = _load("foliationtype", config.FOLIATIONTYPE)
    if term not in data:
        raise KeyError(f"unknown foliation term {term!r}")
    entry = data[term]
    return entry["uri"], entry["label"]


def era(name: str) -> Optional[dict]:
    """ICS era record by CamelCase id (e.g. 'Mississippian')."""
    return _load("eras", config.ICS_ERAS).get(name)


def era_uri(name: str) -> str:
    return f"{config.CGI_ICS}/{name}"
