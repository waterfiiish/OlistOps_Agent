from __future__ import annotations

import hashlib
import re
from pathlib import Path

from packages.database.connection import psycopg_connect
from packages.database.migrations import apply_migrations
from packages.retrieval.embeddings import LocalHashEmbedding

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = PROJECT_ROOT / "data" / "knowledge_seed"
HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def chunks(markdown: str, target_chars: int = 600) -> list[tuple[list[str], str]]:
    sections: list[tuple[list[str], str]] = []
    heading_path: list[str] = []
    current: list[str] = []

    def flush() -> None:
        content = "\n".join(current).strip()
        if not content:
            return
        paragraphs = content.split("\n\n")
        buffer = ""
        for paragraph in paragraphs:
            candidate = f"{buffer}\n\n{paragraph}".strip()
            if buffer and len(candidate) > target_chars:
                sections.append((heading_path.copy(), buffer))
                buffer = paragraph
            else:
                buffer = candidate
        if buffer:
            sections.append((heading_path.copy(), buffer))

    for line in markdown.splitlines():
        match = HEADING.match(line)
        if match:
            flush()
            current.clear()
            level = len(match.group(1))
            heading_path[:] = heading_path[: level - 1]
            heading_path.append(match.group(2).strip())
        else:
            current.append(line)
    flush()
    return sections


def ingest() -> None:
    files = sorted(SEED_DIR.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No Markdown policies found in {SEED_DIR}")
    embedder = LocalHashEmbedding()
    with psycopg_connect() as connection:
        apply_migrations(connection)
        for path in files:
            content = path.read_text(encoding="utf-8")
            content_hash = digest(content)
            title = next(
                (
                    match.group(2).strip()
                    for match in [HEADING.search(content)]
                    if match is not None
                ),
                path.stem,
            )
            row = connection.execute(
                """
                INSERT INTO knowledge.documents(
                    title, source_type, license_note, content_hash, status, metadata
                )
                VALUES (
                    %s, 'project_simulated_policy',
                    '项目模拟文档，可用于非商业作品集演示',
                    %s, 'embedding',
                    jsonb_build_object(
                        'filename', CAST(%s AS text),
                        'simulated', true,
                        'embedding_provider', 'local_hash',
                        'embedding_dimensions', 384
                    )
                )
                ON CONFLICT (content_hash) DO UPDATE
                SET title = EXCLUDED.title,
                    status = 'embedding',
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                RETURNING id
                """,
                (title, content_hash, path.name),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Failed to upsert knowledge document: {path.name}")
            document_id = row["id"]
            job_row = connection.execute(
                """
                INSERT INTO knowledge.ingestion_jobs(document_id, status)
                VALUES (%s, 'running')
                RETURNING id
                """,
                (document_id,),
            ).fetchone()
            if job_row is None:
                raise RuntimeError(f"Failed to create ingestion job: {path.name}")
            job_id = job_row["id"]
            connection.execute(
                "DELETE FROM knowledge.chunks WHERE document_id = %s",
                (document_id,),
            )
            for ordinal, (heading_path, chunk) in enumerate(chunks(content)):
                embedding_text = "\n".join([title, *heading_path, chunk])
                connection.execute(
                    """
                    INSERT INTO knowledge.chunks(
                        document_id, ordinal, heading_path, content,
                        content_hash, token_count, embedding, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, CAST(%s AS vector),
                        jsonb_build_object(
                            'embedding_provider', 'local_hash',
                            'embedding_dimensions', 384
                        )
                    )
                    """,
                    (
                        document_id,
                        ordinal,
                        heading_path,
                        chunk,
                        digest(f"{content_hash}:{ordinal}:{chunk}"),
                        max(1, len(chunk) // 3),
                        embedder.vector_literal(embedding_text),
                    ),
                )
            connection.execute(
                """
                UPDATE knowledge.documents
                SET status = 'ready', updated_at = now()
                WHERE id = %s
                """,
                (document_id,),
            )
            connection.execute(
                """
                UPDATE knowledge.ingestion_jobs
                SET status = 'completed', completed_at = now()
                WHERE id = %s
                """,
                (job_id,),
            )
            print(f"Ingested and embedded {path.name}")
        connection.commit()
        count_row = connection.execute(
            """
            SELECT count(*) AS count, count(embedding) AS embedded_count
            FROM knowledge.chunks
            """
        ).fetchone()
        if count_row is None:
            raise RuntimeError("Failed to count knowledge chunks")
        count = count_row["count"]
        embedded_count = count_row["embedded_count"]
    print(
        "Hybrid knowledge baseline ready: "
        f"{count} chunks, {embedded_count} embeddings"
    )


if __name__ == "__main__":
    ingest()
