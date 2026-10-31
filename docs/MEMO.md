# Memo: Setting delivery promises per order

**To:** Head of Marketplace Operations · **Re:** Delivery-date promises · **Basis:** 96k Olist orders, 2016–2018

## The problem
Olist promises a median of 24 days for deliveries that take 10. The padding still doesn't stop 7% of orders arriving late. In the 2018 test period that rose to 9%, and peaked at 20% in March during a carrier disruption.

## What we found

**1. A missed promise costs about 2 stars.**
- Late orders score 1.99 stars lower than comparable on-time orders.
- They are 47 percentage points more likely to get a 1-star review.
- The estimate holds across five methods, within the same seller, and with seasonality removed. A placebo with shuffled lateness gives zero.

**2. Customers barely reward slack.**
- Each extra week of arriving early is worth about 0.16 stars, against −2 stars for missing the date.
- Three quarters of late orders are reviewed before they arrive, because the survey goes out on the promised date.

**3. A model predicts each order's delivery time well enough to set its promise.**
- It is trained on 2017 and tested on Feb–Aug 2018.
- Promises set at its 90th and 95th percentiles were kept 91.8% and 95.6% of the time.

**4. Per-order promises beat a network-wide rule.** Over Feb–Aug 2018:

| Policy | Late deliveries | Average promise | 1-star reviews per 10k orders |
|---|---|---|---|
| Olist today | 9.0% | 22.9 days | baseline |
| **Model P92.5 (chosen in Jan, run unchanged)** | **6.5%** | 23.5 days | **−141** |
| Model, same promise length | 6.9% | 22.9 days | −112 |
| Model, same late rate | 9.1% | 20.8 days | ≈ 0 |

The gain comes from moving padding, not adding it:
- **São Paulo (44% of orders):** promises get 1.7 days shorter with no extra late orders.
- **Rio de Janeiro and Bahia:** promises get a few days longer, and their late rates roughly halve.

## Recommendation
1. **Replace the network-wide promise with the model's per-order P92.5 promise**, after the experiment below confirms it.
2. **Refresh the model's calibration weekly and alert on the live late rate.** No model anticipated the Feb–Mar 2018 disruption, and promises have to widen as soon as deliveries slow down.
3. **Test holding the review survey until delivery.** This is a separate, cheap experiment.

## Before rolling out: a 3-arm experiment
- **Arms:** Control, Reliable (P92.5), and Fast (about 2 days shorter at today's late rate). Customers are randomised individually and only the promise changes.
- **Reliability effect:** the drop in late deliveries shows up in 2–4 weeks. The 1-star effect needs about 7,100 reviewed orders per arm, roughly 2–3 months at this volume.
- **Sales effect of shorter promises:** published evidence suggests about +0.7% sales per day faster (Cui et al., 2024). That would make the Fast arm worth about +1.6%, but measuring it needs visitor-level traffic data. A regional test cannot detect it.
- **Repeat purchases:** read from a 10% holdout kept for 12 months.
- **Decision rule:**
  - Ship Reliable if 1-star reviews fall and conversion is not more than 1% worse.
  - Ship Fast only if conversion rises and lateness stays within 1 point of control.

## Risks and assumptions
- **Reviews:** the projection assumes they respond to the new promises the way they did to Olist's. The experiment tests exactly this.
- **Sales:** the value of shorter promises comes from another retailer and is unverified for Olist.
- **Under-promising:** about half of orders would get longer promises. Customers may react to seeing a later date even if it is met, which the conversion metric captures.
- **Undelivered orders:** about 1% of orders are never delivered, so no promise policy can exceed about 99% on time.

*Details: [README](../README.md) · Phase write-ups in [`docs/`](.) · Dashboard: `streamlit run dashboard/app.py`*
