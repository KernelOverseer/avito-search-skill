#!/usr/bin/env python3
"""Search Avito.ma and print clean, structured results.

Resolves names -> ids, builds a correct search URL (keyword in path, single city
in path, multi-city via ?cities=), fetches via the r.jina.ai proxy, parses the
embedded __NEXT_DATA__ JSON, and prints a concise listing (or full JSON).

Examples:
  search.py --category telephones --keyword iphone --price 3000-8000 --city casablanca
  search.py --category voitures --city rabat -f brand=58 -f model=golf7 --pages 2
  search.py --keyword "studio meuble" --city "el jadida" --seller-type pro
  search.py --category 2010 --price -80000 -f regdate=2015-2020 --json

Universal options: --keyword --category --city --sector --price --seller-type
--ad-options --include-unpriced.  Category-specific filters (brand, fuel, rooms,
condition…) go through -f KEY=VALUE (see: lookup.py filters <category>).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avito_common as ac

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)
CHALLENGE_MARKERS = ("Just a moment", "challenge", "captcha", "Markdown Content:")
BASE = "https://www.avito.ma"


def err(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def seg(s):
    return quote(str(s), safe="")


def parse_price(v):
    v = v.strip()
    if re.fullmatch(r"\d+-\d+|-?\d+|\d+-", v) and v not in ("-", ""):
        return v
    err(f"--price must be MIN-MAX (open forms: -5000, 2000-); got {v!r}", 2)


def build_url(a):
    cat = ac.resolve_category(a.category) if a.category else None
    if a.category and cat is None:
        err(f"unknown category {a.category!r} — run: lookup.py category {a.category}", 2)

    cities = []
    for c in a.city or []:
        for part in str(c).split(","):
            part = part.strip()
            if not part:
                continue
            city = ac.resolve_city(part)
            if city is None:
                err(f"unknown city {part!r} — run: lookup.py city {part}", 2)
            cities.append(city)
    if a.sector and len(cities) != 1:
        err("--sector needs exactly one --city", 2)

    # path: /fr/{city|maroc}/{sector?}/{keyword-or-category-slug}
    if cities and len(cities) == 1:
        city_seg = ac.slugify(cities[0]["name"])
    else:
        city_seg = "maroc"
    sector_seg = ""
    if a.sector:
        sector_seg, area_id = ac.resolve_sector(cities[0], a.sector)
        if area_id is None:
            warn(f"sector {a.sector!r} not in catalog; using derived slug {sector_seg!r}")
    if a.keyword:
        last = a.keyword
    elif cat:
        last = cat["searchSlug"]
    else:
        err("need --keyword or --category (or both)", 2)
    path = f"/fr/{seg(city_seg)}" + (f"/{seg(sector_seg)}" if sector_seg else "") + f"/{seg(last)}"

    params = {}
    if cat and a.keyword:
        params["category"] = cat["id"]
    if len(cities) > 1:
        params["cities"] = ",".join(c["id"] for c in cities)
    if a.price:
        params["price"] = parse_price(a.price)
    if a.seller_type:
        st = {"particulier": "0", "particuliers": "0", "p": "0",
              "pro": "1", "professionnel": "1", "professionnels": "1"}
        key = ac.norm(a.seller_type).replace(" ", "")
        if key not in st:
            err("--seller-type must be 'particulier' or 'pro'", 2)
        params["seller_type"] = st[key]
    ad_opts = [o.strip() for o in (a.ad_options or "").split(",") if o.strip()]
    bad = [o for o in ad_opts if o not in ("has_price", "has_image", "hotdeal", "urgent")]
    if bad:
        err(f"bad --ad-options {bad}; valid: has_price, has_image, hotdeal, urgent", 2)
    if not a.include_unpriced and "has_price" not in ad_opts:
        ad_opts.append("has_price")
    if a.include_unpriced:
        ad_opts = [o for o in ad_opts if o != "has_price"]
    if ad_opts:
        params["ad_options"] = ",".join(ad_opts)

    known = None
    if cat and a.filter:
        entry = ac.category_filters(cat["id"])
        known = set((entry or {}).get("filters", {}).keys())
        for f in (entry or {}).get("filters", {}).values():
            if f.get("childrenKey"):
                known.add(f["childrenKey"])  # e.g. model under brand
        known |= {"category", "cities", "price", "seller_type", "ad_options", "o"}
    for f in a.filter or []:
        if "=" not in f:
            err(f"-f must be KEY=VALUE, got {f!r}", 2)
        k, v = f.split("=", 1)
        if known is not None and k not in known:
            warn(f"filter {k!r} not in catalog for this category — sending anyway.")
        params[k] = v
    return path, params


def jina_fetch(url, timeout):
    """Fetch a search page through r.jina.ai; return the raw HTML body."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_name = tmp.name
    try:
        cp = subprocess.run(
            ["curl", "-sS", "-f", "--max-time", str(timeout),
             "-H", "x-respond-with: html",
             "-o", tmp_name, f"https://r.jina.ai/{url}"],
            capture_output=True, text=True)
        if cp.returncode == 22:
            return None, f"proxy returned HTTP error for {url}"
        if cp.returncode != 0:
            return None, f"curl failed (exit {cp.returncode}): {cp.stderr.strip()[:200]}"
        body = open(tmp_name, encoding="utf-8", errors="replace").read()
        return body, None
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def extract_next_data(body):
    m = NEXT_DATA_RE.search(body)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def fetch_page(url, timeout, retry_wait):
    body, ferr = jina_fetch(url, timeout)
    if ferr is None:
        data = extract_next_data(body)
        if data is not None:
            try:
                cp = data["props"]["pageProps"]["componentProps"]
                if cp.get("ads") is not None:
                    return cp, None
            except (KeyError, TypeError):
                pass
        if any(mk in body for mk in CHALLENGE_MARKERS):
            ferr = "proxy/Cloudflare challenge page returned"
        else:
            ferr = f"no __NEXT_DATA__ in response; head: {body[:180]!r}"
    warn(f"{ferr} — retrying once in {retry_wait}s ({url})")
    time.sleep(retry_wait)
    body, ferr2 = jina_fetch(url, timeout)
    if ferr2 is not None:
        return None, ferr2
    data = extract_next_data(body)
    if data is None:
        return None, "still no __NEXT_DATA__ after retry — likely rate-limited by r.jina.ai; wait 60+s"
    try:
        return data["props"]["pageProps"]["componentProps"], None
    except (KeyError, TypeError):
        return None, "unexpected __NEXT_DATA__ shape after retry"


