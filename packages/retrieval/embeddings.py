from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter

LATIN_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]{1,}", re.IGNORECASE)
CHINESE_SEQUENCE = re.compile(r"[\u4e00-\u9fff]+")


class LocalHashEmbedding:
    """Deterministic, offline feature-hashing embeddings for the local RAG baseline.

    This provider is deliberately dependency-free and is not presented as a semantic
    embedding model. It gives pgvector a reproducible dense representation and keeps the
    complete hybrid retrieval path usable without an API key. A model-backed provider can
    replace it later without changing the storage or retrieval contracts.
    """

    provider = "local_hash"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 32:
            raise ValueError("dimensions must be at least 32")
        self.dimensions = dimensions

    @staticmethod
    def tokenize(text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKC", text).lower()
        tokens = LATIN_TOKEN.findall(normalized)
        for sequence in CHINESE_SEQUENCE.findall(normalized):
            if len(sequence) <= 4:
                tokens.append(sequence)
            for size in (2, 3, 4):
                tokens.extend(
                    sequence[index : index + size]
                    for index in range(max(0, len(sequence) - size + 1))
                )
        return tokens

    def embed(self, text: str) -> list[float]:
        counts = Counter(self.tokenize(text))
        vector = [0.0] * self.dimensions
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "little") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign * (1.0 + math.log1p(count))
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def vector_literal(self, text: str) -> str:
        return self.to_literal(self.embed(text))

    @staticmethod
    def to_literal(vector: list[float]) -> str:
        return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
