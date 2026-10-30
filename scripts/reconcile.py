"""Reconcile the dbt warehouse against an independent pandas implementation.

The headline numbers are computed twice: once by the dbt models (SQL) and once here, directly from
the raw CSVs with pandas. If both implementations agree, a silent join or date bug in either one is
very unlikely.

    python scripts/reconcile.py                       # real data in data/raw, warehouse/olist.duckdb
    python scripts/reconcile.py --raw data/sample --db warehouse/ci.duckdb
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

END = pd.Timestamp("2018-08-31")
WINDOW = 180


def from_csvs(raw: Path) -> dict[str, float]:
    ts = ["order_purchase_timestamp", "order_delivered_carrier_date", "order_delivered_customer_date",
          "order_estimated_delivery_date"]
    o = pd.read_csv(raw / "olist_orders_dataset.csv", parse_dates=ts)
    c = pd.read_csv(raw / "olist_customers_dataset.csv")
    items = pd.read_csv(raw / "olist_order_items_dataset.csv", usecols=["order_id"])
    r = pd.read_csv(raw / "olist_order_reviews_dataset.csv", parse_dates=["review_creation_date",
                                                                          "review_answer_timestamp"])
    r = (r.sort_values(["order_id", "review_answer_timestamp", "review_id"], ascending=[True, False, True])
          .drop_duplicates("order_id"))

    f = o.merge(c, on="customer_id").merge(r[["order_id", "review_score"]], on="order_id", how="left")
    f["pdate"] = f.order_purchase_timestamp.dt.normalize()
    anomaly = ((f.order_delivered_carrier_date < f.order_purchase_timestamp)
               | (f.order_delivered_customer_date < f.order_delivered_carrier_date))
    f["eligible"] = ((f.order_status == "delivered") & f.order_delivered_customer_date.notna()
                     & f.order_id.isin(items.order_id) & ~anomaly & (f.pdate <= END))
    f["days_late"] = (f.order_delivered_customer_date.dt.normalize() - f.order_estimated_delivery_date).dt.days
    f["promised"] = (f.order_estimated_delivery_date - f.pdate).dt.days
    e = f[f.eligible]

    f["session"] = f.groupby("customer_unique_id").pdate.rank(method="dense").astype(int)
    first = f[f.session == 1].groupby("customer_unique_id").agg(first=("pdate", "min"), eligible=("eligible", "all"))
    second = f[f.session == 2].groupby("customer_unique_id").pdate.min().rename("second")
    first = first.join(second)
    first["repeat"] = (first.second - first["first"]).dt.days.le(WINDOW)
    cohort = first[(first["first"] <= END - pd.Timedelta(days=WINDOW)) & first.eligible]

    return {
        "orders": len(f),
        "eligible_orders": len(e),
        "late_rate": (e.days_late > 0).mean(),
        "avg_promised_days": e.promised.mean(),
        "avg_review_late": e[e.days_late > 0].review_score.mean(),
        "avg_review_on_time": e[e.days_late <= 0].review_score.mean(),
        "split_checkout_orders": int((f.groupby(["customer_unique_id", "pdate"]).order_id.transform("size") > 1).sum()),
        "cohort_customers": len(cohort),
        "repeat_rate": cohort.repeat.mean(),
    }


def from_warehouse(db: Path) -> dict[str, float]:
    con = duckdb.connect(str(db), read_only=True)
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    elig = "from marts.fct_orders where is_analysis_eligible"
    return {
        "orders": q("select count(*) from marts.fct_orders"),
        "eligible_orders": q(f"select count(*) {elig}"),
        "late_rate": q(f"select avg(is_late::int) {elig}"),
        "avg_promised_days": q(f"select avg(promised_days) {elig}"),
        "avg_review_late": q(f"select avg(review_score) {elig} and is_late"),
        "avg_review_on_time": q(f"select avg(review_score) {elig} and not is_late"),
        "split_checkout_orders": q("select count(*) from marts.fct_orders where is_split_checkout"),
        "cohort_customers": q("select count(*) from marts.fct_customer_first_purchase "
                              "where has_full_followup and first_session_eligible"),
        "repeat_rate": q("select avg(repeat_within_window::int) from marts.fct_customer_first_purchase "
                         "where has_full_followup and first_session_eligible"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--db", type=Path, default=Path("warehouse/olist.duckdb"))
    a = ap.parse_args()

    expected, actual = from_csvs(a.raw), from_warehouse(a.db)
    ok = True
    print(f"{'metric':24} {'pandas (raw CSVs)':>18} {'dbt warehouse':>15}")
    for k, v in expected.items():
        w = actual[k]
        match = abs(float(v) - float(w)) <= 1e-6 * max(1.0, abs(float(v)))
        ok &= match
        print(f"{k:24} {v:>18.4f} {w:>15.4f}  {'ok' if match else 'MISMATCH'}")
    print("\nreconciled: all metrics match" if ok else "\nMISMATCH: the implementations disagree")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