def clean_ad(ad):
    price = ad.get("price") or {}
    monthly = ad.get("monthlyPayment") or {}
    seller = ad.get("seller") or {}
    params = {}
    for p in (ad.get("params") or {}).get("secondary", []) or []:
        if p.get("label") and p.get("value"):
            params[p["label"]] = p["value"]
    flags = [f for f, k in (("urgent", "isUrgent"), ("hotdeal", "isHotDeal"),
                            ("delivery", "isDelivery"), ("shop", "isShop"),
                            ("premium", "isPremium")) if ad.get(k)]
    if ad.get("discount"):
        flags.append("discount")
    phone = (seller.get("phone") or {}).get("number")
    return {
        "id": ad.get("id") or ad.get("listId"),
        "subject": ad.get("subject"),
        "price": {"value": price.get("value"), "currency": price.get("currency")} if price.get("value") else None,
        "old_price": (ad.get("oldPrice") or {}).get("value"),
        "loan_monthly_dh": monthly.get("value"),
        "location": ad.get("location"),
        "city_id": ad.get("cityId"),
        "area_id": ad.get("areaId"),
        "date": ad.get("date"),
        "params": params,
        "seller": {"name": seller.get("name"), "type": seller.get("type"),
                   "phone": phone, "verified": seller.get("isVerifiedSeller")},
        "images": len(ad.get("images") or []),
        "flags": flags,
        "category": (ad.get("category") or {}).get("name"),
        "url": ad.get("href"),
    }


def facet_summary(cp):
    out = {}
    for f in (cp.get("facetedSearchResponse") or {}).get("filters", []):
        key = f.get("queryParam") or f.get("key")
        vals = sorted(f.get("values") or [], key=lambda v: -int(v.get("count") or 0))[:10]
        out[key] = {"label": f.get("label"),
                    "values": [{"key": v.get("key"), "label": v.get("value"),
                                "count": int(v.get("count") or 0)} for v in vals]}
    return out


