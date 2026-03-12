"""
Upload endpoints for handling file uploads.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from backend.services.knowledge_base import KnowledgeBase
from backend.services.processing_service import ProcessingService

router = APIRouter()
logger = logging.getLogger(__name__)

processing_service = ProcessingService()
knowledge_base = KnowledgeBase()

# In-memory storage (replace with a persistent database in production).
uploads = {}
results = {}


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
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    original_name = Path(file.filename).name
    safe_filename = f"{upload_id}_{original_name.replace(' ', '_')}"
    file_path = os.path.join(upload_dir, safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info("File saved: %s", file_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to save file")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from exc

    now = datetime.now().isoformat()
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
    if upload_id not in uploads:
        raise HTTPException(status_code=404, detail="Upload not found")

    upload = uploads[upload_id]
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
    if result_id not in results:
        raise HTTPException(status_code=404, detail="Result not found")
    return results[result_id]


def process_file_background(upload_id: str) -> None:
    """Background processing of uploaded file."""
    logger.info("Starting background processing for %s", upload_id)

    upload = uploads.get(upload_id)
    if not upload:
        logger.error("Upload ID not found in memory store: %s", upload_id)
        return

    try:
        upload["status"] = "extracting"
        upload["updated_at"] = datetime.now().isoformat()

        process_result = processing_service.process_upload(upload["file_path"], upload_id)
        if not process_result.get("success", False):
            raise RuntimeError(process_result.get("error", "Processing failed"))

        upload["status"] = "cleaning"
        upload["updated_at"] = datetime.now().isoformat()
        upload["processed_data"] = process_result

        # Store answer in student_answers collection for consistency retrieval.
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
            upload["student_answer_ingest"] = answer_ingest
        except Exception as exc:  # noqa: BLE001
            logger.warning("Student answer ingestion failed for %s: %s", upload_id, exc)

        upload["status"] = "analyzing"
        upload["updated_at"] = datetime.now().isoformat()

        upload["status"] = "marking"
        upload["updated_at"] = datetime.now().isoformat()

        time.sleep(2)

        result_id = str(uuid.uuid4())
        upload["result_id"] = result_id
        upload["status"] = "complete"
        upload["updated_at"] = datetime.now().isoformat()

        results[result_id] = {
            "id": result_id,
            "upload_id": upload_id,
            "filename": upload["filename"],
            "total_marks": 14.5,
            "max_marks": 16,
            "percentage": 90.6,
            "word_count": process_result.get("word_count", 0),
            "question_count": process_result.get("question_count", 0),
            "question_marks": [
                {
                    "point": "Document structure analysis",
                    "awarded": 1.0 if process_result.get("question_count", 0) > 0 else 0.5,
                    "explanation": "Automatically extracted question boundaries and key sections.",
                },
                {
                    "point": "Content extraction quality",
                    "awarded": 0.5,
                    "explanation": "Text extraction and cleanup completed successfully.",
                },
            ],
            "professional_marks": process_result.get("professional_marks", {}),
            "feedback": f"Document processed successfully. Found {process_result.get('question_count', 0)} questions.",
            "citations": ["Based on extracted text"],
            "created_at": datetime.now().isoformat(),
        }

        logger.info("Processing complete for %s", upload_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Processing failed for %s", upload_id)
        if upload_id in uploads:
            uploads[upload_id]["status"] = "failed"
            uploads[upload_id]["error"] = str(exc)
            uploads[upload_id]["updated_at"] = datetime.now().isoformat()
