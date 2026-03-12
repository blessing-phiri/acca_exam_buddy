"""Upload endpoints for handling file uploads and orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from backend.services.knowledge_base import KnowledgeBase
from backend.services.marking_service import MarkingService
from backend.services.processing_service import ProcessingService

router = APIRouter()
logger = logging.getLogger(__name__)

processing_service = ProcessingService()
knowledge_base = KnowledgeBase()
marking_service = MarkingService()

DATA_DIR = Path("data/uploads")
UPLOADS_STORE_FILE = DATA_DIR / "uploads_store.json"
RESULTS_STORE_FILE = DATA_DIR / "results_store.json"
_STORE_LOCK = threading.Lock()


def _ensure_store_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not UPLOADS_STORE_FILE.exists():
        UPLOADS_STORE_FILE.write_text(json.dumps({"items": {}}, indent=2), encoding="utf-8")
    if not RESULTS_STORE_FILE.exists():
        RESULTS_STORE_FILE.write_text(json.dumps({"items": {}}, indent=2), encoding="utf-8")


def _load_store(path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items", {})
        return items if isinstance(items, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_store(path: Path, items: Dict[str, Dict[str, Any]]) -> None:
    payload = {"items": items, "updated_at": datetime.now().isoformat()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _set_upload_state(upload_id: str, status: str, **updates: Any) -> None:
    with _STORE_LOCK:
        upload = uploads.get(upload_id)
        if not upload:
            return
        upload["status"] = status
        upload["updated_at"] = datetime.now().isoformat()
        upload.update(updates)
        _save_store(UPLOADS_STORE_FILE, uploads)


def _persist_result(result_id: str, payload: Dict[str, Any]) -> None:
    with _STORE_LOCK:
        results[result_id] = payload
        _save_store(RESULTS_STORE_FILE, results)


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _derive_marking_inputs(upload: Dict[str, Any], process_result: Dict[str, Any]) -> Dict[str, Any]:
    questions = process_result.get("questions") or []
    cleaned_answer = (process_result.get("cleaned_text") or "").strip()

    if questions:
        first = questions[0]
        header = str(first.get("header") or "").strip()
        body = str(first.get("text") or "").strip()
        question_text = "\n".join(part for part in [header, body] if part).strip()
    else:
        question_number = (upload.get("question_number") or "").strip()
        suffix = f" for question {question_number}" if question_number else ""
        question_text = f"Assess this ACCA {upload.get('paper', 'AA')} student answer{suffix}."

    if not question_text:
        question_text = f"Assess this ACCA {upload.get('paper', 'AA')} student answer."

    detected_marks = [
        _to_float(item.get("marks"))
        for item in questions
        if isinstance(item, dict) and item.get("marks") is not None
    ]
    max_marks = sum(mark for mark in detected_marks if mark is not None and mark > 0)
    if max_marks <= 0:
        max_marks = 16.0

    return {
        "question_text": question_text,
        "student_answer": cleaned_answer,
        "max_marks": max_marks,
    }


def _fallback_mark_result(process_result: Dict[str, Any], max_marks: float, error: str) -> Dict[str, Any]:
    question_count = int(process_result.get("question_count", 0) or 0)
    base = max_marks * 0.6
    bonus = min(max_marks * 0.15, question_count * 0.25)
    total = max(0.0, min(max_marks, round(base + bonus, 2)))

    return {
        "total_marks": total,
        "max_marks": max_marks,
        "question_marks": [
            {
                "point": "Content relevance",
                "awarded": round(min(max_marks, total * 0.5), 2),
                "explanation": "Fallback heuristic applied because the LLM engine call failed.",
            },
            {
                "point": "Structure and coverage",
                "awarded": round(min(max_marks, total * 0.5), 2),
                "explanation": "Estimated from extracted question boundaries and answer coverage.",
            },
        ],
        "professional_marks": process_result.get("professional_marks", {}),
        "feedback": f"Marking engine unavailable; fallback score generated. Error: {error}",
        "citations": ["Fallback scoring mode"],
        "confidence_score": 0.45,
        "needs_review": True,
        "model_used": "fallback-heuristic",
    }


_ensure_store_files()
uploads = _load_store(UPLOADS_STORE_FILE)
results = _load_store(RESULTS_STORE_FILE)


@router.post("/api/v1/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    paper: str = Form(...),
    question_number: Optional[str] = Form(None),
):
    """Upload a file for marking."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are allowed")

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB allowed.")

    upload_id = str(uuid.uuid4())
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename).name
    safe_filename = f"{upload_id}_{original_name.replace(' ', '_')}"
    file_path = str(DATA_DIR / safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info("File saved: %s", file_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to save file")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from exc

    now = datetime.now().isoformat()
    with _STORE_LOCK:
        uploads[upload_id] = {
            "id": upload_id,
            "filename": original_name,
            "saved_filename": safe_filename,
            "file_path": file_path,
            "file_size": file_size,
            "paper": paper,
            "question_number": question_number,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        _save_store(UPLOADS_STORE_FILE, uploads)

    background_tasks.add_task(process_file_background, upload_id)

    return {
        "upload_id": upload_id,
        "filename": original_name,
        "size": file_size,
        "status": "pending",
        "message": "File uploaded successfully. Processing started.",
    }


@router.get("/api/v1/status/{upload_id}")
async def get_status(upload_id: str):
    """Get processing status for an upload."""
    upload = uploads.get(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    progress_map = {
        "pending": 5,
        "extracting": 25,
        "cleaning": 45,
        "analyzing": 65,
        "marking": 85,
        "complete": 100,
        "failed": 0,
    }

    return {
        "upload_id": upload_id,
        "filename": upload["filename"],
        "status": upload["status"],
        "progress": progress_map.get(upload["status"], 0),
        "result_id": upload.get("result_id"),
        "created_at": upload["created_at"],
        "updated_at": upload.get("updated_at", upload["created_at"]),
    }


@router.get("/api/v1/result/{result_id}")
async def get_result(result_id: str):
    """Get marking result."""
    result = results.get(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


def process_file_background(upload_id: str) -> None:
    """Background processing of uploaded file."""
    logger.info("Starting background processing for %s", upload_id)

    upload = uploads.get(upload_id)
    if not upload:
        logger.error("Upload ID not found in store: %s", upload_id)
        return

    try:
        _set_upload_state(upload_id, "extracting")

        process_result = processing_service.process_upload(upload["file_path"], upload_id)
        if not process_result.get("success", False):
            raise RuntimeError(process_result.get("error", "Processing failed"))

        _set_upload_state(upload_id, "cleaning", processed_data=process_result)

        try:
            answer_ingest = knowledge_base.ingest_student_answer(
                answer_text=process_result.get("cleaned_text", ""),
                metadata={
                    "paper": upload.get("paper", "AA"),
                    "upload_id": upload_id,
                    "question_number": upload.get("question_number"),
                    "source_file": upload.get("filename"),
                },
            )
            _set_upload_state(upload_id, "cleaning", student_answer_ingest=answer_ingest)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Student answer ingestion failed for %s: %s", upload_id, exc)

        _set_upload_state(upload_id, "analyzing")
        mark_inputs = _derive_marking_inputs(upload=upload, process_result=process_result)

        _set_upload_state(upload_id, "marking")
        try:
            mark_result = asyncio.run(
                marking_service.mark_answer(
                    question_text=mark_inputs["question_text"],
                    student_answer=mark_inputs["student_answer"],
                    max_marks=mark_inputs["max_marks"],
                    question_type=None,
                    paper_code=upload.get("paper", "AA"),
                    context={
                        "upload_id": upload_id,
                        "question_number": upload.get("question_number"),
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Engine marking failed for %s", upload_id)
            mark_result = _fallback_mark_result(process_result, mark_inputs["max_marks"], str(exc))

        total_marks = float(mark_result.get("total_marks", 0.0))
        max_marks = float(mark_result.get("max_marks", mark_inputs["max_marks"]))
        percentage = round((total_marks / max_marks) * 100, 2) if max_marks > 0 else 0.0

        result_id = str(uuid.uuid4())
        result_payload = {
            "id": result_id,
            "upload_id": upload_id,
            "filename": upload["filename"],
            "total_marks": total_marks,
            "max_marks": max_marks,
            "percentage": percentage,
            "word_count": process_result.get("word_count", 0),
            "question_count": process_result.get("question_count", 0),
            "question_marks": mark_result.get("question_marks", []),
            "professional_marks": mark_result.get("professional_marks", {}),
            "feedback": mark_result.get(
                "feedback",
                f"Document processed successfully. Found {process_result.get('question_count', 0)} questions.",
            ),
            "citations": mark_result.get("citations", []),
            "confidence_score": mark_result.get("confidence_score"),
            "needs_review": mark_result.get("needs_review", False),
            "model_used": mark_result.get("model_used", "unknown"),
            "created_at": datetime.now().isoformat(),
        }

        _persist_result(result_id, result_payload)
        _set_upload_state(upload_id, "complete", result_id=result_id)

        logger.info("Processing complete for %s", upload_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Processing failed for %s", upload_id)
        _set_upload_state(upload_id, "failed", error=str(exc))
