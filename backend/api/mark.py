"""Marking API endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.services.marking_service import MarkingService

router = APIRouter(prefix="/api/v1/mark", tags=["marking"])
logger = logging.getLogger(__name__)

marking_service = MarkingService()
batch_jobs: Dict[str, Dict[str, Any]] = {}


class MarkRequest(BaseModel):
    question_text: str
    student_answer: str
    max_marks: float = Field(..., gt=0, le=30)
    question_type: Optional[str] = None
    paper_code: str = "AA"
    context: Optional[Dict[str, Any]] = None


class MarkResponse(BaseModel):
    id: str
    total_marks: float
    max_marks: float
    percentage: float
    question_marks: List[Dict[str, Any]]
    professional_marks: Dict[str, float]
    feedback: str
    citations: List[str]
    confidence_score: float
    needs_review: bool
    processing_time_ms: float
    model_used: str
    created_at: str


class BatchMarkRequest(BaseModel):
    answers: List[Dict[str, Any]]
    paper_code: str = "AA"


class BatchMarkResponse(BaseModel):
    batch_id: str
    status: str
    total_answers: int
    estimated_time_seconds: int


@router.post("/", response_model=MarkResponse)
async def mark_answer(request: MarkRequest):
    """Mark a single answer."""
    try:
        result = await marking_service.mark_answer(
            question_text=request.question_text,
            student_answer=request.student_answer,
            max_marks=request.max_marks,
            question_type=request.question_type,
            paper_code=request.paper_code,
            context=request.context,
        )

        result["id"] = str(uuid.uuid4())
        result["created_at"] = datetime.now().isoformat()
        result["percentage"] = round((result["total_marks"] / request.max_marks) * 100, 2)
        return result
    except RuntimeError as exc:
        # LLM/provider failures should be surfaced as 503 with actionable detail.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Single mark request failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/llm-health")
async def llm_health() -> Dict[str, Any]:
    """Provider health probe for keys/connectivity/model availability."""
    payload = await marking_service.get_llm_health()
    if payload.get("overall_ok"):
        return payload
    raise HTTPException(status_code=503, detail=payload)


@router.post("/batch", response_model=BatchMarkResponse)
async def mark_batch(request: BatchMarkRequest, background_tasks: BackgroundTasks):
    """Queue a batch marking job."""
    if not request.answers:
        raise HTTPException(status_code=400, detail="answers list cannot be empty")

    for index, answer in enumerate(request.answers):
        if not all(key in answer for key in ["question_text", "student_answer", "max_marks"]):
            raise HTTPException(status_code=400, detail=f"answer at index {index} missing required fields")

    batch_id = str(uuid.uuid4())
    batch_info: Dict[str, Any] = {
        "id": batch_id,
        "status": "pending",
        "answers": request.answers,
        "paper_code": request.paper_code,
        "created_at": datetime.now().isoformat(),
        "progress": 0,
        "completed": 0,
        "total": len(request.answers),
        "results": [],
    }
    batch_jobs[batch_id] = batch_info

    background_tasks.add_task(process_batch, batch_id)

    return BatchMarkResponse(
        batch_id=batch_id,
        status="pending",
        total_answers=len(request.answers),
        estimated_time_seconds=len(request.answers) * 20,
    )


@router.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Get batch marking status."""
    batch = batch_jobs.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    return {
        "batch_id": batch_id,
        "status": batch.get("status", "unknown"),
        "progress": batch.get("progress", 0),
        "completed": batch.get("completed", 0),
        "total": batch.get("total", 0),
        "results": batch.get("results", []),
    }


@router.get("/types")
async def get_question_types():
    """Get supported question types."""
    return {
        "types": [
            {"id": "audit_risk", "name": "Audit Risk", "description": "Identify and explain audit risks"},
            {"id": "ethical_threats", "name": "Ethical Threats", "description": "Identify ethical threats and safeguards"},
            {"id": "substantive_procedures", "name": "Substantive Procedures", "description": "Describe audit procedures"},
            {"id": "internal_control", "name": "Internal Control", "description": "Identify control deficiencies"},
            {"id": "audit_report", "name": "Audit Report", "description": "Determine audit opinion"},
            {"id": "going_concern", "name": "Going Concern", "description": "Evaluate going concern issues"},
        ]
    }


@router.get("/stats")
async def get_marking_stats():
    """Get aggregated marking statistics."""
    return marking_service.get_stats()


async def process_batch(batch_id: str) -> None:
    """Process a queued batch marking job."""
    batch = batch_jobs.get(batch_id)
    if not batch:
        return

    answers = batch.get("answers", [])
    if not answers:
        batch["status"] = "failed"
        batch["completed_at"] = datetime.now().isoformat()
        return

    batch["status"] = "processing"

    results: List[Dict[str, Any]] = []
    for index, answer in enumerate(answers):
        try:
            max_marks = float(answer["max_marks"])
            result = await marking_service.mark_answer(
                question_text=str(answer["question_text"]),
                student_answer=str(answer["student_answer"]),
                max_marks=max_marks,
                question_type=answer.get("question_type"),
                paper_code=batch.get("paper_code", "AA"),
                context=answer.get("context"),
            )

            result["id"] = str(uuid.uuid4())
            result["created_at"] = datetime.now().isoformat()
            result["percentage"] = round((result["total_marks"] / max_marks) * 100, 2)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Batch answer failed index=%s", index)
            results.append({"error": str(exc), "answer_index": index})

        batch["completed"] = index + 1
        batch["progress"] = round(((index + 1) / len(answers)) * 100, 2)

    batch["status"] = "completed"
    batch["results"] = results
    batch["completed_at"] = datetime.now().isoformat()
    logger.info("Batch %s completed with %s results", batch_id, len(results))
