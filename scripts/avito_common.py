"""Shared helpers for the avito-search skill scripts (stdlib only)."""
import json
import re
import unicodedata
from pathlib import Path

REFS = Path(__file__).resolve().parent.parent / "references"


def norm(s):
    """lowercase, strip accents, collapse to alpha-numeric words separated by single spaces."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", str(s).lower()))


def slugify(s):
    """Avito path slug: lowercase ascii, words joined by underscore (e.g. El Jadida -> el_jadida)."""
    return norm(s).replace(" ", "_")


def score(query, target):
    """Fuzzy match score. 100 exact, 80 prefix, 60 word-start, 40 substring, 0 no match."""
    nq, nt = norm(query), norm(target)
    if not nq or not nt:
        return 0
    if nq == nt:
        return 100
    if nt.startswith(nq):
        return 80
    if any(w.startswith(nq) for w in nt.split()):
        return 60
    if nq in nt:
        return 40
    return 0


def best_matches(query, candidates, key, limit=8):
    """candidates: list of items; key(item) -> string to match against.
    Returns list of (item, score) sorted by score desc, only score > 0."""
    scored = []
    for item in candidates:
        s = score(query, key(item))
        if s > 0:
            scored.append((item, s))
    scored.sort(key=lambda x: (-x[1], norm(key(x[0]))))
    return scored[:limit]


_cache = {}


def load(name):
    if name not in _cache:
        _cache[name] = json.loads((REFS / name).read_text(encoding="utf-8"))
    return _cache[name]


def category_by_id(cat_id):
    return load("category_tree.json")["byId"].get(str(cat_id))


def resolve_category(query):
    """Accepts a category id, exact/fuzzy name, or searchSlug.
    Returns dict(id, name, searchSlug, adType, path) or None."""
    by_id = load("category_tree.json")["byId"]
    entry = by_id.get(str(query))
    if entry is None:
        matches = best_matches(query, list(by_id.values()),
                               lambda e: f"{e['name']} {e.get('searchSlug', '')}")
        entry = matches[0][0] if matches else None
    if entry is None:
        return None
    # full display path, e.g. "Véhicules > Voitures > Voitures d'occasion"
    parts, cur = [], entry
    while cur:
        parts.append(cur["name"])
        cur = by_id.get(cur.get("parent")) if cur.get("parent") else None
    return {"id": entry["id"], "name": entry["name"],
            "searchSlug": entry.get("searchSlug", ""), "adType": entry.get("adType", ""),
            "path": " > ".join(reversed(parts))}


def resolve_city(query):
    """Accepts a city id or fuzzy name. Returns dict(id, name, areas) or None."""
    cities = load("cities.json")["cities"]
    cid, entry = str(query), cities.get(str(query))
    if entry is None:
        matches = best_matches(query, list(cities.items()), lambda kv: kv[1]["name"], limit=1)
        if not matches:
            return None
        (cid, entry), _ = matches[0]
    return {"id": str(cid), "name": entry["name"], "areas": entry.get("areas", {})}


def resolve_sector(city_entry, query):
    """Resolve a sector/area name within a resolved city. Returns (slug, area_id|None)."""
    areas = city_entry["areas"]
    for aid, name in areas.items():
        if score(query, name) >= 80:
            return slugify(name), aid
    for aid, name in areas.items():
        if score(query, name) > 0:
            return slugify(name), aid
    return slugify(query), None


def category_filters(cat_id):
    """Filter params dict for a category id (from filters_by_category.json), or None."""
    slug = (category_by_id(cat_id) or {}).get("searchSlug")
    if not slug:
        return None
    cats = load("filters_by_category.json")["categories"]
    entry = cats.get(slug)
    if entry is None:  # slug keys in the file use the same string
        for k, v in cats.items():
            if v.get("categoryId") == str(cat_id):
                entry = v
                break
    return entry
