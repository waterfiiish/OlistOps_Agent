from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.database.connection import psycopg_connect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "data" / "processed" / "data_quality_report.html"

CHECKS = {
    "row_counts": """
        SELECT 'orders' AS table_name, count(*) AS value FROM raw.orders
        UNION ALL SELECT 'order_items', count(*) FROM raw.order_items
        UNION ALL SELECT 'reviews', count(*) FROM raw.order_reviews
        UNION ALL SELECT 'customers', count(*) FROM raw.customers
        UNION ALL SELECT 'products', count(*) FROM raw.products
        UNION ALL SELECT 'sellers', count(*) FROM raw.sellers
        ORDER BY table_name
    """,
    "key_integrity": """
        SELECT 'duplicate_order_ids' AS check_name,
               count(*) - count(DISTINCT order_id) AS value
        FROM raw.orders
        UNION ALL
        SELECT 'duplicate_customer_ids',
               count(*) - count(DISTINCT customer_id)
        FROM raw.customers
        UNION ALL
        SELECT 'duplicate_product_ids',
               count(*) - count(DISTINCT product_id)
        FROM raw.products
        UNION ALL
        SELECT 'duplicate_seller_ids',
               count(*) - count(DISTINCT seller_id)
        FROM raw.sellers
        UNION ALL
        SELECT 'duplicate_review_ids',
               count(*) - count(DISTINCT review_id)
        FROM raw.order_reviews
        UNION ALL
        SELECT 'orphan_order_items', count(*)
        FROM raw.order_items i LEFT JOIN raw.orders o USING(order_id)
        WHERE o.order_id IS NULL
        UNION ALL
        SELECT 'orphan_reviews', count(*)
        FROM raw.order_reviews r LEFT JOIN raw.orders o USING(order_id)
        WHERE o.order_id IS NULL
        UNION ALL
        SELECT 'orphan_customer_orders', count(*)
        FROM raw.orders o LEFT JOIN raw.customers c USING(customer_id)
        WHERE c.customer_id IS NULL
    """,
    "time_quality": """
        SELECT 'approved_before_purchase' AS check_name, count(*) AS value
        FROM staging.stg_orders
        WHERE approved_at < purchased_at
        UNION ALL
        SELECT 'delivered_before_carrier', count(*)
        FROM staging.stg_orders
        WHERE delivered_at < carrier_at
        UNION ALL
        SELECT 'cancelled_with_delivery_date', count(*)
        FROM staging.stg_orders
        WHERE order_status IN ('canceled', 'unavailable') AND delivered_at IS NOT NULL
        UNION ALL
        SELECT 'delivered_missing_actual_date', count(*)
        FROM staging.stg_orders
        WHERE order_status = 'delivered' AND delivered_at IS NULL
    """,
    "missingness": """
        SELECT 'product_category_missing' AS check_name,
               count(*) FILTER (WHERE product_category_name IS NULL OR product_category_name = '')
               AS missing,
               count(*) AS total
        FROM raw.products
        UNION ALL
        SELECT 'product_weight_missing',
               count(*) FILTER (WHERE product_weight_g IS NULL OR product_weight_g = ''),
               count(*)
        FROM raw.products
        UNION ALL
        SELECT 'review_message_missing',
               count(*) FILTER (
                   WHERE review_comment_message IS NULL OR review_comment_message = ''
               ),
               count(*)
        FROM raw.order_reviews
    """,
    "aggregation_risk": """
        SELECT 'multi_item_orders' AS check_name, count(*) AS value
        FROM (
            SELECT order_id FROM raw.order_items GROUP BY order_id HAVING count(*) > 1
        ) x
        UNION ALL
        SELECT 'multi_seller_orders', count(*)
        FROM (
            SELECT order_id FROM raw.order_items
            GROUP BY order_id HAVING count(DISTINCT seller_id) > 1
        ) x
        UNION ALL
        SELECT 'payment_vs_items_abs_diff_over_1', count(*)
        FROM (
            SELECT
                o.order_id,
                abs(coalesce(p.payment_value, 0) -
                    coalesce(i.item_value + i.freight_value, 0)) AS difference
            FROM raw.orders o
            LEFT JOIN (
                SELECT order_id, sum(payment_value::numeric) AS payment_value
                FROM raw.order_payments GROUP BY order_id
            ) p USING(order_id)
            LEFT JOIN (
                SELECT
                    order_id,
                    sum(price::numeric) AS item_value,
                    sum(freight_value::numeric) AS freight_value
                FROM raw.order_items GROUP BY order_id
            ) i USING(order_id)
        ) x
        WHERE difference > 1
    """,
}


def _table(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"<h2>{html.escape(title)}</h2><p>No rows.</p>"
    columns = list(rows[0])
    head = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(row[column]))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    return (
        f"<h2>{html.escape(title)}</h2>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    )


def generate(output: Path = OUTPUT) -> None:
    sections = []
    with psycopg_connect() as connection:
        for name, sql in CHECKS.items():
            rows = [dict(row) for row in connection.execute(sql).fetchall()]
            sections.append(_table(name.replace("_", " ").title(), rows))
    generated = datetime.now(UTC).isoformat()
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>OlistOps Data Quality Report</title>
  <style>
    body {{ font: 15px/1.55 system-ui, sans-serif; margin: 2rem auto;
            max-width: 1100px; color: #172033; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
    th, td {{ border: 1px solid #d7deea; padding: .55rem .7rem; text-align: left; }}
    th {{ background: #eef4ff; }}
    .note {{ background: #fff8e8; border-left: 4px solid #f0a128; padding: 1rem; }}
  </style>
</head>
<body>
  <h1>OlistOps 数据质量报告</h1>
  <p>生成时间（UTC）：{html.escape(generated)}</p>
  <p class="note">所有 RAW CSV 保持只读；指标工具仅查询 MART。
  多商品、多卖家订单必须先聚合到目标粒度。</p>
  {''.join(sections)}
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    generate()
