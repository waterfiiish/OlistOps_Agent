CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS eval;

CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id text,
    customer_unique_id text,
    customer_zip_code_prefix text,
    customer_city text,
    customer_state text
);

CREATE TABLE IF NOT EXISTS raw.geolocation (
    geolocation_zip_code_prefix text,
    geolocation_lat text,
    geolocation_lng text,
    geolocation_city text,
    geolocation_state text
);

CREATE TABLE IF NOT EXISTS raw.orders (
    order_id text,
    customer_id text,
    order_status text,
    order_purchase_timestamp text,
    order_approved_at text,
    order_delivered_carrier_date text,
    order_delivered_customer_date text,
    order_estimated_delivery_date text
);

CREATE TABLE IF NOT EXISTS raw.order_items (
    order_id text,
    order_item_id text,
    product_id text,
    seller_id text,
    shipping_limit_date text,
    price text,
    freight_value text
);

CREATE TABLE IF NOT EXISTS raw.order_payments (
    order_id text,
    payment_sequential text,
    payment_type text,
    payment_installments text,
    payment_value text
);

CREATE TABLE IF NOT EXISTS raw.order_reviews (
    review_id text,
    order_id text,
    review_score text,
    review_comment_title text,
    review_comment_message text,
    review_creation_date text,
    review_answer_timestamp text
);

CREATE TABLE IF NOT EXISTS raw.products (
    product_id text,
    product_category_name text,
    product_name_lenght text,
    product_description_lenght text,
    product_photos_qty text,
    product_weight_g text,
    product_length_cm text,
    product_height_cm text,
    product_width_cm text
);

CREATE TABLE IF NOT EXISTS raw.sellers (
    seller_id text,
    seller_zip_code_prefix text,
    seller_city text,
    seller_state text
);

CREATE TABLE IF NOT EXISTS raw.category_translation (
    product_category_name text,
    product_category_name_english text
);

CREATE TABLE IF NOT EXISTS app.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text NOT NULL UNIQUE,
    role text NOT NULL DEFAULT 'analyst',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES app.users(id),
    key_hash text NOT NULL UNIQUE,
    label text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE TABLE IF NOT EXISTS app.chat_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES app.users(id),
    title text NOT NULL DEFAULT 'New analysis',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.chat_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES app.chat_sessions(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'system')),
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.agent_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES app.chat_sessions(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'queued',
    intent text,
    model_profile text,
    state jsonb NOT NULL DEFAULT '{}'::jsonb,
    warning_count integer NOT NULL DEFAULT 0,
    error jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS app.agent_events (
    sequence bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES app.agent_runs(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_events_run_sequence
    ON app.agent_events(run_id, sequence);

CREATE TABLE IF NOT EXISTS app.agent_steps (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES app.agent_runs(id) ON DELETE CASCADE,
    node_name text NOT NULL,
    status text NOT NULL,
    input_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    error jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS app.tool_calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES app.agent_runs(id) ON DELETE CASCADE,
    step_id bigint REFERENCES app.agent_steps(id) ON DELETE SET NULL,
    tool_name text NOT NULL,
    permission text NOT NULL,
    arguments jsonb NOT NULL,
    result_summary jsonb,
    error jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS app.approvals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES app.agent_runs(id) ON DELETE CASCADE,
    action_type text NOT NULL,
    action_payload jsonb NOT NULL,
    impact_summary text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    decided_by uuid REFERENCES app.users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);

CREATE TABLE IF NOT EXISTS app.artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES app.agent_runs(id) ON DELETE CASCADE,
    artifact_type text NOT NULL,
    path text NOT NULL,
    content_hash text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge.documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    source_type text NOT NULL,
    source_url text,
    license_note text,
    content_hash text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'ready',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge.chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES knowledge.documents(id) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    heading_path text[] NOT NULL DEFAULT ARRAY[]::text[],
    content text NOT NULL,
    content_hash text NOT NULL UNIQUE,
    token_count integer,
    embedding vector,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    UNIQUE(document_id, ordinal)
);
CREATE INDEX IF NOT EXISTS ix_chunks_search_vector
    ON knowledge.chunks USING gin(search_vector);

CREATE TABLE IF NOT EXISTS knowledge.ingestion_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid REFERENCES knowledge.documents(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'queued',
    error jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS eval.datasets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    version text NOT NULL,
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eval.cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id uuid NOT NULL REFERENCES eval.datasets(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    input jsonb NOT NULL,
    expected jsonb NOT NULL,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[],
    UNIQUE(dataset_id, external_id)
);

CREATE TABLE IF NOT EXISTS eval.runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id uuid NOT NULL REFERENCES eval.datasets(id),
    configuration jsonb NOT NULL,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'queued',
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS eval.results (
    id bigserial PRIMARY KEY,
    eval_run_id uuid NOT NULL REFERENCES eval.runs(id) ON DELETE CASCADE,
    case_id uuid NOT NULL REFERENCES eval.cases(id),
    passed boolean,
    scores jsonb NOT NULL DEFAULT '{}'::jsonb,
    output jsonb NOT NULL DEFAULT '{}'::jsonb,
    error jsonb
);

INSERT INTO app.users (username, role)
VALUES ('local-analyst', 'admin')
ON CONFLICT (username) DO NOTHING;

