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
Tip: quote multi-word queries — lookup.py brand phones apple "iphone 15 pro".
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


def model_params_for(catalog):
    """(brand_param, model_param, combined_param) for a brand catalog, derived from
    filters_by_category.json (the param carrying a childrenKey), with a fallback."""
    cat_id = "2010" if catalog == "cars" else "5010"
    entry = ac.category_filters(ac.resolve_category(cat_id)) or {}
    for key, f in entry.get("filters", {}).items():
        ck = f.get("childrenKey")
        if ck:
            return key, ck, f"{key}_model"
    if catalog == "cars":
        return ("brand", "model", "brand_model")
    return ("phone_brand", "phone_model", "phone_brand_model")


def match_models(query, models, limit):
    """Match a model query against both label and slug (exact slugs like
    apple_iphone_15_pro must resolve), best score first."""
    scored = []
    for mslug, mname in models.items():
        s = max(ac.score(query, mname), ac.score(query, mslug.replace("_", " ")))
        if s > 0:
            scored.append(((mslug, mname), s))
    scored.sort(key=lambda x: (-x[1], ac.norm(x[0][1])))
    return scored[:limit]


def cmd_category(args):
    entries = ac.flat_categories()
    matches = []
    if any(e["id"] == str(args.query) for e in entries):
        matches = [(e, 100) for e in entries if e["id"] == str(args.query)]
    else:
        scored = []
        for e in entries:
            s = max(ac.score(args.query, e["name"]), ac.score(args.query, e["searchSlug"]))
            if s > 0:
                scored.append((e, s))
        scored.sort(key=lambda x: (-x[1], ac.norm(x[0]["name"])))
        matches = scored[:10]
    if not matches:
        err(f"no category matches {args.query!r}. Try a broader word (e.g. 'voiture', 'telephone', 'appartement').")
    out = []
    for e, s in matches:
        out.append({"id": e["id"], "name": e["name"], "searchSlug": e["searchSlug"],
                    "adType": e["adType"], "path": e["path"]})
        print(f"{e['id']:>5}  {e['name']}  ({e['adType']})")
        print(f"       path: {e['path']}")
        print(f"       url:  /fr/maroc/{e['searchSlug']}")
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
    brand_param, model_param, combined_param = model_params_for(args.catalog)
    matches = ac.best_matches(args.brand, list(brands.items()), lambda kv: kv[1]["name"], limit=5)
    if not matches:
        err(f"no {args.catalog} brand matches {args.brand!r}. Quote multi-word queries: "
            f"lookup.py brand {args.catalog} \"<name>\".")
    for (bid, b), _ in matches:
        models = b.get("models", {})
        print(f"{bid}  {b['name']}  ({len(models)} models)")
        print(f"     use: search.py ... -f {brand_param}={bid} -f {model_param}=<slug>   (auto-combined)")
        if args.model:
            all_mm = match_models(args.model, models, limit=len(models))
            mm = all_mm if args.all else all_mm[:3]
            if not mm:
                err(f"no model of {b['name']} matches {args.model!r} "
                    f"(quote multi-word queries: \"iphone 15 pro\"; very recent models may "
                    f"be missing from the catalog — search by --keyword instead).")
            for (mslug, mname), _s in mm:
                quirk = "   [! slug contains whitespace — Avito catalog quirk]" \
                        if mslug != mslug.strip() or " " in mslug else ""
                print(f"     model: {mslug}  {mname}{quirk}")
                print(f"            -> -f {model_param}={mslug}   (combined: {combined_param}={bid}_{mslug})")
            if not args.all and len(all_mm) > 3:
                print(f"     … {len(all_mm) - 3} more matches: add --all")
        else:
            shown = models if args.all else dict(list(models.items())[:8])
            for mslug, mname in shown.items():
                quirk = "   [! slug contains whitespace — Avito catalog quirk]" \
                        if " " in mslug else ""
                print(f"     model: {mslug}  {mname}{quirk}")
            if not args.all and len(models) > 8:
                print(f"     … {len(models) - 8} more: lookup.py brand {args.catalog} "
                      f"{ac.norm(b['name'])} --all")
    if args.json:
        print(json.dumps([{"id": bid, "name": b["name"], "models": b.get("models", {})}
                          for bid, b in matches], ensure_ascii=False, indent=1))


def cmd_filters(args):
    cat = ac.resolve_category(args.category)
    if cat is None:
        err(f"no category matches {args.category!r}.")
    entry = ac.category_filters(cat)
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
            if f.get("type") == "Range":
                unit = f" in {f['suffix']}" if f.get("suffix") else ""
                k = key.lower()
                if "regdate" in k or "date" in k or "year" in k:
                    ex = "2015-2020"
                elif f.get("suffix") == "DH":
                    ex = "3000-8000"
                elif f.get("suffix") == "km":
                    ex = "0-200000"
                elif f.get("suffix") in ("m²", "m2"):
                    ex = "60-120"
                else:
                    ex = "MIN-MAX"
                print(f"     format: MIN-MAX{unit}   (e.g. {key}={ex})")
            else:
                print("     <free value>")
            continue
        items = sorted(values.items(), key=lambda kv: -int(kv[1].get("count") or 0))
        cap = len(items) if (args.param or args.expand) else 12
        for k, v in items[:cap]:
            count = fmt_count(v.get("count"))
            children = v.get("children")
            child_note = f" (+{len(children)} sub-values: --expand)" if children else ""
            print(f"     {k} = {v.get('label', k)}{count}{child_note}")
            if args.expand and children:
                for cslug, clabel in children.items():
                    quirk = "  [! whitespace in slug]" if " " in cslug else ""
                    print(f"        - {cslug} = {clabel}{quirk}")
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
    s.add_argument("-a", "--all", action="store_true", help="list all models (no truncation)")
    s.set_defaults(fn=cmd_brand)

    s = sub.add_parser("filters", parents=[common], help="list valid filter params + enums for a category")
    s.add_argument("category")
    s.add_argument("-p", "--param", default=None, help="show full enum for one param")
    s.add_argument("--expand", action="store_true",
                   help="also print sub-values (model slugs) of every enum value")
    s.set_defaults(fn=cmd_filters)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
