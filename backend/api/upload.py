"""
Upload endpoints for handling file uploads
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import Optional
import uuid
import os
from datetime import datetime
import shutil
import logging

from backend.services.processing_service import ProcessingService

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize services
processing_service = ProcessingService()

# In-memory storage (replace with database later)
uploads = {}
results = {}

@router.post("/api/v1/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    paper: str = Form(...),
    question_number: Optional[str] = Form(None)
):
    """Upload a file for marking"""
    
    # Validate file type
    if not (file.filename.endswith('.pdf') or file.filename.endswith('.docx')):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are allowed")
    
    # Validate file size (10MB limit)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=400, detail="File too large. Max 10MB allowed.")
    
    # Generate unique ID
    upload_id = str(uuid.uuid4())
    
    # Create upload directory
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Save file with unique name
    safe_filename = f"{upload_id}_{file.filename.replace(' ', '_')}"
    file_path = os.path.join(upload_dir, safe_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"File saved: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save file: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")
    
    # Store metadata
    uploads[upload_id] = {
        "id": upload_id,
        "filename": file.filename,
        "saved_filename": safe_filename,
        "file_path": file_path,
        "file_size": file_size,
        "paper": paper,
        "question_number": question_number,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    # Start processing in background
    background_tasks.add_task(process_file_background, upload_id)
    
    return {
        "upload_id": upload_id,
        "filename": file.filename,
        "size": file_size,
        "status": "pending",
        "message": "File uploaded successfully. Processing started."
    }

@router.get("/api/v1/status/{upload_id}")
async def get_status(upload_id: str):
    """Get processing status for an upload"""
    if upload_id not in uploads:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    upload = uploads[upload_id]
    
    # Map status to progress percentage
    progress_map = {
        "pending": 5,
        "extracting": 25,
        "cleaning": 45,
        "analyzing": 65,
        "marking": 85,
        "complete": 100,
        "failed": 0
    }
    
    return {
        "upload_id": upload_id,
        "filename": upload["filename"],
        "status": upload["status"],
        "progress": progress_map.get(upload["status"], 0),
        "result_id": upload.get("result_id"),
        "created_at": upload["created_at"],
        "updated_at": upload.get("updated_at", upload["created_at"])
    }

@router.get("/api/v1/result/{result_id}")
async def get_result(result_id: str):
    """Get marking result"""
    if result_id not in results:
        raise HTTPException(status_code=404, detail="Result not found")
    
    return results[result_id]

def process_file_background(upload_id: str):
    """Background processing of uploaded file"""
    logger.info(f"Starting background processing for {upload_id}")
    
    upload = uploads[upload_id]
    
    try:
        # Step 1: Extract text
        upload["status"] = "extracting"
        upload["updated_at"] = datetime.now().isoformat()
        
        # Process document
        process_result = processing_service.process_upload(
            upload["file_path"], 
            upload_id
        )
        
        if not process_result.get("success", False):
            raise Exception(process_result.get("error", "Processing failed"))
        
        # Step 2: Cleaning complete
        upload["status"] = "cleaning"
        upload["updated_at"] = datetime.now().isoformat()
        
        # Store extracted data
        upload["processed_data"] = process_result
        
        # Step 3: Analyzing document structure
        upload["status"] = "analyzing"
        upload["updated_at"] = datetime.now().isoformat()
        
        # Step 4: Marking (will be implemented in Epic 4)
        upload["status"] = "marking"
        upload["updated_at"] = datetime.now().isoformat()
        
        # For now, create mock result
        import time
        time.sleep(2)  # Simulate marking
        
        # Generate mock result
        result_id = str(uuid.uuid4())
        upload["result_id"] = result_id
        upload["status"] = "complete"
        upload["updated_at"] = datetime.now().isoformat()
        
        # Create result with actual document stats
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
                    "point": f"Question 1 (detected from document)",
                    "awarded": 1.0,
                    "explanation": "Based on extracted content"
                },
                {
                    "point": f"Question 2 (detected from document)",
                    "awarded": 0.5,
                    "explanation": "Partially correct"
                }
            ],
            "professional_marks": {
                "structure": 0.5,
                "terminology": 0.5,
                "practicality": 0.5
            },
            "feedback": f"Document processed successfully. Found {process_result.get('question_count', 0)} questions.",
            "citations": ["Based on extracted text"],
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Processing complete for {upload_id}")
        
    except Exception as e:
        logger.error(f"Processing failed for {upload_id}: {str(e)}")
        upload["status"] = "failed"
        upload["error"] = str(e)
        upload["updated_at"] = datetime.now().isoformat()