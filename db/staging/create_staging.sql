DROP VIEW IF EXISTS staging.stg_orders CASCADE;
CREATE VIEW staging.stg_orders AS
SELECT
    order_id,
    customer_id,
    NULLIF(order_status, '') AS order_status,
    NULLIF(order_purchase_timestamp, '')::timestamp AS purchased_at,
    NULLIF(order_approved_at, '')::timestamp AS approved_at,
    NULLIF(order_delivered_carrier_date, '')::timestamp AS carrier_at,
    NULLIF(order_delivered_customer_date, '')::timestamp AS delivered_at,
    NULLIF(order_estimated_delivery_date, '')::timestamp AS estimated_at
FROM raw.orders;

DROP VIEW IF EXISTS staging.stg_order_items CASCADE;
CREATE VIEW staging.stg_order_items AS
SELECT
    order_id,
    NULLIF(order_item_id, '')::integer AS order_item_id,
    product_id,
    seller_id,
    NULLIF(shipping_limit_date, '')::timestamp AS shipping_limit_at,
    NULLIF(price, '')::numeric(14, 2) AS price,
    NULLIF(freight_value, '')::numeric(14, 2) AS freight_value
FROM raw.order_items;

DROP VIEW IF EXISTS staging.stg_order_payments CASCADE;
CREATE VIEW staging.stg_order_payments AS
SELECT
    order_id,
    NULLIF(payment_sequential, '')::integer AS payment_sequential,
    NULLIF(payment_type, '') AS payment_type,
    NULLIF(payment_installments, '')::integer AS payment_installments,
    NULLIF(payment_value, '')::numeric(14, 2) AS payment_value
FROM raw.order_payments;

DROP VIEW IF EXISTS staging.stg_reviews CASCADE;
CREATE VIEW staging.stg_reviews AS
SELECT
    review_id,
    order_id,
    NULLIF(review_score, '')::integer AS review_score,
    NULLIF(review_comment_title, '') AS review_comment_title,
    NULLIF(review_comment_message, '') AS review_comment_message,
    NULLIF(review_creation_date, '')::timestamp AS review_created_at,
    NULLIF(review_answer_timestamp, '')::timestamp AS review_answered_at
FROM raw.order_reviews;

DROP VIEW IF EXISTS staging.stg_products CASCADE;
CREATE VIEW staging.stg_products AS
SELECT
    p.product_id,
    p.product_category_name,
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
    NULLIF(p.product_name_lenght, '')::integer AS product_name_length,
    NULLIF(p.product_description_lenght, '')::integer AS product_description_length,
    NULLIF(p.product_photos_qty, '')::integer AS product_photos_qty,
    NULLIF(p.product_weight_g, '')::numeric AS product_weight_g,
    NULLIF(p.product_length_cm, '')::numeric AS product_length_cm,
    NULLIF(p.product_height_cm, '')::numeric AS product_height_cm,
    NULLIF(p.product_width_cm, '')::numeric AS product_width_cm
FROM raw.products p
LEFT JOIN raw.category_translation t USING (product_category_name);

DROP VIEW IF EXISTS staging.stg_customers CASCADE;
CREATE VIEW staging.stg_customers AS
SELECT
    customer_id,
    customer_unique_id,
    NULLIF(customer_zip_code_prefix, '')::integer AS zip_prefix,
    customer_city,
    customer_state
FROM raw.customers;

DROP VIEW IF EXISTS staging.stg_sellers CASCADE;
CREATE VIEW staging.stg_sellers AS
SELECT
    seller_id,
    NULLIF(seller_zip_code_prefix, '')::integer AS zip_prefix,
    seller_city,
    seller_state
FROM raw.sellers;

