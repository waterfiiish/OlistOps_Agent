DO $$
BEGIN
    IF (
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'knowledge'
          AND c.relname = 'chunks'
          AND a.attname = 'embedding'
          AND NOT a.attisdropped
    ) IS DISTINCT FROM 'vector(384)' THEN
        ALTER TABLE knowledge.chunks
            ALTER COLUMN embedding TYPE vector(384)
            USING embedding::vector(384);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
    ON knowledge.chunks
    USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

CREATE TABLE IF NOT EXISTS knowledge.search_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    query text NOT NULL,
    retrieval_mode text NOT NULL
        CHECK (retrieval_mode IN ('hybrid', 'fts', 'vector')),
    expanded_terms text[] NOT NULL DEFAULT ARRAY[]::text[],
    lexical_candidate_count integer NOT NULL DEFAULT 0,
    vector_candidate_count integer NOT NULL DEFAULT 0,
    result_chunk_ids uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
    duration_ms double precision NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_search_logs_created_at
    ON knowledge.search_logs(created_at DESC);
