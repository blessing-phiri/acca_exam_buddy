"""
Knowledge Base Service
Handles ingestion and retrieval of ACCA knowledge documents
"""

import os
import json
import hashlib
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging
from pathlib import Path
import re

from backend.services.document_processor import DocumentProcessor
from backend.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

class KnowledgeBase:
    """Main knowledge base for ACCA marking"""
    
    def __init__(self):
        self.vector_store = VectorStore()
        self.processor = DocumentProcessor()
        self.data_dir = "data/knowledge"
        os.makedirs(self.data_dir, exist_ok=True)
        
        # ACCA paper codes
        self.valid_papers = ["AA", "AAA", "F8"]
        
        # Question types for categorization
        self.question_types = [
            "audit_risk",
            "ethical_threats", 
            "substantive_procedures",
            "internal_control",
            "audit_report",
            "going_concern",
            "professional_marks"
        ]
    
    def ingest_marking_scheme(self, file_path: str, metadata: Dict) -> Dict:
        """
        Ingest a marking scheme PDF into the knowledge base
        
        Args:
            file_path: Path to marking scheme PDF
            metadata: Metadata about the document (paper, year, etc.)
        
        Returns:
            Ingestion results with stats
        """
        logger.info(f"Ingesting marking scheme: {file_path}")
        
        # Process the document
        process_result = self.processor.process(file_path)
        
        if not process_result.get("success", False):
            return {
                "success": False,
                "error": process_result.get("error", "Processing failed")
            }
        
        text = process_result.get("text", "")
        
        # Chunk the document intelligently
        chunks = self._chunk_marking_scheme(text, metadata)
        
        # Add to vector store
        ids = self.vector_store.add_document_chunks(
            collection_name="marking_schemes",
            chunks=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks]
        )
        
        # Save ingestion record
        ingestion_record = {
            "file_path": file_path,
            "metadata": metadata,
            "chunk_count": len(chunks),
            "chunk_ids": ids,
            "ingested_at": datetime.now().isoformat()
        }
        
        # Save to JSON for tracking
        record_file = os.path.join(
            self.data_dir, 
            f"ingestion_{hashlib.md5(file_path.encode()).hexdigest()}.json"
        )
        with open(record_file, 'w') as f:
            json.dump(ingestion_record, f, indent=2)
        
        return {
            "success": True,
            "chunk_count": len(chunks),
            "ids": ids,
            "record_file": record_file
        }
    
    def ingest_examiner_report(self, file_path: str, metadata: Dict) -> Dict:
        """
        Ingest an examiner report into the knowledge base
        
        Examiner reports contain valuable insights about:
        - Common mistakes
        - What good answers look like
        - Partial credit guidance
        """
        logger.info(f"Ingesting examiner report: {file_path}")
        
        process_result = self.processor.process(file_path)
        
        if not process_result.get("success", False):
            return {"success": False, "error": process_result.get("error")}
        
        text = process_result.get("text", "")
        
        # Extract specific sections from examiner reports
        sections = self._extract_examiner_sections(text)
        
        chunks = []
        for section in sections:
            chunks.append({
                "text": section["text"],
                "metadata": {
                    **metadata,
                    "section_type": section["type"],
                    "question_ref": section.get("question_ref", "general"),
                    "insight_type": section.get("insight_type", "general")
                }
            })
        
        # Add to vector store
        ids = self.vector_store.add_document_chunks(
            collection_name="examiner_reports",
            chunks=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks]
        )
        
        return {
            "success": True,
            "chunk_count": len(chunks),
            "ids": ids
        }
    
    def _chunk_marking_scheme(self, text: str, base_metadata: Dict) -> List[Dict]:
        """
        Intelligently chunk a marking scheme by question and sub-question
        
        Returns list of chunks with metadata
        """
        chunks = []
        
        # Split by question markers
        lines = text.split('\n')
        current_chunk = []
        current_question = None
        current_marks = None
        
        question_patterns = [
            r'Question\s+(\d+)',
            r'Requirement\s*\(([a-z])\)',
            r'\(([a-z])\)\s+marks?\s*(\d+)',
            r'Part\s+\(([a-z])\)'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this line starts a new question
            is_new_question = False
            question_match = None
            marks_match = None
            
            for pattern in question_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    is_new_question = True
                    if len(match.groups()) >= 1:
                        current_question = match.group(1)
                    if len(match.groups()) >= 2:
                        try:
                            current_marks = float(match.group(2))
                        except:
                            current_marks = None
                    break
            
            if is_new_question and current_chunk:
                # Save previous chunk
                chunk_text = '\n'.join(current_chunk)
                if len(chunk_text) > 50:  # Minimum chunk size
                    chunks.append({
                        "text": chunk_text,
                        "metadata": {
                            **base_metadata,
                            "question_ref": current_question,
                            "marks": current_marks,
                            "chunk_type": "question"
                        }
                    })
                current_chunk = [line]
            else:
                current_chunk.append(line)
        
        # Add last chunk
        if current_chunk:
            chunk_text = '\n'.join(current_chunk)
            if len(chunk_text) > 50:
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        **base_metadata,
                        "question_ref": current_question,
                        "marks": current_marks,
                        "chunk_type": "question"
                    }
                })
        
        # Also create smaller chunks for specific marking points
        marking_points = self.processor.extract_marking_points(text)
        for i, point in enumerate(marking_points):
            chunks.append({
                "text": point["criteria"],
                "metadata": {
                    **base_metadata,
                    "marks": point["marks"],
                    "chunk_type": "marking_point",
                    "point_index": i
                }
            })
        
        return chunks
    
    def _extract_examiner_sections(self, text: str) -> List[Dict]:
        """
        Extract specific sections from examiner reports
        
        Sections include:
        - Common mistakes
        - Good answers
        - Partial credit guidance
        - Specific question feedback
        """
        sections = []
        
        # Look for common mistakes sections
        mistake_patterns = [
            r'common mistakes?(.*?)(?=\n\n|\Z)',
            r'common errors?(.*?)(?=\n\n|\Z)',
            r'weaknesses(.*?)(?=\n\n|\Z)'
        ]
        
        for pattern in mistake_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                sections.append({
                    "text": match.strip(),
                    "type": "examiner_comment",
                    "insight_type": "common_mistakes"
                })
        
        # Look for good answer examples
        good_patterns = [
            r'good answers?(.*?)(?=\n\n|\Z)',
            r'strong answers?(.*?)(?=\n\n|\Z)',
            r'excellent responses?(.*?)(?=\n\n|\Z)'
        ]
        
        for pattern in good_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                sections.append({
                    "text": match.strip(),
                    "type": "examiner_comment",
                    "insight_type": "good_example"
                })
        
        # Look for partial credit guidance
        partial_patterns = [
            r'partial credit(.*?)(?=\n\n|\Z)',
            r'half mark(.*?)(?=\n\n|\Z)',
            r'½ mark(.*?)(?=\n\n|\Z)'
        ]
        
        for pattern in partial_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                sections.append({
                    "text": match.strip(),
                    "type": "examiner_comment",
                    "insight_type": "partial_credit"
                })
        
        # If no specific sections found, chunk by question
        if not sections:
            questions = self.processor.detect_questions(text)
            for q in questions:
                sections.append({
                    "text": q.get("text", ""),
                    "type": "question_feedback",
                    "question_ref": q.get("part", q.get("number", "unknown"))
                })
        
        return sections
    
    def retrieve_marking_rules(self, 
                              question_text: str,
                              question_type: str = None,
                              paper: str = "AA",
                              n_results: int = 5) -> List[Dict]:
        """
        Retrieve relevant marking rules for a question
        
        This is the core RAG retrieval function
        """
        # Extract keywords for hybrid search
        from backend.utils.text_utils import extract_keywords
        keywords = extract_keywords(question_text)
        
        # Build filter
        filter_dict = {}
        if paper:
            filter_dict["paper"] = paper
        if question_type:
            filter_dict["question_type"] = question_type
        
        # Search marking schemes
        results = self.vector_store.hybrid_search(
            collection_name="marking_schemes",
            query=question_text,
            keywords=keywords,
            n_results=n_results
        )
        
        return results
    
    def retrieve_examiner_guidance(self,
                                  question_text: str,
                                  question_type: str = None,
                                  n_results: int = 3) -> List[Dict]:
        """
        Retrieve relevant examiner guidance
        
        This provides insights about common mistakes and good answers
        """
        # Search examiner reports
        results = self.vector_store.search(
            collection_name="examiner_reports",
            query=question_text,
            n_results=n_results,
            filter_dict={"question_type": question_type} if question_type else None
        )
        
        return results
    
    def get_knowledge_summary(self) -> Dict:
        """Get summary of knowledge base contents"""
        
        stats = {}
        for collection in ["marking_schemes", "examiner_reports", "technical_articles"]:
            stats[collection] = self.vector_store.get_collection_stats(collection)
        
        # Count ingested files
        ingested_files = list(Path(self.data_dir).glob("ingestion_*.json"))
        
        return {
            "vector_stats": stats,
            "ingested_files_count": len(ingested_files),
            "status": "ready"
        }