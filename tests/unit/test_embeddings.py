import pytest

from packages.retrieval.embeddings import LocalHashEmbedding, cosine_similarity
from packages.retrieval.service import expand_query


def test_local_hash_embedding_is_deterministic_and_normalized() -> None:
    embedder = LocalHashEmbedding(dimensions=64)
    first = embedder.embed("配送延期与包装检查")
    second = embedder.embed("配送延期与包装检查")
    assert first == second
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_related_text_has_higher_similarity_than_unrelated_text() -> None:
    embedder = LocalHashEmbedding(dimensions=128)
    query = embedder.embed("配送延期包装")
    related = embedder.embed("配送发生延期，需要完成包装检查")
    unrelated = embedder.embed("信用卡分期支付结构")
    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)


def test_query_expansion_adds_domain_terms_without_duplicates() -> None:
    terms = expand_query("如何处理配送延期")
    assert "延期" in terms
    assert "delivery" in terms
    assert len(terms) == len(set(terms))
