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
`mileage_exact` (min-max), `pfiscale`, `auto_condition`, `v_origin`, `doors`, `first_owner`.
Phones: `phone_brand`, `phone_model`, `condition`, `storage_capacity`.
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
- sort param → none exists on web UI (relevance/date mix; `sortingMethod: SCORE` server-side)

## Multi-value encoding

Comma-separated: `cities=5,8`, `brand=49,13`, `extra_details=car_ac,car_airbags`.
Ranges: `min-max` (`price=3000-8000`, `regdate=2015-2020`, `mileage_exact=0-100000`).
