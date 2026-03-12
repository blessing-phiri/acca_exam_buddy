"""
Knowledge base API routes for ingestion and retrieval.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.knowledge_base import KnowledgeBase

router = APIRouter(tags=["knowledge"])
kb = KnowledgeBase()


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
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Web ingestion failed"))

    return result


@router.get("/api/v1/knowledge/search")
async def search_knowledge(
    query: str,
    collection: Literal["marking_schemes", "examiner_reports", "technical_articles"] = "technical_articles",
    n_results: int = 5,
    paper: Optional[str] = "AA",
):
    if not query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    filter_dict = {"paper": paper} if paper else None

    if collection == "marking_schemes":
        results = kb.retrieve_marking_rules(query, paper=paper or "", n_results=n_results)
    elif collection == "examiner_reports":
        results = kb.retrieve_examiner_guidance(query, n_results=n_results)
    else:
        results = kb.vector_store.search(
            collection_name=collection,
            query=query,
            n_results=n_results,
            filter_dict=filter_dict,
        )

    return {
        "query": query,
        "collection": collection,
        "count": len(results),
        "results": results,
    }


@router.get("/api/v1/knowledge/stats")
async def knowledge_stats():
    return kb.get_knowledge_summary()
