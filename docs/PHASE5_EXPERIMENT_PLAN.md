# Phase 5: Experiment plan for model-based delivery promises

Sizing and simulations: [`analysis/05_experiment_design.ipynb`](../analysis/05_experiment_design.ipynb). Helpers: [`analysis/experiment.py`](../analysis/experiment.py). Tables: [`phase5_sample_sizes.csv`](phase5_sample_sizes.csv), [`phase5_geo_power.csv`](phase5_geo_power.csv).

## Why an experiment
Phase 4 showed that per-order model promises could cut late deliveries by about a quarter. Two links can't be verified from historical data:
1. **Reviews:** whether reviews react to the new promises the way the Phase 2 dose-response predicts.
2. **Sales:** what a shorter promise is worth. Historical data only contains completed orders, never the customers a long promise turned away.

## Hypotheses
- **H1 (Reliable vs Control):** model promises at P92.5 reduce the 1-star review rate. Expected effect −1.4 pts, from 10.9%.
- **H2 (Fast vs Control):** model promises about 2 days shorter at today's late rate increase orders per visitor. Expected effect +1.6%, borrowed from Cui et al. (2024); unverified for Olist.

## Design

| Item | Choice |
|---|---|
| **Arms** | Control: Olist's current promise · Reliable: model P92.5 · Fast: model quantile matching today's late rate (about 2.1 days shorter) |
| **Allocation** | Equal, stratified by destination state |
| **Unit** | Customer (visitor ID before login). All visits and orders of a customer see one arm. |
| **Treatment** | Only the promised delivery date shown before and after checkout. Logistics, sellers and the review survey stay unchanged. |
| **Interference** | Minimal, since physical delivery is unchanged. A customer seeing different arms on different devices is the main risk, mitigated by logging in. |

## Metrics

| Type | Metric | Comparison |
|---|---|---|
| Primary | 1-star review rate per delivered order | Reliable vs Control |
| Primary | Orders per visitor (conversion) | Fast vs Control |
| Secondary | Late-delivery rate (manipulation check) | All arms |
| Secondary | Mean review score; average promise shown; revenue per visitor | All arms |
| Guardrail | Late rate: Fast must stay within +1 pt of Control | Fast vs Control |
| Guardrail | Cancellation rate; review response rate; sample-ratio mismatch | All arms |
| Long-term | 180-day repeat purchase | 10% holdout kept for 12 months after launch |

## Sample size (alpha 5% two-sided, 80% power)

| Question | Needed | At this dataset's volume (~6,700 orders/month) |
|---|---|---|
| Late rate falls, Reliable (9.0% → 6.5%) | ~1,760 orders per arm | 2–4 weeks |
| 1-star rate falls, Reliable (10.9% → 9.5%) | ~7,100 reviewed orders per arm | ~2 months (2 arms), ~3 months (3 arms), plus 2–4 weeks of review lag |
| Conversion +1.6%, Fast | 1.2M–6.1M visitors per arm, for baseline conversion of 5% down to 1% | Requires visitor-level traffic |
| Repeat purchase −15% (2.0% base) | ~32,000 new customers per arm | ~10 months of new customers plus 6 months of follow-up, so a holdout rather than a test readout |

## Validation of the design on real data
- **A/A tests:** across 200 random customer splits of real Feb–Aug 2018 orders, the 1-star comparison flagged 7% (unadjusted) and 6% (adjusted). Both are within simulation noise of 5%. Reported standard errors match the empirical spread.
- **Replay:** only the promise changes, so each real order can be re-scored against each arm's promise. With 2,000 orders per arm the late-rate drop is detected 88% of the time, matching the closed form.
- **Regression adjustment (CUPED):** checkout-time covariates explain only about 2% of review variance, so the time saved is small. Reviews are noisy in ways checkout data can't predict.
- **Geo alternative:** randomising about 100 two-digit CEP regions and simulating on real weekly orders keeps false positives at 4%. But even a 12-week test needs a ~13% lift for 80% power, so a geo test cannot measure a 1.6% sales effect. This is why the plan uses visitor-level randomisation.

## Monitoring and stopping
- **Four weekly looks** on the late-rate guardrail, with O'Brien–Fleming boundaries: |z| > 4.05, 2.86, 2.34, 2.02.
- **Sample-ratio mismatch** check (χ² on assignment counts) at every look; any mismatch pauses the test.
- **No early stopping for success** on primary metrics. The test runs until the review sample is complete.

## Analysis plan
- **Intention-to-treat** by assigned arm.
- **Models:**
  - Proportions: linear probability models with customer-clustered standard errors.
  - Means: OLS, adjusted for the pre-registered checkout covariates (predicted delivery quantiles, P(late at Olist's promise), Olist's promised days).
- **Multiple comparisons:** two primary comparisons, each at α = 0.05. The two arms answer different questions, so no family-wise correction is applied across them. Secondary metrics are reported with confidence intervals and not used for the decision.
- **Heterogeneity** by destination state is pre-specified, because Phase 4 predicts gains concentrated outside São Paulo.

## Decision rule
- **Ship Reliable** if the 1-star rate falls significantly and orders per visitor are not worse by more than 1% (non-inferiority).
- **Ship Fast** only if conversion rises significantly and the late rate stays within 1 point of Control.
- **If both pass**, pick the frontier point (Phase 4) using the measured sales value of a day against the measured review cost of lateness.

## Follow-up experiment
Phase 2 found that 74% of late orders are reviewed before they arrive. A separate test should hold the review survey until delivery. It belongs in its own experiment, because it changes how the review metric itself is measured.
