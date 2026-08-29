---
name: avito-search
description: Search any category of listings (cars, phones, real estate, home, jobs, services…) on Avito.ma, Morocco's largest classifieds site. Use when the user wants to find, filter, price-check, or compare used/new items, vehicles, or property for sale or rent in Morocco. Resolves categories/cities/brands offline, builds exact search URLs, fetches past Cloudflare via the Jina reader proxy, and returns structured listing data.
---

# Avito.ma search

Morocco's largest classifieds site (~1M live ads). The site is behind Cloudflare; everything is
fetched through the **r.jina.ai** reader proxy. Search pages embed a `__NEXT_DATA__` JSON blob
with the complete structured response — never parse HTML/markdown.

All mechanical work is done by two scripts in this skill's `scripts/` directory (run them with
their full path, from any working directory). `lookup.py` is offline; only `search.py` hits the
network.

## 1. Resolve names → ids (offline)

```bash
scripts/lookup.py category telephone       # fuzzy: id, searchSlug, adType, url path
scripts/lookup.py city casablanca          # id, path slug, sector list
scripts/lookup.py sector casablanca maarif # sector slug for the URL path
scripts/lookup.py brand cars volkswagen golf   # brand id + model slug (or: phones)
scripts/lookup.py filters 2010             # valid filter params + enum values for a category
scripts/lookup.py filters 2010 -p fuel     # full enum list for one param
```

Every command accepts ids, names (French or English, accents optional), or slugs, and supports
`--json`. Do **not** read the reference JSONs directly — they are large; `lookup.py` is the
indexed interface to them.

## 2. Search

```bash
# typical product search
scripts/search.py --category telephones --keyword iphone --price 3000-8000 --city casablanca --top 10

# cars with category-specific filters (discover keys via: lookup.py filters 2010)
scripts/search.py --category voitures --city rabat -f brand=58 -f model=golf7 --pages 2

# keyword across multiple cities, seller type, structured output
scripts/search.py --keyword "studio meuble" --city casablanca,rabat --seller-type pro --json --facets
```

- `--keyword` is free text; `--category` accepts id/name/slug; both combine (`keyword` in path +
  `?category=`).
- `--price MIN-MAX` in DH, open forms `-5000` / `2000-`. `--sector` narrows within a single city.
- `-f KEY=VALUE` (repeatable) carries any category-specific filter: `brand`, `model`, `fuel`,
  `regdate=2015-2020`, `mileage_exact=0-100000`, `rooms`, `condition`, `storage_capacity`…
- Defaults: `ad_options=has_price` (drop with `--include-unpriced`), 1 page (35 ads/page),
  top 20 shown. `--pages N` paginates (3s pause between pages), `--json` emits full fields
  (params, seller+phone, flags, loan estimate), `--facets` adds live counts per filter — use them
  to suggest refinements.
- `--dry-run` prints the URL without fetching. On failure the script retries once after 30s; if
  r.jina.ai is rate-limiting (free tier ≈20 req/min), wait 60+s and rerun.

The first output line shows the exact query URL and total matching ads — cite both to the user.

## Presenting results (quality checks)

- **Outlier/scam prices**: flag or drop prices far outside the plausible band (observed in the
  wild: 810k–1.35M DH on ~2010 economy cars). Thresholds are context-dependent.
- **Fake mileage**: `0 km`/`200 km` on a 10+ year-old car is fake — exclude. `0 km` on a
  current-year car may be a legit showroom vehicle.
- **Duplicates**: same item reposted — dedupe by title + key attributes + city.
- Prices are in Moroccan dirham (DH/MAD). `DH/mois` values are Avito's loan estimates, not rents
  (except in actual rental categories). Show "prix non spécifié" ads only if requested.

## Notes

- UI and enum labels are French; ads are often Arabic. `/fr/` search matches Arabic ad text.
  City names use French spellings (`sale` = Salé, `fes` = Fès). All slugs: lowercase, accents
  stripped, underscores (`el_jadida`, `ain_chock`).
- There is **no sort param** — results come in a relevance/date mix.
- Reference catalogs (`references/`, point-in-time 2026-08-29): `category_tree.json` (138
  categories), `cities.json` (500 cities + 1,527 sectors), `filters_by_category.json` (105
  categories), `brands_cars.json` / `brands_phones.json`. `url_params.md` documents verified
  param semantics and pitfalls in depth.
- Refreshing catalogs (manual, only when stale): the config endpoints
  `https://r.jina.ai/https://services.avito.ma/api/v2/config/listing/tree`,
  `.../config/listing/filters?category_id=<id>&type=sell&lang=fr`, and
  `.../api/v1/admng/config/cities` return the site's own source of truth via plain r.jina.ai
  (JSON follows a `Markdown Content:` line).
- Manual fetch fallback if the scripts are broken: `curl -s -H "x-respond-with: html" --max-time 60
  "https://r.jina.ai/<search-url>"`, then extract the `<script id="__NEXT_DATA__" ...>` JSON blob
  and read `props.pageProps.componentProps` → `ads.totalListingAds`, `ads.ads[]`,
  `facetedSearchResponse.filters`.
