"""
Marking API Endpoints
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
import uuid

from backend.services.marking_service import MarkingService
from backend.services.processing_service import ProcessingService

router = APIRouter(prefix="/api/v1/mark", tags=["marking"])

# Initialize services
marking_service = MarkingService()
processing_service = ProcessingService()

# Request/Response models
class MarkRequest(BaseModel):
    question_text: str
    student_answer: str
    max_marks: float = Field(..., gt=0, le=30)
    question_type: Optional[str] = None
    paper_code: str = "AA"
    context: Optional[Dict] = None

class MarkResponse(BaseModel):
    id: str
    total_marks: float
    max_marks: float
    percentage: float
    question_marks: List[Dict]
    professional_marks: Dict[str, float]
    feedback: str
    citations: List[str]
    confidence_score: float
    needs_review: bool
    processing_time_ms: float
    model_used: str
    created_at: str

class BatchMarkRequest(BaseModel):
    answers: List[Dict]  # Each with question_text, student_answer, max_marks
    paper_code: str = "AA"

class BatchMarkResponse(BaseModel):
    batch_id: str
    status: str
    total_answers: int
    estimated_time_seconds: int

@router.post("/", response_model=MarkResponse)
async def mark_answer(request: MarkRequest):
    """Mark a single answer"""
    
    try:
        result = await marking_service.mark_answer(
            question_text=request.question_text,
            student_answer=request.student_answer,
            max_marks=request.max_marks,
            question_type=request.question_type,
            paper_code=request.paper_code,
            context=request.context
        )
        
        # Add metadata
        result["id"] = str(uuid.uuid4())
        result["created_at"] = datetime.now().isoformat()
        result["percentage"] = (result["total_marks"] / request.max_marks) * 100
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch", response_model=BatchMarkResponse)
async def mark_batch(request: BatchMarkRequest, background_tasks: BackgroundTasks):
    """Start batch marking job"""
    
    batch_id = str(uuid.uuid4())
    
    # Store batch info (in real implementation, use database)
    batch_info = {
        "id": batch_id,
        "status": "pending",
        "answers": request.answers,
        "paper_code": request.paper_code,
        "created_at": datetime.now().isoformat(),
        "results": []
    }
    
    # Start processing in background
    background_tasks.add_task(process_batch, batch_id, batch_info)
    
    return BatchMarkResponse(
        batch_id=batch_id,
        status="pending",
        total_answers=len(request.answers),
        estimated_time_seconds=len(request.answers) * 30  # Rough estimate
    )

@router.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Get batch marking status"""
    
    # In real implementation, retrieve from database
    # This is a placeholder
    return {
        "batch_id": batch_id,
        "status": "processing",
        "progress": 50,
        "completed": 5,
        "total": 10
    }

@router.get("/types")
async def get_question_types():
    """Get supported question types"""
    return {
        "types": [
            {"id": "audit_risk", "name": "Audit Risk", "description": "Identify and explain audit risks"},
            {"id": "ethical_threats", "name": "Ethical Threats", "description": "Identify ethical threats and safeguards"},
            {"id": "substantive_procedures", "name": "Substantive Procedures", "description": "Describe audit procedures"},
            {"id": "internal_control", "name": "Internal Control", "description": "Identify control deficiencies"},
            {"id": "audit_report", "name": "Audit Report", "description": "Determine audit opinion"},
            {"id": "going_concern", "name": "Going Concern", "description": "Evaluate going concern issues"}
        ]
    }

@router.get("/stats")
async def get_marking_stats():
    """Get marking statistics"""
    return marking_service.get_stats()

async def process_batch(batch_id: str, batch_info: Dict):
    """Process batch marking in background"""
    
    # Update status
    batch_info["status"] = "processing"
    
    results = []
    for i, answer in enumerate(batch_info["answers"]):
        try:
            result = await marking_service.mark_answer(
                question_text=answer["question_text"],
                student_answer=answer["student_answer"],
                max_marks=answer["max_marks"],
                paper_code=batch_info["paper_code"]
            )
            
            result["id"] = str(uuid.uuid4())
            result["created_at"] = datetime.now().isoformat()
            result["percentage"] = (result["total_marks"] / answer["max_marks"]) * 100
            
            results.append(result)
            
        except Exception as e:
            results.append({
                "error": str(e),
                "answer_index": i
            })
        
        # Update progress (in real implementation, store in database)
        batch_info["progress"] = (i + 1) / len(batch_info["answers"]) * 100
    
    batch_info["status"] = "completed"
    batch_info["results"] = results
    batch_info["completed_at"] = datetime.now().isoformat()
    
    # In real implementation, save to database
    logger.info(f"Batch {batch_id} completed with {len(results)} results")