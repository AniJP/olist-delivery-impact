# Data profile and early findings

Profiled from the raw Kaggle files before any modelling (2026-10-29). Every number here is
reproduced by `scripts/reconcile.py` from both the dbt warehouse and an independent pandas pass.

## Coverage
- **99,441 orders** from Sep 2016 to Oct 2018; volume is meaningful from Jan 2017 to Aug 2018.
  Analysis windows end on **2018-08-31** (later months hold only a handful of orders).
- 96,478 orders are `delivered`; 96,282 are **analysis-eligible** (delivered, have items, sane timeline).
- 96,096 distinct customers (`customer_unique_id`); `customer_id` is per order, not per person.

## Data-quality issues and how they're handled
| Issue | Count | Handling |
|---|---|---|
| Handed to carrier *before* purchase | 166 | `has_timestamp_anomaly`, excluded from analysis |
| Delivered *before* carrier pickup | 23 | same |
| Status `delivered` but no delivery date | 8 | not eligible |
| Orders with no items (mostly `unavailable`/`canceled`) | 775 | not eligible |
| Orders with 2–3 survey answers | 547 | keep the latest answer (`stg_olist__reviews`) |
| One `review_id` attached to several orders | 814 | expected (one survey per checkout); kept |
| Geolocation points outside Brazil | 42 | dropped before taking each zip's median point |
| Customer / seller zips with no geolocation | 278 / 7 | `distance_km` is null for those orders |
| Categories missing from the translation file | 2 | seed `category_translation_patch` |
| Payments ≠ items + freight by more than R$1 | 249 | dbt warning test; vouchers and instalment interest |

## Findings that shaped the project
1. **Estimates are heavily padded.** The median promise is 24 days and the median delivery 10, so
   the median order arrives 12 days early. Only **6.8%** of orders are late.
2. **Lateness wrecks reviews.** The average score is 4.29 on time and 2.27 when late, and the 1-star
   share goes from ~6% to ~68% once an order is 8+ days late.
3. **Arriving very early barely helps.** 15+ days early scores 4.32 against 4.20 for 1–7 days early,
   so the padding buys almost no satisfaction.
4. **Measurement trap.** 73% of late orders were reviewed *before they arrived*: the survey goes out
   around the estimated date. Many "late" reviews rate a missing package, not the delivered product.
5. **Split checkouts inflate retention.** Olist creates one order per seller, so a single checkout
   can look like repeat purchases (1,887 orders sit in multi-order same-day sessions). Grouping orders
   into purchase sessions drops the 180-day repeat rate from a naive ~3.2% to **2.0%**.
6. **Retention after late deliveries is an open question.** Among customers with a full 180-day
   follow-up window, 2.03% return after an on-time first purchase and 1.57% after a late one. That's
   borderline significant and still confounded (region, category, season); Phase 2 tests it properly.
