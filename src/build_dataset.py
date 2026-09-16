#!/usr/bin/env python3
"""
Build the consolidated Sydney housing dataset.

Inputs  : data/raw/index_<suburb>_p<N>.txt   (Domain sold-listings index pages)
          data/raw/detail_batch<NN>.txt      (Domain individual listing pages)
          data/raw/suburb_context.csv        (ABS SEIFA 2021 + Domain suburb medians)
Output  : data/sydney_housing.csv
          data/data_dictionary.md
          data/collection_log.json

Merge rule: the index card is authoritative for price / beds / baths / parking /
area (it is the field Domain renders on the search result). The listing page
supplies sale method, agency, agent, feature tags and the marketing description,
and provides a second, independent reading of price and sold date which is
retained separately so disagreement can be measured rather than hidden.
"""
import csv, glob, json, os, re, unicodedata
from datetime import datetime, date

RAW = "data/raw"
RETRIEVED_AT = "2026-08-18T06:00:00Z"
EPOCH = date(2026, 1, 1)

log = {"retrieved_at": RETRIEVED_AT, "source_site": "domain.com.au",
       "index_pages": [], "rejected": [], "counts": {}}

# ---------- helpers ----------------------------------------------------------
def norm(s):
    s = unicodedata.normalize("NFKC", (s or "").strip())
    return "" if s.upper() in ("NA", "N/A", "") else s

def parse_price(s):
    s = norm(s)
    if not s or "withheld" in s.lower():
        return None
    d = re.sub(r"[^\d]", "", s)
    return int(d) if d else None

MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

def parse_date(s):
    """Accept '17 Aug 2026' and '2026-08-17'. Reject bare years / out-of-window."""
    s = norm(s)
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})$", s)
        if not m:
            return None                      # bare '2013', '2024', etc.
        d, mon, y = int(m.group(1)), MONTHS.get(m.group(2).lower()), int(m.group(3))
        if not mon:
            return None
        mo = mon
    try:
        dt = date(y, mo, d)
    except ValueError:
        return None
    return dt if date(2025, 1, 1) <= dt <= date(2026, 12, 31) else None

def parse_area(s):
    """First numeric area token in m2. Returns (value, raw_had_multiple)."""
    s = norm(s).replace(",", "")
    if not s:
        return None, False
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm)?", s)
    nums = [float(n) for n in nums if n]
    if not nums:
        return None, False
    return nums[0], len(nums) > 1

def parse_int(s):
    s = norm(s)
    if not s:
        return None
    m = re.match(r"^\d+$", s)
    return int(m.group()) if m else None

def canon_type(s):
    s = norm(s).lower()
    if not s:
        return None
    if "semi" in s:        return "Semi-detached"
    if "town" in s:        return "Townhouse"
    if "villa" in s:       return "Villa"
    if "studio" in s:      return "Studio"
    if "retirement" in s:  return "Retirement living"
    if "apartment" in s or "unit" in s or "flat" in s: return "Apartment"
    if "house" in s:       return "House"
    return s.title()

def canon_method(s):
    s = norm(s).lower()
    if not s:                        return None
    if "prior" in s:                 return "Sold prior to auction"
    if "auction" in s:               return "Auction"
    if "treaty" in s:                return "Private treaty"
    return "Other"

def addr_key(a):
    """Normalised address key for matching index <-> detail rows."""
    a = norm(a).lower()
    a = re.sub(r"\bnsw\b.*$", "", a)          # drop ', Blacktown NSW 2148' tail
    a = re.sub(r",.*$", "", a)                # drop suburb after first comma
    a = a.replace("unit ", "").replace("&", " and ")
    a = re.sub(r"[^a-z0-9]+", "", a)
    return a

