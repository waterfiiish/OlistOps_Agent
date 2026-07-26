DROP MATERIALIZED VIEW IF EXISTS mart.mart_seller_performance_monthly CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mart.mart_category_performance_monthly CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mart.mart_payment_analysis_base CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mart.mart_review_analysis_base CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mart.mart_seller_order_fulfillment CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mart.mart_category_order_fulfillment CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mart.mart_order_fulfillment CASCADE;

CREATE MATERIALIZED VIEW mart.mart_order_fulfillment AS
WITH item_agg AS (
    SELECT
        order_id,
        count(*) AS item_count,
        count(DISTINCT seller_id) AS seller_count,
        sum(price) AS item_value,
        sum(freight_value) AS freight_value
    FROM staging.stg_order_items
    GROUP BY order_id
),
payment_agg AS (
    SELECT
        order_id,
        sum(payment_value) AS payment_value,
        max(payment_installments) AS max_installments
    FROM staging.stg_order_payments
    GROUP BY order_id
),
review_agg AS (
    SELECT
        order_id,
        avg(review_score)::numeric(5, 2) AS review_score,
        string_agg(review_comment_title, ' | ' ORDER BY review_created_at)
            FILTER (WHERE review_comment_title IS NOT NULL) AS review_titles,
        string_agg(review_comment_message, E'\n---\n' ORDER BY review_created_at)
            FILTER (WHERE review_comment_message IS NOT NULL) AS review_messages,
        min(review_created_at) AS first_review_at
    FROM staging.stg_reviews
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    c.customer_city,
    c.customer_state,
    o.order_status,
    o.purchased_at,
    o.approved_at,
    o.carrier_at,
    o.delivered_at,
    o.estimated_at,
    CASE
        WHEN o.delivered_at IS NULL OR o.estimated_at IS NULL THEN NULL
        ELSE o.delivered_at > o.estimated_at
    END AS is_late,
    CASE
        WHEN o.delivered_at > o.estimated_at
        THEN EXTRACT(EPOCH FROM (o.delivered_at - o.estimated_at)) / 86400.0
        ELSE 0
    END::numeric(10, 3) AS late_days,
    CASE
        WHEN o.delivered_at IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (o.delivered_at - o.purchased_at)) / 86400.0
    END::numeric(10, 3) AS delivery_days,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(i.seller_count, 0) AS seller_count,
    COALESCE(i.item_value, 0)::numeric(14, 2) AS item_value,
    COALESCE(i.freight_value, 0)::numeric(14, 2) AS freight_value,
    p.payment_value,
    p.max_installments,
    r.review_score,
    r.review_titles,
    r.review_messages,
    r.first_review_at
FROM staging.stg_orders o
LEFT JOIN staging.stg_customers c USING (customer_id)
LEFT JOIN item_agg i USING (order_id)
LEFT JOIN payment_agg p USING (order_id)
LEFT JOIN review_agg r USING (order_id);

CREATE UNIQUE INDEX ux_mart_order_fulfillment_order
    ON mart.mart_order_fulfillment(order_id);
CREATE INDEX ix_mart_order_fulfillment_purchase
    ON mart.mart_order_fulfillment(purchased_at);

CREATE MATERIALIZED VIEW mart.mart_seller_order_fulfillment AS
WITH seller_items AS (
    SELECT
        i.order_id,
        i.seller_id,
        count(*) AS item_count,
        sum(i.price) AS item_value,
        sum(i.freight_value) AS freight_value,
        min(i.shipping_limit_at) AS first_shipping_limit_at,
        max(i.shipping_limit_at) AS last_shipping_limit_at
    FROM staging.stg_order_items i
    GROUP BY i.order_id, i.seller_id
)
SELECT
    s.order_id,
    s.seller_id,
    se.seller_city,
    se.seller_state,
    o.order_status,
    o.purchased_at,
    o.delivered_at,
    o.estimated_at,
    o.is_late,
    o.late_days,
    o.review_score,
    s.item_count,
    s.item_value,
    s.freight_value,
    s.first_shipping_limit_at,
    s.last_shipping_limit_at
FROM seller_items s
JOIN mart.mart_order_fulfillment o USING (order_id)
LEFT JOIN staging.stg_sellers se USING (seller_id);

CREATE UNIQUE INDEX ux_mart_seller_order
    ON mart.mart_seller_order_fulfillment(order_id, seller_id);
CREATE INDEX ix_mart_seller_purchase
    ON mart.mart_seller_order_fulfillment(purchased_at);
CREATE INDEX ix_mart_seller_id
    ON mart.mart_seller_order_fulfillment(seller_id);

