#!/usr/bin/env python3
"""Resolve names to Avito ids/slugs/enums from the offline reference catalogs.

Usage:
  lookup.py category <query>            # "iphone" -> category id + searchSlug
  lookup.py city <query>                # "casablanca" -> city id + path slug + sectors
  lookup.py sector <city> <query>       # sector slug within a city
  lookup.py brand cars|phones <name>    # brand id + model slugs
  lookup.py filters <category>          # every valid filter param + enum values
  lookup.py filters <category> -p KEY   # full enum list for one param

Add --json for machine-readable output. All commands are offline (no network).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avito_common as ac


def err(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def fmt_count(n):
    return f" [{n}]" if n not in (None, "") else ""


def cmd_category(args):
    by_id = ac.load("category_tree.json")["byId"]
    matches = []
    if str(args.query) in by_id:
        matches = [(by_id[str(args.query)], 100)]
    else:
        scored = []
        for e in by_id.values():
            s = max(ac.score(args.query, e["name"]), ac.score(args.query, e.get("searchSlug", "")))
            if s > 0:
                scored.append((e, s))
        scored.sort(key=lambda x: (-x[1], ac.norm(x[0]["name"])))
        matches = scored[:10]
    if not matches:
        err(f"no category matches {args.query!r}. Try a broader word (e.g. 'voiture', 'telephone', 'appartement').")
    out = []
    for e, s in matches:
        resolved = ac.resolve_category(e["id"])
        out.append({"id": e["id"], "name": e["name"], "searchSlug": e.get("searchSlug", ""),
                    "adType": e.get("adType", ""), "path": resolved["path"]})
        print(f"{e['id']:>5}  {e['name']}  ({e.get('adType', '')})")
        print(f"       path: {resolved['path']}")
        print(f"       url:  /fr/maroc/{e.get('searchSlug', '')}")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_city(args):
    city = ac.resolve_city(args.query)
    if city is None:
        err(f"no city matches {args.query!r}.")
    areas = city["areas"]
    print(f"{city['id']}  {city['name']}  ({len(areas)} sectors)")
    print(f"     path slug: /fr/{ac.slugify(city['name'])}/...")
    if len(areas) > 1:
        shown = sorted(areas.items(), key=lambda kv: ac.norm(kv[1]))[:12]
        for aid, name in shown:
            print(f"     sector {aid:>5}  {name}  (/fr/{ac.slugify(city['name'])}/{ac.slugify(name)}/)")
        if len(areas) > 12:
            print(f"     … {len(areas) - 12} more sectors: lookup.py sector {ac.slugify(city['name'])} <name>")
    if args.json:
        print(json.dumps({"id": city["id"], "name": city["name"],
                          "slug": ac.slugify(city["name"]), "areas": areas},
                         ensure_ascii=False, indent=1))


def cmd_sector(args):
    city = ac.resolve_city(args.city)
    if city is None:
        err(f"no city matches {args.city!r}.")
    slug, aid = ac.resolve_sector(city, args.query)
    exact = aid is not None
    name = city["areas"].get(aid, args.query) if exact else args.query
    print(f"{slug}  ({name}, area id {aid if exact else 'not in catalog'})")
    print(f"     url: /fr/{ac.slugify(city['name'])}/{slug}/...")
    if not exact:
        print("     warning: sector not verified in catalog; slug derived from the name.", file=sys.stderr)
    if args.json:
        print(json.dumps({"city": city["name"], "sector": name, "slug": slug,
                          "area_id": aid}, ensure_ascii=False, indent=1))


def cmd_brand(args):
    catalog = "brands_cars.json" if args.catalog == "cars" else "brands_phones.json"
    brands = ac.load(catalog)["brands"]
    param = "brand" if args.catalog == "cars" else "phone_brand"
    matches = ac.best_matches(args.brand, list(brands.items()), lambda kv: kv[1]["name"], limit=5)
    if not matches:
        err(f"no {args.catalog} brand matches {args.brand!r}.")
    for (bid, b), _ in matches:
        models = b.get("models", {})
        print(f"{bid}  {b['name']}  ({len(models)} models)   -> ?{param}={bid}")
        if args.model:
            mm = ac.best_matches(args.model, list(models.items()), lambda kv: kv[1], limit=3)
            for (mslug, mname), _s in mm:
                print(f"     model: {mslug}  {mname}   -> &model={mslug}")
        else:
            for mslug, mname in list(models.items())[:8]:
                print(f"     model: {mslug}  {mname}")
            if len(models) > 8:
                print(f"     … {len(models) - 8} more: lookup.py brand {args.catalog} {ac.norm(b['name'])} <model>")
    if args.json:
        print(json.dumps([{"id": bid, "name": b["name"], "models": b.get("models", {})}
                          for bid, b in matches], ensure_ascii=False, indent=1))


def cmd_filters(args):
    cat = ac.resolve_category(args.category)
    if cat is None:
        err(f"no category matches {args.category!r}.")
    entry = ac.category_filters(cat["id"])
    if entry is None:
        err(f"no filter catalog for category {cat['id']} ({cat['name']}). "
            f"It works with universal params only: price, cities, seller_type, ad_options, o.")
    filters = entry["filters"]
    print(f"category {cat['id']}  {cat['name']}  (~{entry.get('total', '?')} ads)")
    for key, f in filters.items():
        label, ftype = f.get("label", key), f.get("type", "")
        suffix = f" {f['suffix']}" if f.get("suffix") else ""
        if args.param and ac.norm(key) != ac.norm(args.param):
            continue
        print(f"\n  {key}  ({label}, {ftype}{suffix})")
        values = f.get("values")
        if values is None:
            print("     <free value>")
            continue
        items = sorted(values.items(), key=lambda kv: -int(kv[1].get("count") or 0))
        cap = len(items) if args.param else 12
        for k, v in items[:cap]:
            count = fmt_count(v.get("count"))
            children = v.get("children")
            child_note = f" (+{len(children)} sub-values)" if children else ""
            print(f"     {k} = {v.get('label', k)}{count}{child_note}")
        if len(items) > cap:
            print(f"     … {len(items) - cap} more: lookup.py filters {cat['id']} -p {key}")
    if args.json:
        print(json.dumps({"category": cat, "filters": filters}, ensure_ascii=False, indent=1))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="also print machine-readable JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("category", parents=[common], help="find a category id/searchSlug")
    s.add_argument("query")
    s.set_defaults(fn=cmd_category)

    s = sub.add_parser("city", parents=[common], help="find a city id + path slug + sectors")
    s.add_argument("query")
    s.set_defaults(fn=cmd_city)

    s = sub.add_parser("sector", parents=[common], help="find a sector slug within a city")
    s.add_argument("city")
    s.add_argument("query")
    s.set_defaults(fn=cmd_sector)

    s = sub.add_parser("brand", parents=[common], help="find a brand id and model slugs")
    s.add_argument("catalog", choices=["cars", "phones"])
    s.add_argument("brand")
    s.add_argument("model", nargs="?", default=None)
    s.set_defaults(fn=cmd_brand)

    s = sub.add_parser("filters", parents=[common], help="list valid filter params + enums for a category")
    s.add_argument("category")
    s.add_argument("-p", "--param", default=None, help="show full enum for one param")
    s.set_defaults(fn=cmd_filters)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
