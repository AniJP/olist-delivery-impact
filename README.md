# How should a marketplace set delivery promises?

A data science project on **96k real e-commerce orders** from Olist, a Brazilian marketplace. Olist's delivery estimates are padded by about 12 days, yet 6.8% of orders still arrive late, and late orders collapse review scores (4.3 → 2.3 stars). This project measures what lateness really costs, models each order's delivery time at checkout, and designs an experiment for setting **personalised, shorter promises without more late orders**.

> **Status:** Phase 1 (data foundation) complete. Phases 2–6 in progress.

## Plan

| Phase | Question | Methods |
|---|---|---|
| **1. Data foundation** ✅ | Can we trust the data? | dbt + DuckDB, 56 data tests, unit tests, SQL-vs-pandas reconciliation |
| 2. Causal analysis | How much does lateness *cause* bad reviews and lost customers? | Regression with controls, propensity matching, dose-response, sensitivity analysis |
| 3. Prediction | How long will *this* order take, known at checkout? | Quantile gradient boosting, time-based validation, calibration |
| 4. Trade-off | How much shorter could promises be at today's late rate? | Promise-length vs. late-rate frontier |
| 5. Experiment design | How would we test personalised promises safely? | Metrics, guardrails, power analysis |
| 6. Business impact | What should Olist do? | Memo + dashboard |

## Early findings (from [docs/DATA_PROFILE.md](docs/DATA_PROFILE.md))
- **Padded promises:** the median promise is 24 days for a 10-day median delivery.
- **Lateness wrecks reviews:** the 1-star share rises from ~6% to ~68% once an order is 8+ days late.
- **Early barely helps:** 15+ days early scores only 0.1 stars more than 1–7 days early.
- **Measurement trap:** 73% of late orders were reviewed before they arrived.
- **Split checkouts inflate retention by ~60%:** grouping same-day orders into one purchase drops the 180-day repeat rate from 3.2% to 2.0%.

## Data model

```
raw CSVs (9 tables) ─► staging (typed, deduplicated, geo-cleaned)
                     ─► intermediate (baskets, payments, purchase sessions)
                     ─► marts: fct_orders (1 row/order: promise, outcome, review, checkout features)
                               fct_customer_first_purchase (retention cohort)
```

Key modelling decisions:
- **Purchase sessions.** Olist creates one order per seller, so same-day orders by one person are one checkout, not repeat purchases.
- **Eligibility flag.** Orders with impossible timelines (carrier pickup before purchase, etc.) stay in the table but are excluded from analysis via `is_analysis_eligible`.
- **One review per order:** the latest survey answer.
- **Distance:** great-circle km between the seller's and customer's zip-code centroids, after dropping geocodes outside Brazil.

## Quality checks
- **dbt data tests** on keys, ranges and relationships, plus invariants (the late flag matches the dates, no same-day "repeat" purchases, a distance sanity check).
- **dbt unit test** for the purchase-session logic.
- **Reconciliation:** `scripts/reconcile.py` recomputes the headline metrics from the raw CSVs with pandas and checks the SQL warehouse matches exactly.
- **CI** builds the whole warehouse from a synthetic dataset with the identical schema on every push. The real data isn't committed.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
make setup
# download the data into data/raw (see data/README.md), then:
make build        # dbt: build + test the warehouse
make reconcile    # SQL vs. pandas
```

## Data
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (CC BY-NC-SA 4.0): real, anonymised orders from 2016–2018.
