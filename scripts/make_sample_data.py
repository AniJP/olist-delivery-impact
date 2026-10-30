"""Write a small synthetic Olist-format dataset (same 9 files, same columns) for CI and quick runs.

The real data comes from Kaggle and isn't committed. This sample mimics its structure and the
patterns the project studies: padded delivery estimates, ~7% late orders, reviews that collapse when
an order is late, split checkouts (several orders from one checkout) and a few repeat customers.

    python scripts/make_sample_data.py            # -> data/sample/
    python scripts/make_sample_data.py --orders 2000 --out data/sample
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
from datetime import datetime, timedelta
from pathlib import Path

STATES = {  # state: (lat, lng, zip prefix base)
    "SP": (-23.55, -46.63, 1000), "RJ": (-22.91, -43.17, 20000), "MG": (-19.92, -43.94, 30000),
    "RS": (-30.03, -51.23, 90000), "PR": (-25.43, -49.27, 80000), "BA": (-12.97, -38.50, 40000),
}
CATEGORIES = [("cama_mesa_banho", "bed_bath_table"), ("beleza_saude", "health_beauty"),
              ("esporte_lazer", "sports_leisure"), ("informatica_acessorios", "computers_accessories"),
              ("pc_gamer", None)]  # pc_gamer is missing from the real translation file too


def hid(*parts) -> str:
    return hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()


def ts(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S")


def write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main(n_orders: int, out: Path, seed: int) -> None:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)

    # sellers, products, geolocation
    sellers = []
    for i in range(40):
        st = rng.choice(list(STATES))
        sellers.append((hid("seller", i), STATES[st][2] + rng.randint(0, 50), f"city_{st.lower()}", st))
    products = []
    for i in range(150):
        cat_pt, _ = rng.choice(CATEGORIES)
        products.append((hid("product", i), cat_pt, rng.randint(20, 60), rng.randint(100, 2000), rng.randint(1, 5),
                         rng.randint(100, 15000), rng.randint(10, 60), rng.randint(5, 40), rng.randint(10, 40)))
    geo = []
    for st, (lat, lng, base) in STATES.items():
        for z in range(base, base + 51):
            for _ in range(3):
                geo.append((z, lat + rng.uniform(-0.3, 0.3), lng + rng.uniform(-0.3, 0.3), f"city_{st.lower()}", st))
    geo.append((STATES["SP"][2], 45.06, 7.62, "bad_geocode", "SP"))  # an out-of-Brazil point, as in the real data

    # customers (people) and their orders
    people = [hid("person", i) for i in range(int(n_orders * 0.9))]
    orders, customers, items, payments, reviews = [], [], [], [], []
    start = datetime(2017, 1, 5, 9, 0)
    k = 0
    while len(orders) < n_orders:
        person = people[k % len(people)]
        k += 1
        st = rng.choice(list(STATES))
        zip_prefix = STATES[st][2] + rng.randint(0, 50)
        purchased = start + timedelta(days=rng.randint(0, 590), minutes=rng.randint(0, 1400))
        n_in_checkout = 2 if rng.random() < 0.03 else 1          # split checkout
        visits = [purchased] + ([purchased + timedelta(days=rng.randint(20, 150))] if rng.random() < 0.04 else [])
        for visit in visits:
            for split in range(n_in_checkout):
                if len(orders) >= n_orders:
                    break
                oid = hid("order", len(orders))
                cid = hid("customer", len(orders))
                customers.append([cid, person, zip_prefix, f"city_{st.lower()}", st])
                at = visit + timedelta(minutes=split)
                promised = rng.randint(14, 35)
                estimated = (at + timedelta(days=promised)).replace(hour=0, minute=0, second=0)
                status = rng.choices(["delivered", "canceled", "unavailable", "shipped"], [96, 1.5, 1, 1.5])[0]
                late = rng.random() < 0.07
                actual = promised + rng.randint(1, 15) if late else max(2, promised - rng.randint(3, 20))
                delivered = at + timedelta(days=actual, hours=rng.randint(0, 20))
                shipped = at + timedelta(days=rng.uniform(0.5, 4))
                if len(orders) == 7:  # one carrier timestamp before purchase, like 166 real orders
                    shipped = at - timedelta(hours=5)
                row = [oid, cid, status, ts(at), ts(at + timedelta(minutes=20)),
                       ts(shipped) if status in ("delivered", "shipped") else "",
                       ts(delivered) if status == "delivered" else "", ts(estimated)]
                orders.append(row)
                if status == "unavailable":
                    continue  # like the real data: unavailable orders have no items
                total = 0.0
                seller = rng.choice(sellers)
                for item_no in range(1, rng.choice([1, 1, 1, 1, 2, 3]) + 1):
                    prod = rng.choice(products)
                    price, freight = round(rng.uniform(15, 400), 2), round(rng.uniform(5, 45), 2)
                    total += price + freight
                    items.append([oid, item_no, prod[0], seller[0], ts(at + timedelta(days=5)), price, freight])
                payments.append([oid, 1, rng.choice(["credit_card", "credit_card", "boleto", "voucher"]),
                                 rng.randint(1, 10), round(total, 2)])
                if status == "delivered":
                    days_late = (delivered.date() - estimated.date()).days
                    if days_late > 0:
                        score = rng.choices([1, 2, 3, 4, 5], [55, 12, 13, 10, 10])[0]
                        created = estimated + timedelta(days=1)  # survey sent before the late package arrives
                    else:
                        score = rng.choices([1, 2, 3, 4, 5], [6, 3, 8, 20, 63])[0]
                        created = delivered.replace(hour=0, minute=0, second=0) + timedelta(days=1)
                    comment = rng.choice(["", "", "chegou antes do prazo", "produto ainda nao chegou"])
                    reviews.append([hid("review", oid), oid, score, "", comment, ts(created),
                                    ts(created + timedelta(hours=rng.randint(2, 60)))])

    write(out / "olist_orders_dataset.csv",
          ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
           "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"],
          orders)
    write(out / "olist_customers_dataset.csv",
          ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
          customers)
    write(out / "olist_order_items_dataset.csv",
          ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
          items)
    write(out / "olist_order_payments_dataset.csv",
          ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"], payments)
    write(out / "olist_order_reviews_dataset.csv",
          ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
           "review_creation_date", "review_answer_timestamp"], reviews)
    write(out / "olist_products_dataset.csv",
          ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
           "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
          [list(p) for p in products])
    write(out / "olist_sellers_dataset.csv",
          ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"], [list(s) for s in sellers])
    write(out / "olist_geolocation_dataset.csv",
          ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city",
           "geolocation_state"], [list(g) for g in geo])
    write(out / "product_category_name_translation.csv", ["product_category_name", "product_category_name_english"],
          [[pt, en] for pt, en in CATEGORIES if en])
    print(f"wrote {len(orders)} orders, {len(items)} items, {len(reviews)} reviews to {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--orders", type=int, default=1500)
    ap.add_argument("--out", type=Path, default=Path("data/sample"))
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    main(a.orders, a.out, a.seed)
