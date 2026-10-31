# Phase 4: How short can promises be, and what does it cost?

Full analysis: [`analysis/04_promise_tradeoff.ipynb`](../analysis/04_promise_tradeoff.ipynb). Policy code: [`analysis/policy.py`](../analysis/policy.py). Tables: [`phase4_frontier.csv`](phase4_frontier.csv), [`phase4_options.csv`](phase4_options.csv).

## Set-up
- **Inputs:**
  - Phase 3 calibrated delivery-time quantiles for every order in the calibration month (Jan 2018) and the test period (Feb–Aug 2018)
  - the Phase 2 dose-response: review change by how early or late an order arrives relative to its promise
- **Policies compared:**

  | Policy | Promise for each order |
  |---|---|
  | Olist shifted | Olist's own promise + *k* days for everyone |
  | Model, same quantile | the model's *q*-th percentile, so every order carries the same risk of being late |
  | Model, cost-aware | the day *d* that minimises *d + r · P(late by d)* |

- **Evaluation:** on actual outcomes. Orders never delivered count as late.
- **Honest deployment:** anything chosen in advance is tuned on January and then held fixed for Feb–Aug.

## The frontier (Feb–Aug 2018)
- Olist's promises averaged **22.9 days with 9.0% late**.
- Shifting Olist's promises 3 days shorter would push lateness to 15%.
- The model's frontier is below Olist's everywhere in the useful range.
- The cost-aware optimiser is indistinguishable from the simpler same-quantile rule, so the simple rule is recommended.

## Options (per 10,000 orders, vs Olist)

| Option | Late rate | Avg promise | Late orders avoided | Days shorter | Avg review change | 1-star reviews avoided |
|---|---|---|---|---|---|---|
| Olist today | 9.0% | 22.9 | | | | |
| A. Fewer late, same avg promise | 6.9% | 22.9 | 210 | 0.0 | +0.05 | 112 |
| B. Shorter promises, same late rate | 9.1% | 20.8 | 0 | 2.1 | −0.02 | −8 |
| **C. Deployable (P92.5, chosen in Jan)** | **6.5%** | **23.5** | **253** | −0.6 | **+0.06** | **141** |

- Options A and B are read off the test frontier.
- Option C is what Olist would actually have got from a quantile chosen in January to match its January late rate.

## Where the gain comes from
The model reallocates slack rather than cutting every promise.

| State | Orders | Olist promise | Model promise | Olist late | Model late |
|---|---|---|---|---|---|
| SP | 20,442 | 18.0 | 16.3 | 5.9% | 5.8% |
| RJ | 5,609 | 28.4 | 33.4 | 16.0% | 8.3% |
| MG | 5,243 | 23.9 | 23.0 | 7.3% | 6.2% |
| BA | 1,527 | 28.5 | 33.9 | 17.0% | 8.8% |
| CE | 571 | 30.0 | 33.3 | 22.4% | 15.9% |

- **Over-padded today:** São Paulo, 44% of orders, mostly same-state.
- **Under-promised today:** Rio de Janeiro and the North-East.
- **By month:** option C has fewer late orders in 5 of 7 test months.
  - The biggest gain was in March 2018, during the disruption: 20.5% → 13.5% late.
  - In June and July it is about 0.3–0.4 points worse.

## What a shorter promise is worth
- This data cannot measure it, because customers turned away by a long promise never appear.
- In a field study at an online retailer, Cui, Lu, Sun & Golden (2024, *M&SOM*) found that each day of faster promise raised sales by about 0.73%. They also found more returns and lower retention when promises were over-aggressive.
- If that transferred to Olist, option B's 2.1 days would be worth roughly **+1.6% sales**. This is an assumption to test, not a result.

## Recommendation
1. **Replace the network-wide promise with a per-order model promise at a fixed quantile** (P92.5 matched Olist's reliability in January). In Feb–Aug this would have meant 28% fewer late orders and about 140 fewer 1-star reviews per 10,000 orders, for promises half a day longer on average.
2. **Choose the point on the frontier deliberately.** It ranges from A (same speed, fewer late orders) to B (same reliability, 2 days faster). The choice depends on the sales value of speed.
3. **Run an experiment before the rollout (Phase 5).** The review gain assumes the Phase 2 dose-response holds under a new policy, and the sales gain borrows another retailer's elasticity.

## Assumptions
- Reviews respond to arrival relative to the promise, not to promise length itself.
- The Phase 2 bucket effects carry over to a new promise policy.
- Delivery operations are unchanged; only the promise changes.
