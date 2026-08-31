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
scripts/lookup.py brand cars volkswagen golf   # brand id + model slug (or: phones; --all = full list)
scripts/lookup.py filters 2010             # valid filter params + enum values for a category
scripts/lookup.py filters 5010 -p phone_brand --expand   # incl. model slugs (sub-values)
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

# phones: brand+model (auto-combined server-side into phone_brand_model), then trim by title
scripts/search.py --category telephones -f phone_brand=2 -f phone_model=apple_iphone_15_pro --title-exclude max

# keyword across multiple cities, seller type, structured output
scripts/search.py --keyword "studio meuble" --city casablanca,rabat --seller-type pro --json --facets
```

- `--keyword` is free text; `--category` accepts id/name/slug; both combine (`keyword` in path +
  `?category=`).
- `--price MIN-MAX` in DH, open forms `-5000` / `2000-`. `--sector` narrows within a single city.
- `-f KEY=VALUE` (repeatable) carries any category-specific filter — names differ per category
  (`brand`/`model` for cars, `phone_brand`/`phone_model` for phones, `fuel`, `regdate=2015-2020`,
  `mileage_exact=0-200000`, `rooms`, `storage_capacity`…; check `lookup.py filters <category>`
  — range params expect `MIN-MAX`). **Brand+model passed via
  `-f` is auto-combined** into `brand_model`/`phone_brand_model=<id>_<slug>` — Avito ignores the
  separate model param for some categories (phones: verified 2026-08-30).
- `--title-include REGEX` / `--title-exclude REGEX` (repeatable, case-insensitive) filter ad
  subjects **client-side** after fetching — increase `--pages` to compensate. This is the
  workhorse for model disambiguation (`--title-exclude max` → 15 Pro, not Pro Max) and for
  signals that only live in titles, like iPhone battery health (`--title-include 'batterie|🔋'`).
- Defaults: `ad_options=has_price` (drop with `--include-unpriced`), 1 page (35–47 ads/page by category),
  top 20 shown. `--pages N` paginates (3s pause between pages), `--json` emits full fields
  (params, seller+phone, flags, loan estimate), `--facets` adds live counts per filter — use them
  to suggest refinements.
- `--dry-run` prints the URL without fetching. On failure the script retries once after 30s; if
  r.jina.ai is rate-limiting (free tier ≈20 req/min), wait 60+s and rerun.
- **Heed stderr warnings**: the script validates requested filters against the fetched ads and
  warns `filter X may be IGNORED by Avito` when results don't match the request — treat that as
  a signal to refine or drop the filter, not as noise.

The first output line shows the exact query URL and total matching ads — cite both to the user.

## Presenting results (quality checks)

- **Always include the ad link**: every listing you mention — in chat, a table, or a report —
  must carry its URL (the `url`/`href` field). An ad name alone is not actionable: without the
  link the user cannot open it.
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
  categories), `filters_vertical_union.json` (per-vertical common-filter view),
  `brands_cars.json` / `brands_phones.json`. `url_params.md` documents verified
  param semantics and pitfalls in depth, including catalog quirks (whitespace model slugs —
  valid, send URL-encoded; minor count drift between brand sources).
- Refreshing catalogs (manual, only when stale): the config endpoints
  `https://r.jina.ai/https://services.avito.ma/api/v2/config/listing/tree`,
  `.../config/listing/filters?category_id=<id>&type=sell&lang=fr`, and
  `.../api/v1/admng/config/cities` return the site's own source of truth via plain r.jina.ai
  (JSON follows a `Markdown Content:` line).
- Manual fetch fallback if the scripts are broken: `curl -s -H "x-respond-with: html" --max-time 60
  "https://r.jina.ai/<search-url>"`, then extract the `<script id="__NEXT_DATA__" ...>` JSON blob
  and read `props.pageProps.componentProps` → `ads.totalListingAds`, `ads.ads[]`,
  `facetedSearchResponse.filters`.
