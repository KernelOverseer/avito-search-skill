# Verified URL parameters (empirically tested 2026-08-29)

## URL grammar

```
https://www.avito.ma/fr/{city_slug}/{sector_slug?}/{keyword_or_category_slug}?{filters}&o={page}
```

- Last path segment (`slug3`): EITHER a free-text keyword (`iphone`) OR a category slug
  (`téléphones-à_vendre`). Keyword cannot be a query param — `?keyword=` is echoed but IGNORED.
- City: single city goes in the PATH (`/fr/casablanca/...`). `?cities=5` with ONE id is silently
  dropped. Multiple cities: `?cities=5,8` (comma-separated; repeated params `cities=5&cities=8` → /_error).
- Sector: second path segment (`/fr/casablanca/maarif/...`). `?areas=245` does NOT work.
- Pagination: `?o=2` (35 ads/page).
- Category + keyword combine via param: `/fr/maroc/iphone?category=5010` ✓.
  Stacking keyword after a category slug in the path does NOT work.

## Universal filters (all categories)

| Param | Format | Values |
|---|---|---|
| `price` | `min-max` (open-ended ok: `-100000`, `200000-`) | DH |
| `cities` | comma ids | see cities.json |
| `seller_type` | enum | `0` Particuliers, `1` Professionnels |
| `ad_options` | enum | `has_price`, `has_image`, `hotdeal`, `urgent` |
| `category` | id | see category_tree.json |
| `o` | int | page number |

## Category-specific (see filters_by_category.json)

Cars: `brand`, `model`, `brand_model` (=id_slug, optional), `fuel`, `bv`, `regdate` (min-max),
`mileage_exact`, `pfiscale`, `auto_condition`, `v_origin`, `doors`, `first_owner`.
Phones: `phone_brand`, `phone_brand_model` (=id_slug), `condition`, `storage_capacity`.
Verified 2026-08-30 (all totals with ad_options=has_price): separate `phone_model=<slug>` and
`model=<slug>` are IGNORED for phones — `phone_brand=2` alone returns 8,790 ads, adding
`storage_capacity=256` narrows to 2,860 (filter works), and neither separate model param
changes results — while `phone_brand_model=2_apple_iphone_15_pro` filters correctly (295 ads,
all 15 Pro). Keyword path (`/fr/maroc/iphone_15_pro`) also narrows but substring-matches Pro
Max variants too.
Property: `rooms`, `bathrooms`, `spare_rooms`, `size` (min-max m²), `floor`, `floors`,
`apartment_type`, `property_standing`, `property_condition`, `property_age`,
`property_availability`, `deposit`, `office_units`, `zoning`, `capacity_rooms`,
`capacity_person`, `mezzanine_size`.
Motos: `cylinder_size` (min-max), `moto_seat_height`, `wheels`.
Animals (ferme): `animal_farm_type`, `animal_farm_breed`.
Misc: `misc_condition` (État), `extra_details` (per-category feature keys), `vehicle_condition`.

## Params that DO NOT work (common misconceptions)

- `keyword=...` → ignored; put keyword in path
- `has_price=true`, `is_urgent=true`, `is_hotDeal=true` → ignored; use `ad_options=...`
- `extra=car_ac` → ignored; use `extra_details=car_ac`
- `areas=245` → ignored; put sector slug in path
- `cities=5` (single) → dropped; put city slug in path
- `phone_model=<slug>` / `model=<slug>` in the phones category → silently ignored
  (verified 2026-08-30); use the combined `phone_brand_model=<id>_<slug>`. Note: the separate
  `brand`+`model` pair DOES work for cars — the combined form is the only universally safe one.
- sort param → none exists on web UI (relevance/date mix; `sortingMethod: SCORE` server-side)

## Multi-value encoding

Comma-separated: `cities=5,8`, `brand=49,13`, `extra_details=car_ac,car_airbags`.
Ranges: `min-max` (`price=3000-8000`, `regdate=2015-2020`, `mileage_exact=0-100000`).

## Catalog quirks (observed 2026-08-30)

- **Whitespace in model slugs**: ~85 model slugs contain spaces (mostly cars: Audi `rs 3` /
  `RS Q3`, Toyota `Corolla X SUV`, Mercedes `amg gts`; phones: Samsung `samsung_galaxy_ s25`),
  straight from Avito's own facet data, plus trailing-space (`ssk `, `ds4 `) and `mg3 +`
  variants. They are VALID: URL-encode the value as-is (`model=rs%203` — verified live:
  `brand_model=3_rs%203` → 42 all-RS-3 results; `phone_brand_model=19_samsung_galaxy_%20s25`
  → 105 all-S25 results). lookup.py marks them `[! slug contains whitespace]`.
- **Count drift between reference sources**: `brands_*.json` (insert-config source) and the
  brand children in `filters_by_category.json` (facet source) differ by a model here and there
  (e.g. `apple_iphone_5c` exists only in brands_phones.json: 36 vs 35 Apple models). Slugs from
  either file are valid.
- **Very recent models can be absent** from both (iPhone 17 at capture time) — use `--keyword`
  + `--title-include/--title-exclude` for those.
