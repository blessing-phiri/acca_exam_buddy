"""Tests for knowledge ingestion pipeline utilities."""

from __future__ import annotations

import os

from backend.services.knowledge_base import KnowledgeBase
from backend.services.vector_store import VectorStore


def _make_kb(tmp_path):
    os.environ["EMBEDDING_PROVIDER"] = "hash"
    store = VectorStore(persist_directory=str(tmp_path / "chroma"))
    return KnowledgeBase(vector_store=store)


def test_vector_store_hash_embedding_roundtrip(tmp_path):
    kb = _make_kb(tmp_path)

    insert_result = kb.ingest_technical_document(
        file_path=str(tmp_path / "article.txt"),
        metadata={"paper": "AA", "year": "2025"},
    )
    assert insert_result["success"] is False

    article = tmp_path / "article.txt"
    article.write_text(
        "Audit risk is higher where controls are weak. "
        "Substantive procedures should focus on receivables, revenue cut-off, and journal testing.",
        encoding="utf-8",
    )

    insert_result = kb.ingest_technical_document(
        file_path=str(article),
        metadata={"paper": "AA", "year": "2025"},
    )
    assert insert_result["success"] is True
    assert insert_result["chunk_count"] >= 1

    hits = kb.retrieve_technical_references("revenue cut-off procedures", paper="AA", n_results=3)
    assert isinstance(hits, list)
    assert len(hits) >= 1


def test_extract_article_links_from_index(tmp_path):
    kb = _make_kb(tmp_path)

    html = """
    <html>
      <body>
        <a href="/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles/fraud.html">Fraud article</a>
        <a href="/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles/risk.html">Risk article</a>
        <a href="/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles.html">Index page</a>
        <a href="https://example.com/other.html">External</a>
      </body>
    </html>
    """

    links = kb._extract_article_links(
        "https://www.accaglobal.com/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles.html",
        html,
    )

    assert len(links) == 2
    assert all("technical-articles/" in link for link in links)
    assert all(link.endswith(".html") for link in links)
