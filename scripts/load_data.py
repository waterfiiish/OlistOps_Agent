from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import psycopg

from packages.database.connection import psycopg_connect
from packages.database.migrations import apply_migrations

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

TABLES: dict[str, tuple[str, list[str]]] = {
    "olist_customers_dataset.csv": (
        "raw.customers",
        [
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ],
    ),
    "olist_geolocation_dataset.csv": (
        "raw.geolocation",
        [
            "geolocation_zip_code_prefix",
            "geolocation_lat",
            "geolocation_lng",
            "geolocation_city",
            "geolocation_state",
        ],
    ),
    "olist_orders_dataset.csv": (
        "raw.orders",
        [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    ),
    "olist_order_items_dataset.csv": (
        "raw.order_items",
        [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ],
    ),
    "olist_order_payments_dataset.csv": (
        "raw.order_payments",
        [
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
        ],
    ),
    "olist_order_reviews_dataset.csv": (
        "raw.order_reviews",
        [
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ],
    ),
    "olist_products_dataset.csv": (
        "raw.products",
        [
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
    ),
    "olist_sellers_dataset.csv": (
        "raw.sellers",
        ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
    ),
    "product_category_name_translation.csv": (
        "raw.category_translation",
        ["product_category_name", "product_category_name_english"],
    ),
}


def execute_sql(connection: psycopg.Connection, path: Path) -> None:
    print(f"Applying {path.relative_to(PROJECT_ROOT)}")
    connection.execute(path.read_text(encoding="utf-8"))
    connection.commit()


def copy_csv(
    connection: psycopg.Connection,
    csv_path: Path,
    table: str,
    columns: list[str],
) -> int:
    column_list = ", ".join(columns)
    connection.execute(f"TRUNCATE TABLE {table}")
    copy_sql = (
        f"COPY {table} ({column_list}) FROM STDIN "
        "WITH (FORMAT CSV, HEADER true, ENCODING 'UTF8')"
    )
    with (
        csv_path.open("r", encoding="utf-8", newline="") as source,
        connection.cursor().copy(copy_sql) as copy,
    ):
        while chunk := source.read(1024 * 1024):
            copy.write(chunk)
    count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()["count"]
    connection.commit()
    return int(count)


def load(raw_dir: Path) -> None:
    missing = [filename for filename in TABLES if not (raw_dir / filename).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing Olist CSV files: {missing}. Run scripts/download_olist.py first."
        )
    with psycopg_connect() as connection:
        apply_migrations(connection)
        for filename, (table, columns) in TABLES.items():
            started = time.monotonic()
            count = copy_csv(connection, raw_dir / filename, table, columns)
            elapsed = time.monotonic() - started
            print(f"Loaded {table}: {count:,} rows in {elapsed:.1f}s")
        execute_sql(connection, PROJECT_ROOT / "db" / "staging" / "create_staging.sql")
        execute_sql(connection, PROJECT_ROOT / "db" / "marts" / "refresh_marts.sql")
    print("RAW, STAGING and MART layers are ready.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Olist CSV data into PostgreSQL")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()
    try:
        load(args.raw_dir.resolve())
    except (FileNotFoundError, psycopg.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