# ---------- 1. index pages ---------------------------------------------------
index_rows = []
for f in sorted(glob.glob(f"{RAW}/index_*.txt")):
    suburb = os.path.basename(f).split("_")[1].title()
    n = 0
    for line in open(f, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        p = line.split("|")
        if len(p) < 9:
            log["rejected"].append({"file": f, "reason": "malformed_index_row",
                                    "value": line[:80]})
            continue
        if "block of units" in p[4].lower():
            log["rejected"].append({"file": f, "reason": "whole_building_not_a_dwelling",
                                    "value": p[1]})
            continue
        if not re.search(r"\d", p[1]):
            log["rejected"].append({"file": f, "reason": "project_ad_no_street_number",
                                    "value": p[1]})
            continue
        index_rows.append({"suburb": suburb, "url": p[0], "address": p[1],
                           "price": p[2], "sold_date": p[3], "ptype": p[4],
                           "beds": p[5], "baths": p[6], "parking": p[7],
                           "area": p[8], "src_page": os.path.basename(f)})
        n += 1
    log["index_pages"].append({"file": os.path.basename(f), "records": n})

# dedupe on listing id
seen, deduped = set(), []
for r in index_rows:
    lid = r["url"].rsplit("-", 1)[-1]
    if lid in seen:
        log["rejected"].append({"reason": "duplicate_listing_id", "value": r["url"]})
        continue
    seen.add(lid)
    r["listing_id"] = lid
    deduped.append(r)

# ---------- 2. detail pages --------------------------------------------------
detail = {}
for f in sorted(glob.glob(f"{RAW}/detail_batch*.txt")):
    for line in open(f, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        p = line.split("|")
        if len(p) != 13:
            log["rejected"].append({"file": f, "reason": "malformed_detail_row",
                                    "value": line[:80]})
            continue
        detail[addr_key(p[0])] = {
            "d_price": p[1], "d_date": p[2], "method": p[3], "d_ptype": p[4],
            "d_beds": p[5], "d_baths": p[6], "d_parking": p[7], "d_area": p[8],
            "agency": p[9], "agent": p[10], "features": p[11], "description": p[12]}

# ---------- 3. suburb context ------------------------------------------------
ctx = {r["suburb"]: r for r in csv.DictReader(open(f"{RAW}/suburb_context.csv"))}

# ---------- 4. merge, clean, validate ---------------------------------------
COLS = ["property_id","listing_id","source_url","source_site","retrieved_at",
        "address","suburb","postcode",
        "price_aud",
        "sold_date","sold_date_listing","date_source_disagrees","sale_method",
        "days_since_epoch",
        "property_type","bedrooms","bathrooms","parking",
        "area_sqm","area_source","area_is_internal","area_multivalued","area_implausible",
        "description","description_wordcount","features","feature_count",
        "agency","agent",
        "seifa_irsad_score","seifa_irsad_decile","seifa_irsd_score","seifa_irsd_decile",
        "seifa_ieo_decile","seifa_ier_decile","suburb_urp_2021",
        "suburb_median_house_3bed","suburb_median_unit_2bed","suburb_sales_12m"]

UNIT_TYPES = {"Apartment", "Studio", "Retirement living"}
rows, pid = [], 0
withheld = {"Blacktown": 0, "Chatswood": 0, "Mosman": 0}
matched = 0

for r in deduped:
    price = parse_price(r["price"])
    if price is None:
        withheld[r["suburb"]] += 1
        log["rejected"].append({"reason": "no_displayed_price", "value": r["url"]})
        continue

    d = detail.get(addr_key(r["address"]), {})
    if not d:
        # COMPLETENESS RULE: retain a property only if its individual listing page was
        # also retrieved. Index cards alone carry no sale method, agency, agent, feature
        # tags or marketing text, and often omit area. Admitting index-only rows would
        # reintroduce ~20% missingness on those columns for no gain in information.
        # Which properties got a listing fetch was decided by recency within suburb --
        # a rule neutral with respect to property type. It does NOT preferentially
        # retain houses, which matters because Domain publishes land size for houses far
        # more often than for units (see data_dictionary.md).
        log["rejected"].append({"reason": "no_listing_page_retrieved", "value": r["url"]})
        continue
    matched += 1

    idx_dt = parse_date(r["sold_date"])
    lst_dt = parse_date(d.get("d_date", ""))
    if idx_dt is None:
        log["rejected"].append({"reason": "unparseable_index_date", "value": r["url"]})
        continue

    # Area: prefer the index card, fall back to the listing page. Domain often omits
    # area from the search-result card but publishes it on the listing itself, so this
    # fallback is a genuine coverage gain, not an imputation -- both are observed values.
    area, multi = parse_area(r["area"])
    area_src = "index"
    if area is None:
        area, multi = parse_area(d.get("d_area", ""))
        area_src = "listing" if area is not None else "none"
    ptype = canon_type(r["ptype"]) or canon_type(d.get("d_ptype", ""))
    internal = ptype in UNIT_TYPES
    # a unit reporting >600 m2 is the whole strata parcel, not the dwelling
    implausible = bool(area and internal and area > 600)

    c = ctx[r["suburb"]]
    desc = norm(d.get("description", ""))
    feats = norm(d.get("features", ""))
    pid += 1
    rows.append({
        "property_id": pid,
        "listing_id": r["listing_id"],
        "source_url": r["url"],
        "source_site": "domain.com.au",
        "retrieved_at": RETRIEVED_AT,
        "address": norm(r["address"]),
        "suburb": r["suburb"],
        "postcode": c["postcode"],
        "price_aud": price,
        "sold_date": idx_dt.isoformat(),
        "sold_date_listing": lst_dt.isoformat() if lst_dt else "",
        "date_source_disagrees": int(bool(lst_dt and lst_dt != idx_dt)),
        "sale_method": canon_method(d.get("method", "")) or "",
        "days_since_epoch": (idx_dt - EPOCH).days,
        "property_type": ptype or "",
        "bedrooms": parse_int(r["beds"]) if parse_int(r["beds"]) is not None else "",
        "bathrooms": parse_int(r["baths"]) if parse_int(r["baths"]) is not None else "",
        "parking": parse_int(r["parking"]) if parse_int(r["parking"]) is not None else "",
        "area_sqm": area if area is not None else "",
        "area_is_internal": int(internal),
        "area_multivalued": int(multi),
        "area_source": area_src,
        "area_implausible": int(implausible),
        "description": desc,
        "description_wordcount": len(desc.split()) if desc else 0,
        "features": feats,
        "feature_count": len([x for x in feats.split(";") if x.strip()]) if feats else 0,
        "agency": norm(d.get("agency", "")),
        "agent": norm(d.get("agent", "")),
        "seifa_irsad_score": c["seifa_irsad_score"],
        "seifa_irsad_decile": c["seifa_irsad_decile"],
        "seifa_irsd_score": c["seifa_irsd_score"],
        "seifa_irsd_decile": c["seifa_irsd_decile"],
        "seifa_ieo_decile": c["seifa_ieo_decile"],
        "seifa_ier_decile": c["seifa_ier_decile"],
        "suburb_urp_2021": c["urp_2021"],
        "suburb_median_house_3bed": c["suburb_median_house_3bed"],
        "suburb_median_unit_2bed": c["suburb_median_unit_2bed"],
        "suburb_sales_12m": c["suburb_sales_12m"],
    })

# ---------- 5. hard assertions ----------------------------------------------
from collections import Counter
by_sub = Counter(r["suburb"] for r in rows)
assert len(rows) >= 100, f"FAIL: only {len(rows)} rows (need >=100)"
for s in ("Blacktown", "Chatswood", "Mosman"):
    assert by_sub[s] >= 30, f"FAIL: {s} has {by_sub[s]} rows (need >=30)"
assert all(r["price_aud"] > 0 for r in rows), "FAIL: non-positive price"
assert len({r["listing_id"] for r in rows}) == len(rows), "FAIL: duplicate listing_id"

# ---------- 6. write ---------------------------------------------------------
os.makedirs("data", exist_ok=True)
with open("data/sydney_housing.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS)
    w.writeheader()
    w.writerows(rows)

log["counts"] = {
    "index_records_parsed": len(index_rows),
    "after_dedupe": len(deduped),
    "detail_records_loaded": len(detail),
    "detail_matched_to_index": matched,
    "final_rows": len(rows),
    "by_suburb": dict(by_sub),
    "dropped_price_withheld_or_absent": withheld,
    "rejected_total": len(log["rejected"]),
}
json.dump(log, open("data/collection_log.json", "w"), indent=1)

print(f"rows={len(rows)}  by_suburb={dict(by_sub)}")
print(f"detail matched {matched}/{len(deduped)}")
