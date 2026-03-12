"""Lightweight tests for knowledge base CRUD and scraper helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from backend.services.knowledge_base import KnowledgeBase
from backend.services.resource_scraper import ResourceScraper
from backend.services.vector_store import VectorStore


def _make_kb() -> KnowledgeBase:
    os.environ["EMBEDDING_PROVIDER"] = "hash"
    tmp = tempfile.mkdtemp(prefix="kb_test_")
    store = VectorStore(persist_directory=str(Path(tmp) / "chroma"))
    return KnowledgeBase(vector_store=store)


def test_document_registry_crud() -> None:
    kb = _make_kb()
    txt_file = Path(tempfile.mkdtemp(prefix="kb_file_")) / "article.txt"
    txt_file.write_text(
        "Audit risk and substantive procedures should be specific and practical. " * 5,
        encoding="utf-8",
    )

    result = kb.ingest_technical_document(str(txt_file), {"paper": "AA"})
    assert result["success"] is True

    document_id = result["document_id"]
    item = kb.get_document(document_id)
    assert item is not None

    updated = kb.update_document(document_id, {"topic": "audit risk"})
    assert updated is not None
    assert updated["metadata"]["topic"] == "audit risk"

    listing = kb.list_documents(collection="technical_articles")
    assert listing["count"] >= 1

    deleted = kb.delete_document(document_id, delete_vectors=True)
    assert deleted is True


def test_scraper_helpers() -> None:
    kb = _make_kb()
    scraper = ResourceScraper(kb=kb, request_delay_seconds=0)

    assert scraper._categorize_resource("https://example.com/aa-marking-scheme.pdf", "Marking scheme") == "marking_schemes"
    assert scraper._categorize_resource("https://example.com/examiner-report.pdf", "Examiner report") == "examiner_reports"
    assert scraper._categorize_resource("https://example.com/technical-note.pdf", "Technical") == "technical"

    name = scraper._build_filename("https://example.com/audit-guide.pdf?download=1")
    assert name.endswith(".pdf")
