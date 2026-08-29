# avito-search

**Search [Avito.ma](https://www.avito.ma) — Morocco's largest classifieds site — from your AI agent or terminal.**

Avito carries ~1M live ads across cars, phones, real estate, jobs, and services, but it sits behind
Cloudflare and its search URLs are full of non-obvious rules: `?keyword=` is silently ignored, a
single-value `?cities=` is dropped, `?areas=` does nothing, and there is no sort parameter at all.
This project packages everything needed to search it reliably:

- **Offline catalogs** — 138 categories, 500 cities with 1,527 sectors, per-category filter
  enums, and car/phone brand–model lists — resolved by fuzzy name (`"el jadida"`, `"voitures"`,
  `"iphone"`, accents optional).
- **A search command** that builds a correct URL, fetches through the free
  [r.jina.ai](https://r.jina.ai) reader proxy (no API key, no account), and returns structured
  results extracted from the page's embedded `__NEXT_DATA__` JSON — never HTML scraping.
- **Empirically verified URL grammar** — every supported parameter was tested against the live
  site; the known-broken ones are excluded by construction.

```console
$ scripts/search.py --category telephones --keyword iphone --price 3000-8000 --city casablanca --top 3

Query: https://www.avito.ma/fr/casablanca/iphone?category=5010&price=3000-8000&ad_options=has_price
Total matching ads: 1,702 | fetched 1 page(s), 35 ads | showing 3

  1. iPhone 13 Pro — 4 000 DH — Casablanca — il y a 28 minutes — part.
     https://www.avito.ma/fr/sidi_moumen/smartphone_et_téléphone/iPhone_13_Pro_58555497.htm
  2. iPhone 14 en très bon état & câble original OFFERT — 4 500 DH (was 6 800) — il y a 4 heures — PRO [HOTDEAL] [DELIVERY]
     https://www.avito.ma/fr/aïn_chock/smartphone_et_téléphone/iPhone_14_en_très_bon_état_56603944.htm
  3. iPhone 17 normal presque neuf — 7 800 DH — Casablanca — il y a 6 heures — part.
     https://www.avito.ma/fr/maarif/smartphone_et_téléphone/iPhone_17_normal_presque_neuf_58552989.htm
```

## Requirements

- Python 3.8+ (standard library only — nothing to `pip install`)
- `curl`
- Internet access to `r.jina.ai` (free tier is rate-limited to ~20 requests/min)

## Install

### As an agent skill (ZCode)

```bash
git clone https://github.com/<you>/avito-search.git
ln -s "$(pwd)/avito-search" ~/.zcode/skills/avito-search
```

The symlink keeps the skill in sync with `git pull`. Alternatively, drop the folder into a
project at `.zcode/skills/avito-search` for workspace-only availability.

Once installed, just ask naturally — the skill triggers on requests like *"find a used Golf 7 in
Rabat under 150k"*, *"what do iPhone 15s go for in Casablanca?"*, or *"2-bedroom apartments for
rent in Agadir"*. The agent resolves categories, cities, and filters on its own.

The SKILL.md format is plain Markdown with frontmatter, so the folder also drops into other
agent CLIs that scan a skills directory. And since the scripts are self-contained, you can wire
them into any agent (or cron job, or notebook) yourself — see below.

### Standalone (any shell)

```bash
git clone https://github.com/<you>/avito-search.git
cd avito-search
python3 scripts/lookup.py city casablanca
```

## Usage

Two scripts do all the work. `lookup.py` is fully offline; only `search.py` hits the network.

### `lookup.py` — resolve names to ids, slugs, and enums

| Command | What it does |
|---|---|
| `lookup.py category <query>` | fuzzy-find a category: id, searchSlug, ad type, URL path |
| `lookup.py city <query>` | city id, path slug, and its sector list |
| `lookup.py sector <city> <query>` | sector slug for the URL path |
| `lookup.py brand cars\|phones <name> [model]` | brand id + model slugs |
| `lookup.py filters <category> [-p KEY]` | every valid filter param and enum value for a category |

```console
$ scripts/lookup.py brand cars volkswagen golf
58  Volkswagen  (47 models)   -> ?brand=58
     model: golf   Golf 1     -> &model=golf
     model: golf2  Golf 2     -> &model=golf2
     ...

$ scripts/lookup.py filters 5010 -p condition
category 5010  Smartphone et Téléphone  (~29637 ads)

  condition  (État du téléphone, List)
     2 = Bon état [15049]
     0 = Neuf [7961]
     1 = Reconditionné [1321]
     3 = Pour pièces [242]
```

Every subcommand accepts ids, French or English names, or slugs (accents optional), and supports
`--json`. Don't read the reference JSONs directly — `lookup.py` is the indexed interface to them.

### `search.py` — search and get structured results

| Flag | Meaning |
|---|---|
| `--keyword TEXT` | free-text term (goes in the URL path, where Avito requires it) |
| `--category CAT` | category id, name, or slug; combines with `--keyword` |
| `--city C` | city name or id; repeat or comma-separate for multiple |
| `--sector S` | sector/arrondissement within a single city |
| `--price MIN-MAX` | in DH; open forms `-5000` and `2000-` work |
| `--seller-type` | `particulier` or `pro` |
| `--ad-options` | csv of `has_price,has_image,hotdeal,urgent` (default `has_price`) |
| `--include-unpriced` | don't force `ad_options=has_price` |
| `-f KEY=VALUE` | any category-specific filter, repeatable (see `lookup.py filters`) |
| `--pages N` | pages to fetch, 35 ads each, 3s pause between (rate-limit friendly) |
| `--top N` | ads to show in text output (default 20) |
| `--json` | full structured output: params, seller + phone, flags, loan estimate |
| `--facets` | add live per-filter counts — great for suggesting refinements |
| `--dry-run` | print the URL that would be fetched, without fetching |

```bash
# used cars in Rabat: specific model, several pages
scripts/search.py --category voitures --city rabat -f brand=58 -f model=golf7 --pages 2

# keyword across multiple cities, professionals only, structured output
scripts/search.py --keyword "studio meuble" --city casablanca,rabat --seller-type pro --json --facets

# cheap cars, any brand, bounded year and mileage via category filters
scripts/search.py --category 2010 --price -80000 -f regdate=2015-2020 -f mileage_exact=0-150000
```

In `--json` mode each ad carries: id, subject, price (+ old price and Avito's monthly loan
estimate), location, city/area ids, relative date, category attributes (mileage, storage,
rooms…), seller name/type/phone, image count, flags, and the ad URL.

On failure the script detects proxy/Cloudflare challenge pages, retries once after 30s, and
exits with a clear explanation. If r.jina.ai is rate-limiting you, wait 60+s and rerun.

## How it works

```
 you / agent
    │
    │  scripts/lookup.py        offline: names → ids/slugs from references/*.json
    │  scripts/search.py        builds URL, fetches, parses, formats
    ▼
 r.jina.ai reader proxy   ───►   avito.ma search page (HTML, Cloudflare bypassed)
    │
    ▼  extract <script id="__NEXT_DATA__" type="application/json">
 clean JSON:  total ads · ads[] · facet counts
```

Avito is a Next.js site: every search page embeds the complete structured search response in a
`__NEXT_DATA__` JSON blob. Fetching the page through r.jina.ai with the `x-respond-with: html`
header passes Cloudflare without credentials, and the scripts extract and flatten that blob —
no HTML parsing, no fragile CSS selectors.

The URL grammar is encoded in `search.py` once, including all the verified pitfalls, so callers
can't hit them. The rules it enforces:

- keyword goes in the **path** (`/fr/maroc/iphone`); `?keyword=` is ignored by the site
- a single city goes in the **path** (`/fr/casablanca/…`); multiple cities use `?cities=5,12`;
  sectors are path slugs (`/fr/casablanca/maarif/…`) — `?areas=` does nothing
- ranges are `min-max`, open-ended allowed (`-5000`, `2000-`); multi-values are comma-separated
- `ad_options` covers `has_price`/`has_image`/`hotdeal`/`urgent` (the `has_price=true`-style
  params are silently ignored); slugs are lowercase, accents stripped, underscore-joined
  (`el_jadida`, `ain_chock`)
- there is **no sort parameter** — results come in a relevance/date mix

`references/url_params.md` documents all of this in depth, including the full broken-parameter
list.

## Limitations

- **Rate limits**: r.jina.ai's free tier allows ~20 requests/min. The script sleeps 3s between
  pages and retries once on failure; for big crawls, pace yourself or use a paid Jina key.
- **Search only** (by design): listing search and facet counts. No ad-detail pages, no posting,
  no messaging, no account features.
- **Catalog freshness**: reference counts were captured 2026-08-29. Enum keys are stable; counts
  drift. Refresh instructions below.
- **Language**: UI and enum labels are French, ad text is often Arabic; keyword search matches
  both. City names use French spellings (`sale` = Salé, `fes` = Fès). Prices are in Moroccan
  dirham (DH/MAD).

## Refreshing the catalogs

The catalogs came from Avito's own config API, reachable through the same proxy (JSON follows a
`Markdown Content:` line in the response):

```
https://r.jina.ai/https://services.avito.ma/api/v2/config/listing/tree
https://r.jina.ai/https://services.avito.ma/api/v2/config/listing/filters?category_id=<id>&type=sell&lang=fr
https://r.jina.ai/https://services.avito.ma/api/v1/admng/config/cities
```

One request each. Note the insert-flow configs' `isParam` flags describe the ad-posting flow —
search-side params are what this project documents (see `references/url_params.md`).

## Repository layout

```
SKILL.md                     skill entry point shown to agents (routing + quality checks)
README.md                    this file
scripts/
  lookup.py                  offline name → id/slug/enum resolution
  search.py                  URL builder + fetcher + parser + formatter
  avito_common.py            shared fuzzy matching and catalog loading
references/
  category_tree.json         138 categories: id, name, adType, searchSlug
  cities.json                500 cities + 1,527 sector areas
  filters_by_category.json   per-category filter enums (105 categories)
  brands_cars.json           142 car brands / 1,242 models
  brands_phones.json         phone brands / models
  url_params.md              verified param semantics + pitfalls (deep dive)
```

## Disclaimer

This project is not affiliated with Avito.ma. It reads publicly listed search results through a
reader proxy and is intended for personal, non-abusive use in accordance with the site's terms
of service. Be kind to the infrastructure: the default pacing exists for a reason.
