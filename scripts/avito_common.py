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
    """Fuzzy match score. 100 exact, 80 prefix, 60 word-start, 40 substring,
    30 all-query-words-present (order-free, word-prefix), 0 no match."""
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
    words = nt.split()
    if all(any(w.startswith(qw) for w in words) for qw in nq.split()):
        return 30
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


_flat_cache = None


def flat_categories():
    """All category entries flattened from the tree, with their parent-name paths.
    The tree is the source of truth: ids repeat across ad types (1010 = apartment
    sell/let/co_rent/vac_rent), so the file's byId map shadows all but one variant."""
    global _flat_cache
    if _flat_cache is None:
        out = []

        def walk(node, parents):
            entry = {"id": node["id"], "name": node["name"],
                     "searchSlug": node.get("searchSlug", ""),
                     "adType": node.get("adType", ""), "path": " > ".join(parents + [node["name"]])}
            out.append(entry)
            for ch in node.get("children") or []:
                walk(ch, parents + [node["name"]])

        for vert in load("category_tree.json")["tree"]:
            walk(vert, [])
        _flat_cache = out
    return _flat_cache


def category_by_id(cat_id):
    matches = [e for e in flat_categories() if e["id"] == str(cat_id)]
    return matches[0] if matches else None


ADTYPE_ORDER = {"sell": 0, "let": 1, "co_rent": 2, "vac_rent": 3, "all": 4}


def resolve_category(query):
    """Accepts a category id, exact/fuzzy name, or searchSlug.
    Returns dict(id, name, searchSlug, adType, path) or None. When several
    ad-type variants tie (e.g. plain 'appartement'), sell is preferred."""
    entries = flat_categories()
    exact_id = [e for e in entries if e["id"] == str(query)]
    if exact_id:
        exact_id.sort(key=lambda e: ADTYPE_ORDER.get(e["adType"], 9))
        return exact_id[0]
    matches = best_matches(query, entries,
                           lambda e: f"{e['name']} {e['searchSlug']}")
    if not matches:
        return None
    top = [m[0] for m in matches if m[1] == matches[0][1]]
    top.sort(key=lambda e: (ADTYPE_ORDER.get(e["adType"], 9), len(e["name"])))
    return top[0]


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


def category_filters(cat):
    """Filter params dict for a resolved category entry (joined by searchSlug —
    ids repeat across ad types, so they cannot join the two files safely), or None."""
    slug = (cat or {}).get("searchSlug")
    if not slug:
        return None
    return load("filters_by_category.json")["categories"].get(slug)
