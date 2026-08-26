# Data dictionary — `sydney_housing.csv`

SIT307 Machine Learning, Distinction portfolio task, Part 1.
239 sold residential properties across three Sydney suburbs.
Retrieved 18-19 August 2026 from publicly accessible `domain.com.au` pages
permitted by that site's `robots.txt`, enriched with ABS SEIFA 2021 (CC BY).

Prediction target: **`price_aud`**.

## Identity and provenance
| Column | Type | Description |
|---|---|---|
| `property_id` | int | Local row identifier, 1–219. |
| `listing_id` | str | Domain listing identifier. Deduplication key; unique. |
| `source_url` | str | **Direct link to the page this row came from.** Click to verify any record. |
| `source_site` | str | `domain.com.au` for all rows. |
| `retrieved_at` | datetime | UTC retrieval timestamp. |

## Location
| Column | Type | Description |
|---|---|---|
| `address` | str | Street address as published. |
| `suburb` | cat | Blacktown / Chatswood / Mosman. |
| `postcode` | int | 2148 / 2067 / 2088. |

## Target
| Column | Type | Description |
|---|---|---|
| `price_aud` | int | Sale price in AUD. Never null. |

## Transaction
| Column | Type | Description |
|---|---|---|
| `sold_date` | date | Sold date from the index card (authoritative). ISO 8601. |
| `sold_date_listing` | date | Sold date from the listing page, where parseable. Blank if the page showed a bare year or nothing. |
| `date_source_disagrees` | 0/1 | 1 where the two dates differ (16 rows). See caveat below. |
| `sale_method` | cat | Auction / Private treaty / Sold prior to auction / Other. Blank where the listing page was not retrieved. |
| `days_since_epoch` | int | Days from 2026-01-01. Numeric time index for trend analysis. |

## Property characteristics
| Column | Type | Description |
|---|---|---|
| `property_type` | cat | House, Apartment, Townhouse, Semi-detached, Villa, Studio, Retirement living. |
| `bedrooms` | int | Blank = not shown, **not** zero. |
| `bathrooms` | int | Blank = not shown. |
| `parking` | int | Car spaces. Blank = not shown, **not** "no parking". |
| `area_sqm` | float | **Semantics vary — see `area_is_internal`.** |
| `area_is_internal` | 0/1 | 1 for apartments/studios/retirement living, where the figure is internal or on-title floor area; 0 for houses and similar, where it is land area. |
| `area_multivalued` | 0/1 | 1 where the source string carried more than one area figure. 0 throughout the retained data. |
| `area_implausible` | 0/1 | 1 where a unit reports >600 m² — almost certainly the whole strata parcel, not the dwelling (9 rows). Do not treat these as dwelling size. |

## Text and agency
| Column | Type | Description |
|---|---|---|
| `description` | str | Agent marketing description, truncated to ~700 characters. Present for 180/219 rows. |
| `description_wordcount` | int | Word count; 0 where absent. |
| `features` | str | Semicolon-delimited feature tags. |
| `feature_count` | int | Number of feature tags. |
| `agency` | str | Listing agency. |
| `agent` | str | Listing agent. |

## Suburb-level context (joined, constant within suburb)
| Column | Source | Description |
|---|---|---|
| `seifa_irsad_score`, `seifa_irsad_decile` | ABS SEIFA 2021 (SAL) | Relative Socio-economic Advantage and Disadvantage; national decile. |
| `seifa_irsd_score`, `seifa_irsd_decile` | ABS SEIFA 2021 | Relative Socio-economic Disadvantage. |
| `seifa_ieo_decile` | ABS SEIFA 2021 | Education and Occupation. |
| `seifa_ier_decile` | ABS SEIFA 2021 | Economic Resources. |
| `suburb_urp_2021` | ABS 2021 Census | Usual resident population. |
| `suburb_median_house_3bed`, `suburb_median_unit_2bed` | Domain suburb profile | Median price, 12 months to Aug 2026. |
| `suburb_sales_12m` | Domain suburb profile | Reported sales volume, 12 months. |

> **Caution.** All suburb-level columns are constant within a suburb. They add no
> within-suburb variation and are effectively a re-encoding of `suburb`. Treat them
> as such; do not present them as property-level features.

## Known caveats
1. **Price-displayed selection.** Collection used Domain's `excludepricewithheld` filter, so every row has a price — but sales with withheld prices are absent by construction, and withholding is not random. The sample under-represents transactions where the price was suppressed.
2. **`area_sqm` is two variables in one column.** Split it or interact it with `property_type` before modelling.
3. **Date disagreement.** 16 rows show a different sold date on the index card than on the listing page; the index value is retained. The listing-page value is preserved in `sold_date_listing` so the discrepancy is measurable.
4. **Unobserved drivers.** No year built, condition, renovation status, aspect, view, floor level, strata levy or land zoning. For Mosman in particular, harbour outlook is plausibly the single largest price driver and is entirely unobserved.
5. **Narrow time window.** Sales span roughly March–August 2026; the data captures one market state and will not extrapolate across cycles.


---

# Missing values

Every retained property was observed on **both** its index card and its own listing
page, so `description`, `features`, `agency` and `agent` are effectively complete.
What remains missing is missing because Domain never published it.

| Column | Missing | Treatment |
|---|---|---|
| `price_aud` | 0% | **Never imputed.** Rows without a price are dropped at build time. |
| `bedrooms` | 0.4% | Median, imputed inside each CV fold |
| `bathrooms` | 0% | — |
| `parking` | 7.1% | Median inside fold. **Absent ≠ zero.** |
| `area_sqm` | 35.1% | Median inside fold, paired with the `area_known` flag |
| `sale_method` | 3.8% | Own category `"Unknown"` |
| `features` | 0.8% | Empty string; keyword flags become 0 |
| `agency`, `agent` | 0–1.3% | Left blank; not used as predictors |

**Area missingness is structural, not random.** It is absent for 46.0% of apartments
against 20.0% of houses, because land size is a headline attribute of a house and not
a meaningful one for a strata lot. Two consequences:

1. **Do not filter to complete records.** Doing so discards 39% of the sample and
   shifts it from 52.7% apartments to 44.5% — turning a study of three housing
   markets into a study of houses, in two suburbs that are unit-dominant.
2. **Use `area_known` as a feature.** The fact that area was not published is itself
   informative. Hiding it measurably worsens accuracy (17.6% vs 17.2% MAPE).

**Imputation must happen inside cross-validation folds, not before.** Fitting an
imputer on the whole dataset leaks test-fold information into training. In
`notebooks/ai_lab.ipynb` every imputer sits inside an sklearn `Pipeline`; derived
features propagate `NaN` deliberately for the same reason.

`area_source` records where each area came from: `index` (search card), `listing`
(individual listing page — a fallback that raised coverage by ~19 points at no
collection cost), or `none`.