CREATE MATERIALIZED VIEW mart.mart_category_order_fulfillment AS
WITH category_items AS (
    SELECT
        i.order_id,
        p.category,
        count(*) AS item_count,
        sum(i.price) AS item_value,
        sum(i.freight_value) AS freight_value
    FROM staging.stg_order_items i
    LEFT JOIN staging.stg_products p USING (product_id)
    GROUP BY i.order_id, p.category
)
SELECT
    c.order_id,
    COALESCE(c.category, 'unknown') AS category,
    o.order_status,
    o.purchased_at,
    o.delivered_at,
    o.estimated_at,
    o.is_late,
    o.late_days,
    o.review_score,
    c.item_count,
    c.item_value,
    c.freight_value
FROM category_items c
JOIN mart.mart_order_fulfillment o USING (order_id);

CREATE UNIQUE INDEX ux_mart_category_order
    ON mart.mart_category_order_fulfillment(order_id, category);
CREATE INDEX ix_mart_category_purchase
    ON mart.mart_category_order_fulfillment(purchased_at);

CREATE MATERIALIZED VIEW mart.mart_review_analysis_base AS
SELECT
    r.review_id,
    r.order_id,
    r.review_score,
    r.review_comment_title,
    r.review_comment_message,
    r.review_created_at,
    o.purchased_at,
    o.order_status,
    o.is_late,
    o.late_days,
    o.delivery_days
FROM staging.stg_reviews r
JOIN mart.mart_order_fulfillment o USING (order_id);

-- The public dataset contains a small number of repeated review_id values.
-- Keep source rows intact and index review_id non-uniquely instead of inventing a key.
CREATE INDEX ix_mart_review_id
    ON mart.mart_review_analysis_base(review_id);
CREATE INDEX ix_mart_review_score
    ON mart.mart_review_analysis_base(review_score);

CREATE MATERIALIZED VIEW mart.mart_payment_analysis_base AS
WITH payment_by_order_type AS (
    SELECT
        order_id,
        COALESCE(payment_type, 'unknown') AS payment_type,
        sum(payment_value)::numeric(14, 2) AS payment_value,
        max(payment_installments) AS max_installments,
        count(*) AS payment_sequence_count
    FROM staging.stg_order_payments
    GROUP BY order_id, COALESCE(payment_type, 'unknown')
)
SELECT
    p.order_id,
    p.payment_type,
    p.payment_value,
    p.max_installments,
    p.payment_sequence_count,
    o.purchased_at,
    o.order_status,
    o.customer_state,
    o.item_value,
    o.freight_value,
    o.is_late,
    o.review_score
FROM payment_by_order_type p
JOIN mart.mart_order_fulfillment o USING (order_id);

CREATE UNIQUE INDEX ux_mart_payment_order_type
    ON mart.mart_payment_analysis_base(order_id, payment_type);
CREATE INDEX ix_mart_payment_purchase
    ON mart.mart_payment_analysis_base(purchased_at);
CREATE INDEX ix_mart_payment_type
    ON mart.mart_payment_analysis_base(payment_type);

CREATE MATERIALIZED VIEW mart.mart_seller_performance_monthly AS
SELECT
    date_trunc('month', purchased_at)::date AS month,
    seller_id,
    count(DISTINCT order_id) AS order_count,
    sum(item_value)::numeric(16, 2) AS item_value,
    sum(freight_value)::numeric(16, 2) AS freight_value,
    count(*) FILTER (WHERE is_late IS NOT NULL) AS eligible_delivery_count,
    count(*) FILTER (WHERE is_late) AS late_order_count,
    avg(is_late::integer) FILTER (WHERE is_late IS NOT NULL)::numeric(8, 5) AS late_rate,
    avg(late_days) FILTER (WHERE is_late)::numeric(10, 3) AS avg_late_days,
    avg(review_score)::numeric(5, 2) AS avg_review_score
FROM mart.mart_seller_order_fulfillment
GROUP BY date_trunc('month', purchased_at)::date, seller_id;

CREATE UNIQUE INDEX ux_mart_seller_month
    ON mart.mart_seller_performance_monthly(month, seller_id);

CREATE MATERIALIZED VIEW mart.mart_category_performance_monthly AS
SELECT
    date_trunc('month', purchased_at)::date AS month,
    category,
    count(DISTINCT order_id) AS order_count,
    sum(item_value)::numeric(16, 2) AS item_value,
    sum(freight_value)::numeric(16, 2) AS freight_value,
    count(*) FILTER (WHERE is_late IS NOT NULL) AS eligible_delivery_count,
    count(*) FILTER (WHERE is_late) AS late_order_count,
    avg(is_late::integer) FILTER (WHERE is_late IS NOT NULL)::numeric(8, 5) AS late_rate,
    avg(late_days) FILTER (WHERE is_late)::numeric(10, 3) AS avg_late_days,
    avg(review_score)::numeric(5, 2) AS avg_review_score
FROM mart.mart_category_order_fulfillment
GROUP BY date_trunc('month', purchased_at)::date, category;

CREATE UNIQUE INDEX ux_mart_category_month
    ON mart.mart_category_performance_monthly(month, category);