def fmt_price(ad):
    p = ad["price"]
    if not p:
        return "prix n.c."
    s = f"{p['value']:,}".replace(",", " ") + f" {p.get('currency', 'DH')}"
    if ad.get("old_price"):
        s += " " + f"(was {ad['old_price']:,})".replace(",", " ")
    return s


def print_text(url, total, ads, shown, pages_fetched):
    print(f"Query: {url}")
    print(f"Total matching ads: {total:,} | fetched {pages_fetched} page(s), {len(ads)} ads | showing {min(shown, len(ads))}")
    print()
    for i, ad in enumerate(ads[:shown], 1):
        flags = " ".join(f"[{f.upper()}]" for f in ad["flags"])
        seller = "PRO" if (ad["seller"]["type"] or "").upper() in ("STORE", "PRO") else "part."
        print(f"{i:>3}. {ad['subject']} — {fmt_price(ad)} — {ad['location'] or '?'} — {ad['date'] or '?'} — {seller} {flags}")
        print(f"     {ad['url']}")
    if total > len(ads):
        print(f"\n({total - len(ads):,} more ads not fetched — rerun with --pages N)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--keyword", help="free-text search term (goes in the URL path)")
    p.add_argument("--category", help="category id, name or slug (see lookup.py category)")
    p.add_argument("--city", action="append", help="city name or id; repeat or comma-separate for multiple")
    p.add_argument("--sector", help="sector/arrondissement name within the single city")
    p.add_argument("--price", help="MIN-MAX in DH, open forms -5000 / 2000-")
    p.add_argument("--seller-type", help="particulier | pro")
    p.add_argument("--ad-options", help="csv of: has_price,has_image,hotdeal,urgent (default has_price)")
    p.add_argument("--include-unpriced", action="store_true", help="don't force ad_options=has_price")
    p.add_argument("-f", "--filter", action="append", default=[], metavar="KEY=VALUE",
                   help="category-specific filter param (see: lookup.py filters <category>)")
    p.add_argument("--pages", type=int, default=1, help="pages to fetch (35 ads/page)")
    p.add_argument("--top", type=int, default=20, help="ads to show in text output")
    p.add_argument("--json", action="store_true", help="full structured JSON output")
    p.add_argument("--facets", action="store_true", help="include facet counts in JSON output")
    p.add_argument("--sleep", type=float, default=3.0, help="pause between pages (rate limit)")
    p.add_argument("--timeout", type=int, default=60, help="curl timeout per request")
    p.add_argument("--retry-wait", type=float, default=30.0, help="wait before the single retry")
    p.add_argument("--dry-run", action="store_true", help="print the built URL and exit (no fetch)")
    a = p.parse_args()

    path, params = build_url(a)
    url = BASE + path
    if params:
        url += "?" + urlencode(params, quote_via=quote)
    if a.dry_run:
        print(url)
        return

    all_ads, seen, total, fetched, facets = [], set(), None, 0, None
    for page in range(1, a.pages + 1):
        page_url = url if page == 1 else f"{url}{'&' if '?' in url else '?'}o={page}"
        if page > 1:
            time.sleep(a.sleep)
        cp, ferr = fetch_page(page_url, a.timeout, a.retry_wait)
        if ferr is not None:
            if fetched:
                warn(f"stopping at page {page}: {ferr}")
                break
            err(f"{ferr}\n  url: {page_url}", 1)
        fetched += 1
        ads_obj = cp.get("ads") or {}
        if total is None:
            total = ads_obj.get("totalListingAds")
        page_ads = ads_obj.get("ads") or []
        if not page_ads:
            if page == 1:
                warn("page 1 returned 0 ads — check slugs/filters or loosen the query")
            break
        if facets is None:
            facets = facet_summary(cp)
        for ad in page_ads:
            ca = clean_ad(ad)
            key = ca["id"] or f"{ca['subject']}|{ca['location']}"
            if key not in seen:
                seen.add(key)
                all_ads.append(ca)
    if total is None:
        total = len(all_ads)

    if a.json:
        out = {"url": url, "total": total, "pages_fetched": fetched, "ads": all_ads}
        if a.facets:
            out["facets"] = facets
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print_text(url, total, all_ads, a.top, fetched)


if __name__ == "__main__":
    main()
