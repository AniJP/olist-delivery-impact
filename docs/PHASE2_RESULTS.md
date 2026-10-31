# Phase 2: What does a late delivery cost?

Full analysis: [`analysis/02_late_delivery_effect.ipynb`](../analysis/02_late_delivery_effect.ipynb). Estimators: [`analysis/causal.py`](../analysis/causal.py). All estimates: [`phase2_estimates.csv`](phase2_estimates.csv).

## Setup
- **Unit:** 95,637 delivered, reviewed orders (Sept 2016 – Aug 2018); 6.7% arrived after the promised date.
- **Treatment:** delivered after `estimated_delivery_date`.
- **Outcomes:**
  - review score (1–5)
  - 1-star review (yes/no)
  - for 56,342 first-time customers with a full follow-up window: a second purchase session within 180 days
- **Controls (checkout time only):**
  - distance, same-state flag, customer and seller state
  - product category, basket value, freight, weight, volume, number of items and sellers
  - promise length, payment type and instalments
  - purchase month, day of week and hour
- **Never controlled for:** shipping or carrier time. Those are the path by which orders become late, so controlling for them would erase the effect.

## Effect on the review

| Estimator | Stars | 95% CI | 1-star review |
|---|---|---|---|
| Naive difference | −2.02 | −2.06 to −1.98 | +47.2 pp |
| Regression + controls (seller-clustered SE) | −1.98 | −2.03 to −1.94 | +46.6 pp |
| Regression + seller fixed effects | −1.94 | −1.99 to −1.89 | +45.9 pp |
| Propensity weighting (ATT) | −2.00 | −2.04 to −1.96 | +47.2 pp |
| Doubly robust, cross-fitted gradient boosting (ATT) | **−1.99** | −2.03 to −1.95 | **+47.1 pp** |

- **Diagnostics:**
  - After weighting, every numeric control has |SMD| < 0.02, compared with up to 0.28 before.
  - Fewer than 2% of late orders have a propensity above 0.5, so comparable on-time orders exist for nearly all of them.
- **Robustness (regression, stars):**

  | Check | Stars |
  |---|---|
  | Drop the congested months (Nov 2017, Feb–Mar 2018) | −1.85 |
  | Month × customer-state fixed effects | −1.96 |
  | Single-seller, single-item orders only | −2.03 |
  | Same-state orders only | −1.72 |
  | Count only 4+ days late as late | −2.40 |

- **Placebo:** shuffling lateness within month × state cells gives −0.004 (20 draws, range −0.03 to +0.02).

## Dose-response
Compared with arriving 1–7 days early, adjusted for the same controls:

| Arrival | Stars |
|---|---|
| 15+ days early | +0.33 |
| 8–14 days early | +0.17 |
| On the promised day | −0.16 |
| 1–3 days late | −0.85 |
| 4–7 days late | −2.02 |
| 8–14 days late | −2.42 |
| 15+ days late | −2.34 |

An extra week of slack is worth about 0.16 stars, while missing the date costs up to 15 times that.

## Mechanism (descriptive)
- 74% of late orders were reviewed before the parcel arrived. Olist's survey goes out around the promised date.
- Those reviews average 1.84 stars, against 3.53 for late orders reviewed after arrival.
- The comparison is confounded by how late the order was (13.5 vs 1.9 days on average). Still, it makes survey timing a cheap lever worth testing.

## Effect on repeat purchase

| Estimator | Change in 180-day repeat rate | 95% CI |
|---|---|---|
| Naive difference | −0.47 pp | −0.87 to −0.06 |
| Regression + controls | −0.34 pp | −0.73 to +0.05 |
| Propensity weighting (ATT) | −0.32 pp | −0.75 to +0.11 |
| Doubly robust (ATT) | −0.30 pp | −0.73 to +0.12 |

- **Relative effect:** about −15% of the 2.03% base rate (risk ratio 0.85, E-value 1.63).
- **Power:** with 3,953 late and 52,389 on-time first-time customers, the minimum detectable effect at 80% power is 0.65 pp (32% relative). The data cannot confirm or rule out a 15% drop.

## Carried forward
- **Phase 3:** predict the probability of missing a promise, so the model has to be calibrated in the upper tail of delivery time.
- **Phase 4:** the cost of a late order is −1.99 stars; the value of slack is +0.16 stars per week early.
- **Phase 5:** retention needs an experiment sized below a 0.65 pp MDE. Survey timing is a candidate second arm.
