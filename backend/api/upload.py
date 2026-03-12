"""
Upload endpoints for handling file uploads
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import Optional
import uuid
import os
from datetime import datetime
import shutil

router = APIRouter()

# In-memory storage for demo (replace with database later)
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
    
    # Generate unique ID
    upload_id = str(uuid.uuid4())
    
    # Create upload directory if not exists
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Save file
    file_path = f"{upload_dir}/{upload_id}_{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Store metadata
    uploads[upload_id] = {
        "id": upload_id,
        "filename": file.filename,
        "paper": paper,
        "question_number": question_number,
        "file_path": file_path,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    
    # Start processing in background (simulated for now)
    background_tasks.add_task(process_file, upload_id)
    
    return {
        "upload_id": upload_id,
        "status": "pending",
        "message": "File uploaded successfully. Processing started."
    }

@router.get("/api/v1/status/{upload_id}")
async def get_status(upload_id: str):
    """Get processing status for an upload"""
    if upload_id not in uploads:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    upload = uploads[upload_id]
    
    # Simulate progress based on status
    progress_map = {
        "pending": 10,
        "extracting": 30,
        "cleaning": 50,
        "marking": 70,
        "complete": 100,
        "failed": 0
    }
    
    return {
        "upload_id": upload_id,
        "status": upload["status"],
        "progress": progress_map.get(upload["status"], 0),
        "result_id": upload.get("result_id")
    }

@router.get("/api/v1/result/{result_id}")
async def get_result(result_id: str):
    """Get marking result"""
    if result_id not in results:
        raise HTTPException(status_code=404, detail="Result not found")
    
    return results[result_id]

def process_file(upload_id: str):
    """Background processing of uploaded file"""
    import time
    
    upload = uploads[upload_id]
    
    # Simulate processing steps
    steps = ["extracting", "cleaning", "marking", "complete"]
    for step in steps:
        time.sleep(2)  # Simulate work
        upload["status"] = step
        
        if step == "complete":
            # Create mock result
            result_id = str(uuid.uuid4())
            upload["result_id"] = result_id
            
            results[result_id] = {
                "id": result_id,
                "upload_id": upload_id,
                "total_marks": 14.5,
                "max_marks": 16,
                "percentage": 90.6,
                "question_marks": [
                    {
                        "point": "Identified IT system risk",
                        "awarded": 0.5,
                        "explanation": "Correctly identified the risk from new IT system"
                    },
                    {
                        "point": "Explained impact on completeness",
                        "awarded": 0.5,
                        "explanation": "Linked to completeness assertion"
                    },
                    {
                        "point": "Auditor response - test controls",
                        "awarded": 1.0,
                        "explanation": "Specific testing procedures described"
                    }
                ],
                "professional_marks": {
                    "structure": 0.5,
                    "terminology": 0.5,
                    "practicality": 0.5
                },
                "feedback": "Good answer! You identified key risks and provided specific responses.",
                "citations": ["ISA 240", "ISA 315"],
                "created_at": datetime.now().isoformat()
            }