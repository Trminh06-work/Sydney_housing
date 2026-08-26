#!/usr/bin/env python3
"""
Independent cross-check of the dataset.

Every property that has BOTH an index-card reading and a listing-page reading is
two independent extractions of the same property. This script measures how often
they agree, field by field. This is a stronger integrity check than a small manual
spot-check because it covers all 180 doubly-observed properties, not a sample.
"""
import csv, glob, json, re, sys
sys.path.insert(0, "src")
from build_dataset import addr_key, parse_int, parse_price, canon_type, parse_date

detail = {}
for f in sorted(glob.glob("data/raw/detail_batch*.txt")):
    for line in open(f, encoding="utf-8"):
        p = line.strip().split("|")
        if len(p) == 13:
            detail[addr_key(p[0])] = p

rows = list(csv.DictReader(open("data/sydney_housing.csv")))
fields = {"bedrooms": 5, "bathrooms": 6, "parking": 7, "property_type": 4, "price_aud": 1}
res = {k: {"comparable": 0, "agree": 0, "disagree": []} for k in fields}

for r in rows:
    d = detail.get(addr_key(r["address"]))
    if not d:
        continue
    for name, idx in fields.items():
        raw = d[idx]
        if name == "price_aud":
            dv, iv = parse_price(raw), int(r["price_aud"])
        elif name == "property_type":
            dv, iv = canon_type(raw), r["property_type"] or None
        else:
            dv = parse_int(raw); iv = parse_int(r[name]) if r[name] != "" else None
        if dv is None or iv is None:
            continue
        res[name]["comparable"] += 1
        if dv == iv:
            res[name]["agree"] += 1
        else:
            res[name]["disagree"].append(
                {"address": r["address"], "index": iv, "listing": dv, "url": r["source_url"]})

print(f"{'field':<15}{'comparable':>11}{'agree':>7}{'rate':>8}")
out = {}
for k, v in res.items():
    n, a = v["comparable"], v["agree"]
    rate = 100 * a / n if n else 0
    print(f"{k:<15}{n:>11}{a:>7}{rate:>7.1f}%")
    out[k] = {"comparable": n, "agree": a, "agreement_pct": round(rate, 1),
              "disagreements": v["disagree"]}
json.dump(out, open("data/audit_crosscheck.json", "w"), indent=1)

print("\nExample disagreements:")
for k, v in res.items():
    for ex in v["disagree"][:2]:
        print(f"  {k}: {ex['address'][:45]:45} index={ex['index']} listing={ex['listing']}")
