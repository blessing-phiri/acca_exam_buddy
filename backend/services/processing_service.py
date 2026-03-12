"""
Processing Service - Orchestrates document processing pipeline
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
import logging
from pathlib import Path

from backend.services.document_processor import DocumentProcessor

logger = logging.getLogger(__name__)

class ProcessingService:
    """Orchestrates the document processing pipeline"""
    
    def __init__(self, storage_path: str = "data/processed"):
        self.processor = DocumentProcessor()
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        
    def process_upload(self, file_path: str, upload_id: str) -> Dict:
        """
        Full processing pipeline for an uploaded file
        
        Steps:
        1. Extract raw text
        2. Clean text
        3. Detect questions
        4. Extract metadata
        5. Save processed result
        """
        logger.info(f"Processing upload {upload_id}: {file_path}")
        
        # Step 1: Extract raw text
        extraction_result = self.processor.process(file_path)
        
        if not extraction_result.get("success", False):
            return {
                "success": False,
                "error": extraction_result.get("error", "Unknown error"),
                "stage": "extraction"
            }
        
        raw_text = extraction_result.get("text", "")
        
        # Step 2: Clean text
        cleaned_text = self.processor.clean_text(raw_text)
        
        # Step 3: Detect questions
        questions = self.processor.detect_questions(cleaned_text)
        
        # Step 4: Extract metadata
        metadata = self._extract_metadata(cleaned_text, extraction_result)
        
        # Step 5: Generate document hash for deduplication
        doc_hash = hashlib.md5(raw_text.encode()).hexdigest()
        
        # Step 6: Save processed result
        processed_result = {
            "upload_id": upload_id,
            "original_file": file_path,
            "doc_hash": doc_hash,
            "extraction": extraction_result,
            "cleaned_text": cleaned_text,
            "questions": questions,
            "metadata": metadata,
            "word_count": len(cleaned_text.split()),
            "char_count": len(cleaned_text),
            "processed_at": datetime.now().isoformat()
        }
        
        # Save to file
        self._save_processed(upload_id, processed_result)
        
        return {
            "success": True,
            "upload_id": upload_id,
            "doc_hash": doc_hash,
            "question_count": len(questions),
            "word_count": processed_result["word_count"],
            "has_questions": len(questions) > 0,
            "metadata": metadata
        }
    
    def _extract_metadata(self, text: str, extraction: Dict) -> Dict:
        """Extract useful metadata from document"""
        metadata = {
            "file_type": extraction.get("file_type", "unknown"),
            "has_tables": False,
            "has_bullets": False,
            "has_numbers": False,
            "possible_paper": None,
            "possible_year": None
        }
        
        # Check for tables (in Word docs)
        if extraction.get("file_type") == "docx" and extraction.get("tables"):
            metadata["has_tables"] = len(extraction["tables"]) > 0
        
        # Check for common ACCA patterns
        lines = text.split('\n')
        
        # Look for paper code (AA, AAA, etc.)
        paper_match = re.search(r'\b(AA|AAA|F8|F8?)\b', text, re.IGNORECASE)
        if paper_match:
            metadata["possible_paper"] = paper_match.group(0).upper()
        
        # Look for year (20XX)
        year_match = re.search(r'20\d{2}', text)
        if year_match:
            metadata["possible_year"] = year_match.group(0)
        
        # Check formatting
        metadata["has_bullets"] = any(line.strip().startswith(('•', '-', '*')) for line in lines[:20])
        metadata["has_numbers"] = any(line.strip()[0].isdigit() for line in lines[:20])
        
        return metadata
    
    def _save_processed(self, upload_id: str, data: Dict):
        """Save processed data to JSON file"""
        file_path = os.path.join(self.storage_path, f"{upload_id}_processed.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Saved processed data to {file_path}")
    
    def load_processed(self, upload_id: str) -> Optional[Dict]:
        """Load previously processed data"""
        file_path = os.path.join(self.storage_path, f"{upload_id}_processed.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def get_stats(self) -> Dict:
        """Get processing statistics"""
        processed_files = list(Path(self.storage_path).glob("*_processed.json"))
        
        total_words = 0
        total_questions = 0
        
        for file in processed_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    total_words += data.get("word_count", 0)
                    total_questions += len(data.get("questions", []))
            except:
                pass
        
        return {
            "processed_count": len(processed_files),
            "total_words": total_words,
            "total_questions": total_questions,
            "avg_words_per_doc": total_words // max(len(processed_files), 1),
            "storage_path": self.storage_path
        }