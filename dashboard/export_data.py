"""Export the small, aggregated tables the dashboard reads.

The dashboard never touches order-level data, so it can run (and be deployed) from these files
alone. Re-run after `make build` and `make notebooks`:

    python dashboard/export_data.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import causal as C  # noqa: E402
import policy as Y  # noqa: E402

OUT = ROOT / "dashboard" / "data"
DEPLOY_QUANTILE = 0.925  # Phase 4 option C: chosen on January 2018 to match Olist's late rate


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    db = str(ROOT / "warehouse" / "olist.duckdb")

    # Phase 2: cost of lateness
    orders = C.load_orders(db)
    stars = C.dose_response(orders, "review_score")
    one = C.dose_response(orders, "one_star")
    dose = stars[["bucket", "effect", "ci_low", "ci_high", "n"]].merge(
        one[["bucket", "effect"]].rename(columns={"effect": "one_star_effect"}), on="bucket"
    )
    dose.to_csv(OUT / "dose_response.csv", index=False)
    shutil.copy(ROOT / "docs" / "phase2_estimates.csv", OUT / "phase2_estimates.csv")

    # Phase 3 / 4: policies on the Feb-Aug 2018 test period
    preds = pd.read_parquet(ROOT / "warehouse" / "phase3_predictions.parquet")
    test = preds[preds.split == "test"].reset_index(drop=True)
    cdf = Y.cdf_grid(test)
    model_promise = Y.uniform_quantile(cdf, DEPLOY_QUANTILE)
    t = test.assign(
        month=test.purchase_date.dt.strftime("%Y-%m"),
        model_promise=model_promise,
        olist_late=Y.days_late(test.promised_days.to_numpy(float), test) > 0,
        model_late=Y.days_late(model_promise, test) > 0,
    )
    agg = {
        "orders": ("order_id", "size"),
        "olist_promise": ("promised_days", "mean"),
        "model_promise": ("model_promise", "mean"),
        "olist_late": ("olist_late", "mean"),
        "model_late": ("model_late", "mean"),
    }
    t.groupby("customer_state").agg(**agg).reset_index().to_csv(OUT / "by_state.csv", index=False)
    t.groupby("month").agg(**agg).reset_index().to_csv(OUT / "by_month.csv", index=False)

    shutil.copy(ROOT / "docs" / "phase4_frontier.csv", OUT / "frontier.csv")
    shutil.copy(ROOT / "docs" / "phase4_options.csv", OUT / "options.csv")
    shutil.copy(ROOT / "docs" / "phase3_coverage.csv", OUT / "coverage.csv")
    shutil.copy(ROOT / "docs" / "phase5_sample_sizes.csv", OUT / "sample_sizes.csv")

    summary = pd.DataFrame(
        {
            "metric": ["test_orders", "deploy_quantile", "reviewed_orders", "review_sd", "one_star_rate"],
            "value": [
                len(test),
                DEPLOY_QUANTILE,
                len(orders),
                float(orders.review_score.std()),
                float(np.mean(orders.review_score == 1)),
            ],
        }
    )
    summary.to_csv(OUT / "summary.csv", index=False)
    print(f"wrote {len(list(OUT.glob('*.csv')))} files to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
