"""
Core Marking Service
Orchestrates the entire marking process with RAG and LLM
"""

import os
import json
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from enum import Enum

from backend.services.knowledge_base import KnowledgeBase
from backend.services.vector_store import VectorStore
from backend.llm.providers import DeepSeekProvider, MiniMaxProvider

logger = logging.getLogger(__name__)

class QuestionType(str, Enum):
    AUDIT_RISK = "audit_risk"
    ETHICAL_THREATS = "ethical_threats"
    SUBSTANTIVE_PROCEDURES = "substantive_procedures"
    INTERNAL_CONTROL = "internal_control"
    AUDIT_REPORT = "audit_report"
    GOING_CONCERN = "going_concern"
    PROFESSIONAL_MARKS = "professional_marks"

class MarkingService:
    """Main marking engine"""
    
    def __init__(self):
        self.knowledge_base = KnowledgeBase()
        self.vector_store = VectorStore()
        
        # Initialize LLM providers
        self.primary_llm = DeepSeekProvider()
        self.fallback_llm = MiniMaxProvider()
        
        # Load prompt templates
        self.prompt_templates = self._load_prompt_templates()
        
        # Marking statistics
        self.stats = {
            "total_marked": 0,
            "avg_confidence": 0,
            "avg_time_ms": 0,
            "by_type": {}
        }
    
    def _load_prompt_templates(self) -> Dict:
        """Load prompt templates for different question types"""
        return {
            QuestionType.AUDIT_RISK: self._build_audit_risk_prompt,
            QuestionType.ETHICAL_THREATS: self._build_ethical_threats_prompt,
            QuestionType.SUBSTANTIVE_PROCEDURES: self._build_procedures_prompt,
            QuestionType.INTERNAL_CONTROL: self._build_control_prompt,
            QuestionType.AUDIT_REPORT: self._build_report_prompt,
            QuestionType.GOING_CONCERN: self._build_going_concern_prompt,
        }
    
    async def mark_answer(self, 
                         question_text: str,
                         student_answer: str,
                         max_marks: float,
                         question_type: Optional[str] = None,
                         paper_code: str = "AA",
                         context: Optional[Dict] = None) -> Dict:
        """
        Main entry point - mark a student answer
        
        Args:
            question_text: The exam question
            student_answer: The student's answer
            max_marks: Maximum marks available
            question_type: Type of question (auto-detected if not provided)
            paper_code: ACCA paper code (AA, AAA, etc.)
            context: Additional context (marking scheme, etc.)
        
        Returns:
            Marking result with breakdown and feedback
        """
        start_time = datetime.now()
        
        # Step 1: Detect question type if not provided
        if not question_type:
            question_type = self._detect_question_type(question_text)
        
        logger.info(f"Marking {question_type} question, max marks: {max_marks}")
        
        # Step 2: Retrieve relevant knowledge
        marking_rules = await self._retrieve_marking_rules(
            question_text, question_type, paper_code
        )
        
        examiner_guidance = await self._retrieve_examiner_guidance(
            question_text, question_type, paper_code
        )
        
        # Step 3: Build prompt
        prompt_builder = self.prompt_templates.get(
            question_type, 
            self._build_generic_prompt
        )
        
        prompt = prompt_builder(
            question_text=question_text,
            student_answer=student_answer,
            marking_rules=marking_rules,
            examiner_guidance=examiner_guidance,
            max_marks=max_marks,
            context=context
        )
        
        # Step 4: Call LLM with retry logic
        llm_response = await self._call_llm_with_retry(prompt)
        
        # Step 5: Parse and validate response
        result = self._parse_llm_response(llm_response, max_marks)
        
        # Step 6: Add metadata
        result["question_type"] = question_type
        result["paper_code"] = paper_code
        result["processing_time_ms"] = (datetime.now() - start_time).total_seconds() * 1000
        result["model_used"] = self.primary_llm.model_name
        
        # Step 7: Calculate confidence score
        result["confidence_score"] = self._calculate_confidence(result)
        
        # Step 8: Store for consistency checking
        await self._store_for_consistency(result, student_answer)
        
        # Update stats
        self._update_stats(result)
        
        return result
    
    def _detect_question_type(self, question_text: str) -> str:
        """Detect question type from text"""
        text_lower = question_text.lower()
        
        # Pattern matching for different question types
        if any(term in text_lower for term in ["audit risk", "risk of material misstatement"]):
            return QuestionType.AUDIT_RISK
        elif any(term in text_lower for term in ["ethical threat", "safeguard", "ethics"]):
            return QuestionType.ETHICAL_THREATS
        elif any(term in text_lower for term in ["substantive procedure", "audit procedure"]):
            return QuestionType.SUBSTANTIVE_PROCEDURES
        elif any(term in text_lower for term in ["internal control", "control deficiency"]):
            return QuestionType.INTERNAL_CONTROL
        elif any(term in text_lower for term in ["auditor's report", "audit opinion"]):
            return QuestionType.AUDIT_REPORT
        elif "going concern" in text_lower:
            return QuestionType.GOING_CONCERN
        
        return QuestionType.AUDIT_RISK  # Default
    
    async def _retrieve_marking_rules(self, 
                                     question_text: str,
                                     question_type: str,
                                     paper_code: str) -> List[Dict]:
        """Retrieve relevant marking rules from knowledge base"""
        
        results = self.knowledge_base.retrieve_marking_rules(
            question_text=question_text,
            question_type=question_type,
            paper=paper_code,
            n_results=5
        )
        
        # Format for prompt
        formatted = []
        for r in results:
            formatted.append({
                "text": r["document"],
                "marks": r["metadata"].get("marks", "unknown"),
                "source": r["metadata"].get("paper", "unknown"),
                "relevance": 1 - r.get("distance", 0)
            })
        
        return formatted
    
    async def _retrieve_examiner_guidance(self,
                                        question_text: str,
                                        question_type: str,
                                        paper_code: str) -> List[Dict]:
        """Retrieve relevant examiner guidance"""
        
        results = self.knowledge_base.retrieve_examiner_guidance(
            question_text=question_text,
            question_type=question_type,
            n_results=3
        )
        
        return [r["document"] for r in results]
    
    async def _call_llm_with_retry(self, prompt: str, max_retries: int = 3) -> str:
        """Call LLM with retry logic and fallback"""
        
        for attempt in range(max_retries):
            try:
                # Try primary LLM first
                response = await self.primary_llm.generate(prompt)
                return response
            except Exception as e:
                logger.warning(f"Primary LLM attempt {attempt + 1} failed: {str(e)}")
                
                if attempt == max_retries - 1:
                    # Last attempt - try fallback
                    logger.info("Trying fallback LLM")
                    try:
                        response = await self.fallback_llm.generate(prompt)
                        return response
                    except Exception as e2:
                        logger.error(f"Fallback LLM also failed: {str(e2)}")
                        raise
        
        raise Exception("All LLM attempts failed")
    
    def _parse_llm_response(self, response: str, max_marks: float) -> Dict:
        """Parse LLM response into structured result"""
        
        try:
            # Try to parse as JSON first
            result = json.loads(response)
            
            # Validate required fields
            required_fields = ["total_marks", "question_marks", "feedback"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Missing required field: {field}")
            
            # Ensure marks don't exceed max
            result["total_marks"] = min(float(result["total_marks"]), max_marks)
            
            return result
            
        except json.JSONDecodeError:
            # If not JSON, try to extract structured data from text
            return self._extract_from_text(response, max_marks)
    
    def _extract_from_text(self, text: str, max_marks: float) -> Dict:
        """Extract marking information from text response"""
        
        # This is a fallback - in practice, we'll always ask for JSON
        lines = text.split('\n')
        
        result = {
            "total_marks": 0,
            "question_marks": [],
            "professional_marks": {"structure": 0, "terminology": 0, "practicality": 0},
            "feedback": "",
            "citations": [],
            "needs_review": True  # Flag for review if parsing failed
        }
        
        # Try to find total marks
        import re
        mark_pattern = r'total[:\s]*(\d+(?:\.\d+)?)'
        for line in lines:
            match = re.search(mark_pattern, line, re.IGNORECASE)
            if match:
                result["total_marks"] = min(float(match.group(1)), max_marks)
                break
        
        # Use whole text as feedback
        result["feedback"] = text[:500]  # First 500 chars
        
        return result
    
    def _calculate_confidence(self, result: Dict) -> float:
        """Calculate confidence score (0-1) for the marking"""
        
        confidence = 1.0
        
        # Deduct for missing data
        if not result.get("question_marks"):
            confidence -= 0.3
        
        if not result.get("professional_marks"):
            confidence -= 0.2
        
        # Check if marks seem reasonable
        total = result.get("total_marks", 0)
        max_marks = result.get("max_marks", 0)
        
        if max_marks > 0:
            percentage = total / max_marks
            
            # Very high or very low scores might need review
            if percentage > 0.95 or percentage < 0.1:
                confidence -= 0.1
        
        # Flag for review if low confidence
        result["needs_review"] = confidence < 0.7
        
        return max(0, min(1, confidence))
    
    async def _store_for_consistency(self, result: Dict, answer_text: str):
        """Store marking result for future consistency checks"""
        
        # This will be implemented in Epic 5
        pass
    
    def _update_stats(self, result: Dict):
        """Update marking statistics"""
        self.stats["total_marked"] += 1
        
        q_type = result.get("question_type", "unknown")
        if q_type not in self.stats["by_type"]:
            self.stats["by_type"][q_type] = {
                "count": 0,
                "total_confidence": 0,
                "total_time": 0
            }
        
        self.stats["by_type"][q_type]["count"] += 1
        self.stats["by_type"][q_type]["total_confidence"] += result.get("confidence_score", 0)
        self.stats["by_type"][q_type]["total_time"] += result.get("processing_time_ms", 0)
        
        # Update averages
        self.stats["avg_confidence"] = (
            sum(t["total_confidence"] for t in self.stats["by_type"].values()) /
            self.stats["total_marked"]
        )
    
    def get_stats(self) -> Dict:
        """Get marking statistics"""
        return self.stats