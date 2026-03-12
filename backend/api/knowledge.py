"""
Knowledge base API routes for ingestion, retrieval, CRUD, and scraping.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.knowledge_base import KnowledgeBase
from backend.services.resource_scraper import ResourceScraper

router = APIRouter(tags=["knowledge"])
kb = KnowledgeBase()
scraper = ResourceScraper(kb=kb)


class LocalIngestRequest(BaseModel):
    file_path: str = Field(..., description="Absolute or project-relative path to source file")
    doc_type: Literal["marking_scheme", "examiner_report", "technical_article"]
    paper: str = "AA"
    year: Optional[str] = None
    question_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WebIngestRequest(BaseModel):
    index_url: str = "https://www.accaglobal.com/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles.html"
    paper: str = "AA"
    max_articles: int = 15
    request_delay_seconds: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StudentAnswerIngestRequest(BaseModel):
    answer_text: str
    upload_id: Optional[str] = None
    paper: str = "AA"
    question_number: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentUpdateRequest(BaseModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScrapeRunRequest(BaseModel):
    start_url: str = "https://www.accaglobal.com/gb/en/student/exam-support-resources/fundamentals-exams-study-resources/f8/technical-articles.html"
    paper: str = "AA"
    auto_ingest: bool = True
    max_pages: int = 30
    max_pdf_downloads: int = 100
    include_html_articles: bool = True
    request_delay_seconds: float = 1.0


class ManualFallbackResolveRequest(BaseModel):
    notes: Optional[str] = None
    local_file_path: Optional[str] = None
    doc_type: Optional[Literal["marking_scheme", "examiner_report", "technical_article"]] = None
    paper: str = "AA"
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/knowledge/ingest/local")
async def ingest_local(payload: LocalIngestRequest):
    source_path = Path(payload.file_path)
    if not source_path.is_absolute():
        source_path = Path(os.getcwd()) / source_path

    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Source file not found: {source_path}")

    metadata = {
        "paper": payload.paper,
        "year": payload.year or "unknown",
        "question_type": payload.question_type,
        **payload.metadata,
    }

    if payload.doc_type == "marking_scheme":
        result = kb.ingest_marking_scheme(str(source_path), metadata)
    elif payload.doc_type == "examiner_report":
        result = kb.ingest_examiner_report(str(source_path), metadata)
    else:
        result = kb.ingest_technical_document(str(source_path), metadata)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Ingestion failed"))

    return result


@router.post("/api/v1/knowledge/ingest/web")
async def ingest_web(payload: WebIngestRequest):
    metadata = {"paper": payload.paper, **payload.metadata}
    result = kb.ingest_technical_articles_from_index(
        index_url=payload.index_url,
        metadata=metadata,
        max_articles=payload.max_articles,
        request_delay_seconds=payload.request_delay_seconds,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Web ingestion failed"))

    return result


@router.post("/api/v1/knowledge/ingest/student-answer")
async def ingest_student_answer(payload: StudentAnswerIngestRequest):
    metadata = {
        "paper": payload.paper,
        "upload_id": payload.upload_id,
        "question_number": payload.question_number,
        **payload.metadata,
    }
    result = kb.ingest_student_answer(payload.answer_text, metadata)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Student answer ingestion failed"))
    return result


@router.get("/api/v1/knowledge/search")
async def search_knowledge(
    query: str,
    collection: Literal["marking_schemes", "examiner_reports", "technical_articles", "student_answers"] = "technical_articles",
    n_results: int = 5,
    paper: Optional[str] = "AA",
):
    if not query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    if collection == "marking_schemes":
        results = kb.retrieve_marking_rules(query, paper=paper or "", n_results=n_results)
    elif collection == "examiner_reports":
        results = kb.retrieve_examiner_guidance(query, n_results=n_results)
    elif collection == "student_answers":
        results = kb.retrieve_similar_student_answers(query, n_results=n_results)
    else:
        results = kb.retrieve_technical_references(query, paper=paper or "", n_results=n_results)

    return {
        "query": query,
        "collection": collection,
        "count": len(results),
        "results": results,
    }


@router.get("/api/v1/knowledge/documents")
async def list_documents(
    collection: Optional[str] = None,
    document_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    return kb.list_documents(collection=collection, document_type=document_type, limit=limit, offset=offset)


@router.get("/api/v1/knowledge/documents/{document_id}")
async def get_document(document_id: str):
    item = kb.get_document(document_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    return item


@router.patch("/api/v1/knowledge/documents/{document_id}")
async def update_document(document_id: str, payload: DocumentUpdateRequest):
    updated = kb.update_document(document_id, payload.metadata)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@router.delete("/api/v1/knowledge/documents/{document_id}")
async def delete_document(document_id: str, delete_vectors: bool = True):
    deleted = kb.delete_document(document_id, delete_vectors=delete_vectors)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "document_id": document_id, "delete_vectors": delete_vectors}


@router.post("/api/v1/knowledge/scrape/run")
async def run_scrape(payload: ScrapeRunRequest):
    scraper.request_delay_seconds = max(0.0, payload.request_delay_seconds)
    result = scraper.run(
        start_url=payload.start_url,
        paper=payload.paper,
        auto_ingest=payload.auto_ingest,
        max_pages=payload.max_pages,
        max_pdf_downloads=payload.max_pdf_downloads,
        include_html_articles=payload.include_html_articles,
    )
    return result


@router.get("/api/v1/knowledge/scrape/manual-fallback")
async def list_manual_fallback(status: Optional[str] = None):
    return kb.list_manual_fallback(status=status)


@router.post("/api/v1/knowledge/scrape/manual-fallback/{item_id}/resolve")
async def resolve_manual_fallback(item_id: str, payload: ManualFallbackResolveRequest):
    resolved = kb.resolve_manual_fallback(item_id=item_id, notes=payload.notes)
    if not resolved:
        raise HTTPException(status_code=404, detail="Manual fallback item not found")

    ingest_result = None
    if payload.local_file_path and payload.doc_type:
        source_path = Path(payload.local_file_path)
        if not source_path.is_absolute():
            source_path = Path(os.getcwd()) / source_path

        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Source file not found: {source_path}")

        metadata = {"paper": payload.paper, **payload.metadata}
        if payload.doc_type == "marking_scheme":
            ingest_result = kb.ingest_marking_scheme(str(source_path), metadata)
        elif payload.doc_type == "examiner_report":
            ingest_result = kb.ingest_examiner_report(str(source_path), metadata)
        else:
            ingest_result = kb.ingest_technical_document(str(source_path), metadata)

        if not ingest_result.get("success"):
            raise HTTPException(status_code=400, detail=ingest_result.get("error", "Ingestion failed"))

    return {
        "resolved": resolved,
        "ingest_result": ingest_result,
    }


@router.get("/api/v1/knowledge/stats")
async def knowledge_stats():
    return kb.get_knowledge_summary()
