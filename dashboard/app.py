"""Delivery-promise dashboard: what lateness costs, what better promises buy, and how to test it.

Runs entirely from the small aggregated CSVs in dashboard/data (no order-level data needed):

    streamlit run dashboard/app.py
"""

from __future__ import annotations

from pathlib import Path
from statistics import NormalDist

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent / "data"
BLUE, ORANGE, INK2, GRID = "#2a78d6", "#eb6834", "#52514e", "#e4e3df"

st.set_page_config(page_title="Delivery promises · Olist", layout="wide")


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name)


frontier = load("frontier.csv")
options = load("options.csv").set_index("option")
by_state = load("by_state.csv")
by_month = load("by_month.csv")
dose = load("dose_response.csv")
summary = load("summary.csv").set_index("metric")["value"]
sizes = load("sample_sizes.csv").set_index("question")

olist = options.loc["Olist today"]
deploy = options.iloc[3]

# --------------------------------------------------------------------------- header

st.title("How should a marketplace set delivery promises?")
st.caption(
    "Olist orders, Brazil 2016–2018. Policies are evaluated out of time on Feb–Aug 2018 "
    f"({int(summary['test_orders']):,} orders); orders never delivered count as late."
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Cost of a late delivery", "−2.0 stars", help="Doubly robust estimate, Phase 2")
k2.metric(
    "Late deliveries",
    f"{deploy['late rate']:.1%}",
    f"{(deploy['late rate'] - olist['late rate']) * 100:+.1f} pts vs Olist",
    delta_color="inverse",
)
k3.metric(
    "Average promise",
    f"{deploy['avg promise (days)']:.1f} days",
    f"{deploy['avg promise (days)'] - olist['avg promise (days)']:+.1f} vs Olist",
    delta_color="off",
)
k4.metric("1-star reviews avoided", f"{deploy['1-star reviews avoided']:.0f}", "per 10,000 orders")
st.caption(
    f"Recommended policy: model promise at P{summary['deploy_quantile'] * 100:g}, chosen in January 2018 to match "
    "Olist's reliability and run unchanged through August."
)

tab_cost, tab_frontier, tab_where, tab_test = st.tabs(
    ["What lateness costs", "Choose a policy", "Where it helps", "Test it"]
)

# --------------------------------------------------------------------------- cost of lateness

with tab_cost:
    st.subheader("Missing the promise is what hurts, not a slow delivery")
    d = dose.assign(label=dose.bucket.str.split(". ", n=1).str[1], late=dose.bucket.str.contains("late"))
    bars = (
        alt.Chart(d)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("label:N", sort=list(d.label), title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("effect:Q", title="stars vs arriving 1–7 days early"),
            color=alt.condition("datum.late", alt.value(ORANGE), alt.value(BLUE)),
            tooltip=[
                alt.Tooltip("label:N", title="arrival"),
                alt.Tooltip("effect:Q", title="stars", format="+.2f"),
                alt.Tooltip("one_star_effect:Q", title="1-star probability", format="+.1%"),
                alt.Tooltip("n:Q", title="orders", format=","),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(bars, use_container_width=True)
    st.markdown(
        "- Each extra week of arriving early is worth about **+0.16 stars**; 4+ days late costs **2.0–2.4**.\n"
        "- Five estimators (regression, seller fixed effects, propensity weighting, doubly robust ML) agree "
        "within 0.08 stars, and a placebo with shuffled lateness gives zero.\n"
        "- 74% of late orders are reviewed **before** they arrive: the survey goes out around the promised date."
    )

# --------------------------------------------------------------------------- frontier

with tab_frontier:
    st.subheader("Same reliability with shorter promises, or fewer late orders at the same length")
    q = st.slider("Model promise quantile", 0.80, 0.975, float(summary["deploy_quantile"]), 0.005, format="%.3f")
    f = frontier[frontier.policy == "model, same quantile"].copy()
    row = f.iloc[(f.param - q).abs().argmin()]

    c1, c2, c3 = st.columns(3)
    c1.metric("Late rate", f"{row.late_rate:.1%}", f"{(row.late_rate - olist['late rate']) * 100:+.1f} pts vs Olist",
              delta_color="inverse")
    c2.metric("Average promise", f"{row.avg_promise_days:.1f} days",
              f"{row.avg_promise_days - olist['avg promise (days)']:+.1f} vs Olist", delta_color="off")
    c3.metric("Average review effect", f"{row.avg_review_effect:+.3f} stars",
              f"{row.avg_review_effect - olist['review effect (stars)']:+.3f} vs Olist")

    shown = frontier[frontier.policy.isin(["Olist promise shifted", "model, same quantile"])]
    shown = shown[shown.late_rate.between(0.03, 0.16)]
    lines = (
        alt.Chart(shown)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("late_rate:Q", title="share of orders late", axis=alt.Axis(format="%")),
            y=alt.Y("avg_promise_days:Q", title="average promise (days)", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "policy:N",
                scale=alt.Scale(domain=["Olist promise shifted", "model, same quantile"], range=[INK2, BLUE]),
                legend=alt.Legend(orient="top-right", title=None),
            ),
            tooltip=[
                "policy:N",
                alt.Tooltip("param:Q", title="shift (days) / quantile"),
                alt.Tooltip("late_rate:Q", format=".1%"),
                alt.Tooltip("avg_promise_days:Q", format=".1f"),
            ],
        )
    )
    points = pd.DataFrame(
        [
            {"label": "Olist today", "late_rate": olist["late rate"], "avg_promise_days": olist["avg promise (days)"]},
            {"label": f"selected P{q * 100:.1f}", "late_rate": row.late_rate, "avg_promise_days": row.avg_promise_days},
        ]
    )
    dots = (
        alt.Chart(points)
        .mark_point(filled=True, size=140, color="black")
        .encode(x="late_rate:Q", y="avg_promise_days:Q", tooltip=["label:N"])
    )
    labels = dots.mark_text(align="left", dx=10, dy=-8).encode(text="label:N")
    st.altair_chart((lines + dots + labels).properties(height=380), use_container_width=True)
    st.caption(
        "Shifting Olist's promises moves along the grey line; the model's curve is lower everywhere in the "
        "useful range. A cost-aware per-order optimiser was indistinguishable from a single quantile."
    )

# --------------------------------------------------------------------------- where

with tab_where:
    st.subheader("Slack moves from where it is wasted to where it is missing")
    min_orders = st.slider("Show states with at least this many orders", 50, 2000, 300, 50)
    s = by_state[by_state.orders >= min_orders].copy()
    long = pd.concat(
        [
            s.assign(who="Olist", promise=s.olist_promise, late=s.olist_late),
            s.assign(who="Model", promise=s.model_promise, late=s.model_late),
        ]
    )
    order = list(s.sort_values("olist_late").customer_state)
    color = alt.Color("who:N", scale=alt.Scale(domain=["Olist", "Model"], range=[INK2, BLUE]), title=None)
    base = alt.Chart(long).encode(y=alt.Y("customer_state:N", sort=order, title=None), color=color)
    tip = ["customer_state:N", "who:N", alt.Tooltip("orders:Q", format=","),
           alt.Tooltip("promise:Q", format=".1f"), alt.Tooltip("late:Q", format=".1%")]
    left = base.mark_circle(size=90).encode(x=alt.X("promise:Q", title="average promise (days)",
                                                    scale=alt.Scale(zero=False)), tooltip=tip)
    right = base.mark_circle(size=90).encode(x=alt.X("late:Q", title="late rate", axis=alt.Axis(format="%")),
                                             tooltip=tip)
    st.altair_chart(alt.hconcat(left.properties(width=380, height=420), right.properties(width=380, height=420)))
    st.markdown(
        "São Paulo (44% of orders) gets shorter promises at the same late rate; Rio de Janeiro and the North-East "
        "get a few more days and roughly half the late deliveries."
    )
    m = by_month.melt(id_vars="month", value_vars=["olist_late", "model_late"], var_name="who", value_name="late")
    m["who"] = m.who.map({"olist_late": "Olist", "model_late": "Model"})
    st.altair_chart(
        alt.Chart(m)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("month:N", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("late:Q", title="late rate", axis=alt.Axis(format="%")),
            color=color,
            tooltip=["month:N", "who:N", alt.Tooltip("late:Q", format=".1%")],
        )
        .properties(height=260, title="By month: the biggest gain is during the Feb–Mar 2018 disruption"),
        use_container_width=True,
    )

# --------------------------------------------------------------------------- experiment

with tab_test:
    st.subheader("Experiment sizing")
    st.markdown(
        "Three arms randomised by customer: **Control** (Olist's promise), **Reliable** (model P92.5), "
        "**Fast** (about 2 days shorter at today's late rate). Full plan: `docs/PHASE5_EXPERIMENT_PLAN.md`."
    )
    c1, c2, c3 = st.columns(3)
    one_star = sizes.loc["1-star rate falls (Reliable)"]
    base_rate = c1.number_input("Baseline rate", 0.001, 0.9, round(float(one_star.baseline), 3), 0.005, format="%.3f")
    change = c2.number_input("Absolute change to detect", -0.2, 0.2, round(float(one_star.effect), 3), 0.001,
                             format="%.3f")
    monthly = c3.number_input("Eligible units per month", 100, 10_000_000, 6700, 100)
    alpha, power = 0.05, 0.8
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    p1 = min(max(base_rate + change, 1e-6), 1 - 1e-6)
    n = z**2 * (base_rate * (1 - base_rate) + p1 * (1 - p1)) / change**2 if change else float("inf")
    r1, r2, r3 = st.columns(3)
    r1.metric("Units per arm", f"{n:,.0f}")
    r2.metric("Months with 2 arms", f"{2 * n / monthly:,.1f}")
    r3.metric("Months with 3 arms", f"{3 * n / monthly:,.1f}")
    st.caption(
        "Defaults: 1-star review rate (Feb–Aug 2018) and the effect Phase 4 expects from Reliable, at this "
        "dataset's order volume. Validated on real "
        "orders with A/A splits (6–7% false positives) and a replay of real deliveries against each arm's promise."
    )

st.divider()
st.caption(
    "Data: Brazilian E-Commerce Public Dataset by Olist (CC BY-NC-SA 4.0). Code, notebooks and write-ups: "
    "see the repository README."
)
